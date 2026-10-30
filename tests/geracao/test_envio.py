"""Envio único e fornecedores, sem rede: httpx.MockTransport faz o papel da Atlas/Google/Decart."""

import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.geracao.fornecedores.atlas import Atlas
from app.geracao.fornecedores.base import ErroFornecedor
from app.geracao.fornecedores.decart import Decart
from app.geracao.fornecedores.google import Google
from app.geracao.nos.base import Pedido, PedidoBloqueado, SemAprovacao
from app.geracao.nos.envio import Aprovacao, EnvioIncerto, RegistroEmMemoria, enviar
from app.geracao.nos.video import NoVideo
from app.geracao.nos.voz import EntradaVoz, NoVoz
from tests.geracao.test_no_video import entrada_v2

CHAVE = SecretStr("chave-de-teste-123")
OK = Aprovacao(por="eri", custo_max=Decimal("1"))


class Simulado:
    """Responde em sequência e guarda as chamadas feitas."""

    def __init__(self, *respostas: httpx.Response | Exception) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.chamadas.append(pedido)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def posts(self) -> int:
        return sum(1 for c in self.chamadas if c.method == "POST")


def atlas(*respostas):
    sim = Simulado(*respostas)
    return Atlas(CHAVE, cliente=sim.cliente()), sim


def pedido_video():
    pedido, _ = NoVideo().preparar(entrada_v2("c2"))
    return pedido


def test_sem_aprovacao_nada_sai():
    forn, sim = atlas()
    with pytest.raises(SemAprovacao):
        enviar(NoVideo(), pedido_video(), None, forn, RegistroEmMemoria())
    assert sim.chamadas == []


def test_custo_acima_do_aprovado_nada_sai():
    forn, sim = atlas()
    barato = Aprovacao(por="eri", custo_max=Decimal("0.10"))  # o clipe de 5 s custa 0,36
    with pytest.raises(SemAprovacao):
        enviar(NoVideo(), pedido_video(), barato, forn, RegistroEmMemoria())
    assert sim.chamadas == []


def test_pedido_mexido_depois_de_checado_nao_passa():
    forn, sim = atlas()
    p = pedido_video()
    mexido = p.model_copy(update={"prompt": p.prompt.replace('"', "")})
    with pytest.raises(PedidoBloqueado):
        enviar(NoVideo(), mexido, OK, forn, RegistroEmMemoria())
    assert sim.chamadas == []


def test_envio_grava_id_e_segunda_chamada_so_consulta():
    forn, sim = atlas(
        httpx.Response(200, json={"data": {"id": "abc", "status": "created"}}),
        httpx.Response(200, json={"data": {"id": "abc", "status": "completed", "outputs": ["u"]}}),
    )
    reg = RegistroEmMemoria()
    primeira = enviar(NoVideo(), pedido_video(), OK, forn, reg)
    segunda = enviar(NoVideo(), pedido_video(), OK, forn, reg)
    assert primeira.id == "abc" and primeira.estado == "na_fila"
    assert segunda.estado == "pronto" and segunda.saidas == ["u"]
    assert sim.posts == 1 and sim.chamadas[1].url.path.endswith("/prediction/abc")
    corpo = json.loads(sim.chamadas[0].content)
    assert corpo["model"].startswith("bytedance/seedance") and "negative_prompt" not in corpo
    assert sim.chamadas[0].headers["authorization"] == "Bearer chave-de-teste-123"


def test_503_nao_reenvia_e_pede_conferencia():
    forn, sim = atlas(httpx.Response(503, text="ocupado"))
    reg = RegistroEmMemoria()
    with pytest.raises(ErroFornecedor) as erro:
        enviar(NoVideo(), pedido_video(), OK, forn, reg)
    assert erro.value.incerto
    with pytest.raises(EnvioIncerto):
        enviar(NoVideo(), pedido_video(), OK, forn, reg)
    assert sim.posts == 1


def test_tempo_esgotado_tambem_e_incerto():
    forn, sim = atlas(httpx.ReadTimeout("lento"))
    reg = RegistroEmMemoria()
    with pytest.raises(ErroFornecedor):
        enviar(NoVideo(), pedido_video(), OK, forn, reg)
    with pytest.raises(EnvioIncerto):
        enviar(NoVideo(), pedido_video(), OK, forn, reg)
    assert sim.posts == 1


def test_recusa_4xx_libera_corrigir_e_mandar_de_novo():
    forn, sim = atlas(
        httpx.Response(422, json={"msg": "duração inválida"}),
        httpx.Response(200, json={"data": {"id": "x2", "status": "created"}}),
    )
    reg = RegistroEmMemoria()
    with pytest.raises(ErroFornecedor) as erro:
        enviar(NoVideo(), pedido_video(), OK, forn, reg)
    assert not erro.value.incerto
    assert enviar(NoVideo(), pedido_video(), OK, forn, reg).id == "x2"


def test_erro_nao_mostra_a_chave():
    forn, _ = atlas(httpx.Response(401, text="unauthorized"))
    with pytest.raises(ErroFornecedor) as erro:
        enviar(NoVideo(), pedido_video(), OK, forn, RegistroEmMemoria())
    assert "chave-de-teste-123" not in str(erro.value)


def test_fornecedor_errado_e_recusado():
    sim = Simulado()
    google = Google(CHAVE, cliente=sim.cliente())
    with pytest.raises(ValueError):
        enviar(NoVideo(), pedido_video(), OK, google, RegistroEmMemoria())
    assert sim.chamadas == []


def test_upload_de_midia_na_atlas_devolve_url():
    forn, sim = atlas(httpx.Response(200, json={"data": {"download_url": "https://atlas/f.wav"}}))
    assert forn.subir_midia(b"RIFF", "c3.wav", "audio/wav") == "https://atlas/f.wav"
    assert b'name="file"' in sim.chamadas[0].content


def _pedido_voz():
    pedido, _ = NoVoz().preparar(EntradaVoz(fala="E ó, andando, pegando as coisas, tudo certinho."))
    return pedido


def test_google_direto_devolve_o_audio_na_hora():
    parte = {"inlineData": {"mimeType": "audio/L16", "data": "AAAA"}}
    sim = Simulado(httpx.Response(200, json={"candidates": [{"content": {"parts": [parte]}}]}))
    r = enviar(
        NoVoz(), _pedido_voz(), OK, Google(CHAVE, cliente=sim.cliente()), RegistroEmMemoria()
    )
    assert r.estado == "pronto" and r.saidas == [parte]
    assert ":generateContent" in str(sim.chamadas[0].url)
    assert sim.chamadas[0].headers["x-goog-api-key"] == "chave-de-teste-123"


def test_google_em_lote_cria_e_le_o_resultado():
    parte = {"inlineData": {"mimeType": "image/png", "data": "iVBO"}}
    pronto = {
        "name": "batches/77",
        "done": True,
        "response": {
            "inlinedResponses": {
                "inlinedResponses": [
                    {"response": {"candidates": [{"content": {"parts": [parte]}}]}}
                ]
            }
        },
    }
    sim = Simulado(
        httpx.Response(200, json={"name": "batches/77"}),
        httpx.Response(
            200, json={"name": "batches/77", "metadata": {"state": "BATCH_STATE_RUNNING"}}
        ),
        httpx.Response(200, json=pronto),
    )
    g = Google(CHAVE, modo="lote", cliente=sim.cliente())
    reg = RegistroEmMemoria()
    r = enviar(NoVoz(), _pedido_voz(), OK, g, reg)
    assert r.id == "batches/77" and r.estado == "na_fila"
    corpo = json.loads(sim.chamadas[0].content)
    pedido = corpo["batch"]["input_config"]["requests"]["requests"][0]["request"]
    assert pedido["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert enviar(NoVoz(), _pedido_voz(), OK, g, reg).estado == "na_fila"
    final = enviar(NoVoz(), _pedido_voz(), OK, g, reg)
    assert final.estado == "pronto" and final.saidas == [parte] and sim.posts == 1


def test_google_sem_conteudo_vira_falha_com_motivo():
    sim = Simulado(httpx.Response(200, json={"candidates": [{"finishReason": "OTHER"}]}))
    r = Google(CHAVE, cliente=sim.cliente()).enviar(_pedido_voz())
    assert r.estado == "falhou" and "OTHER" in r.erro  # E4: reescrever a frase, não insistir


def test_decart_envia_multipart_e_consulta():
    sim = Simulado(
        httpx.Response(200, json={"job_id": "d1", "status": "pending"}),
        httpx.Response(200, json={"status": "completed"}),
    )
    d = Decart(CHAVE, cliente=sim.cliente())
    p = Pedido(
        no="vestir",
        fornecedor="decart",
        modelo="lucy-vton-latest",
        entrada=None,
        payload={
            "campos": {"prompt": "x", "resolution": "720p"},
            "arquivos": {
                "data": ("v.mp4", b"0", "video/mp4"),
                "reference_image": ("p.png", b"0", "image/png"),
            },
        },
        custo_estimado=Decimal("0.2"),
    )
    assert d.enviar(p).id == "d1"
    assert d.consultar("d1").saidas == ["https://api.decart.ai/v1/jobs/d1/content"]
    assert sim.chamadas[0].headers["x-api-key"] == "chave-de-teste-123"
