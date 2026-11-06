"""Passo 1.2, parte 4: a fila gera a foto pelo nó (fornecedor simulado, sem gastar)."""

import base64
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select

from app import pedidos
from app.creditos import servico as cr
from app.geracao import executores
from app.geracao.fornecedores.base import Resposta
from app.nucleo import midia
from app.nucleo.consentimentos import registrar_aceite
from app.nucleo.db import sessao
from app.nucleo.eventos import ERI, Autor
from app.nucleo.fila.trabalhador import concluir
from app.nucleo.modelos import Trabalho

PNG = b"\x89PNG\r\n\x1a\nfoto-falsa"
ENTRADA = {
    "idade": 26,
    "peca": "She wears a terracotta linen shirt with a pointed collar.",
    "cenario": "a small, cozy Brazilian clothing boutique",
    "cena": "SCENE: standing by the clothing rack, natural light, relaxed smile.",
}


class GoogleSimulado:
    nome = "google"

    def __init__(self):
        self.envios = 0
        self.consultas = 0

    def enviar(self, pedido):
        self.envios += 1
        return Resposta(estado="na_fila", id=f"lote-{self.envios}")

    def consultar(self, id_trabalho):
        self.consultas += 1
        dados = base64.b64encode(PNG).decode()
        parte = {"inlineData": {"mimeType": "image/png", "data": dados}}
        return Resposta(estado="pronto", id=id_trabalho, saidas=[parte])


@pytest.fixture(autouse=True)
def limpar_trabalhos_rodando():
    """Estes testes gravam no banco de verdade e deixam trabalhos "rodando"; no fim, cancela
    para não confundir os testes da fila que procuram trabalhos travados."""
    yield
    from sqlalchemy import update

    with sessao() as s:
        s.execute(
            update(Trabalho)
            .where(Trabalho.estado == "rodando")
            .values(estado="cancelado", travado_ate=None)
        )


@pytest.fixture
def ambiente(monkeypatch):
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="midias-teste")
        monkeypatch.setattr(
            midia, "armazenamento_midias", lambda: midia.Armazenamento(cliente, "midias-teste")
        )
        google = GoogleSimulado()
        monkeypatch.setitem(executores.FORNECEDORES, "google", lambda: google)
        monkeypatch.setattr(executores, "DORMIR", lambda _s: None)
        yield google


def preparar(nome, item="foto", entrada=None):
    with sessao() as s:
        from app.nucleo.lojas import criar_loja_com_dona

        loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
        cr.ativar_plano(s, loja.id, "estudio", f"mp-exec-{loja.id}")
        foto = midia.enviar(
            s,
            loja_id=loja.id,
            conteudo=PNG,
            tipo="influencer",
            content_type="image/png",
            origem="eri",
            autor=ERI,
        )
        chave = f"exec-{loja.id}-1"
        pedidos.criar_pedido(
            s,
            loja_id=loja.id,
            item=item,
            dados={"entrada": entrada or ENTRADA, "influencer_midia_id": foto.id, "opcoes": 2},
            chave_unica=chave,
        )
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == chave))
        trabalho.estado = "rodando"  # como se a fila tivesse pegado
        s.flush()
        s.expunge(trabalho)
        return loja.id, trabalho


def test_foto_gera_2_opcoes_guarda_no_r2_e_desconta(ambiente):
    loja_id, trabalho = preparar("Exec Foto")
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 2 and ambiente.consultas == 2
    assert len(resultado.dados["midias"]) == 2
    assert resultado.custo_real == Decimal("0.08")
    with sessao() as s:
        assert midia.ler(s, resultado.dados["midias"][0], loja_id) == PNG
        concluir(s, trabalho.id, resultado)
        situacao = pedidos.obter_pedido(s, trabalho.chave_unica)
        assert (situacao.estado, situacao.credito) == ("pronto", "debitada")
        assert cr.saldo(s, loja_id).disponivel == 73


def test_pedido_barrado_pela_regra_nao_gasta(ambiente):
    from app.geracao.nos.base import PedidoBloqueado

    _, trabalho = preparar("Exec Bloqueio", entrada={**ENTRADA, "idade": 17})
    with pytest.raises((PedidoBloqueado, ValueError)):
        executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 0


def test_item_ainda_nao_ligado_falha_com_motivo(ambiente):
    _, trabalho = preparar("Exec Nao Ligado")
    trabalho.dados["item"] = "item_que_nao_existe"
    with pytest.raises(executores.NaoLigado):
        executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 0


# --- vídeo (Tein simulada) ----------------------------------------------------------------------

MP4 = b"\x00\x00\x00\x18ftypmp42video-falso"


class TeinSimulada:
    nome = "tein"

    def __init__(self):
        self.envios = 0
        self.uploads = 0

    def subir_midia(self, conteudo, nome_arquivo, tipo):
        self.uploads += 1
        return "https://tein.exemplo/quadro1.png"

    def enviar(self, pedido):
        self.envios += 1
        assert pedido.payload["reference_image"] == ["https://tein.exemplo/quadro1.png"]
        return Resposta(estado="na_fila", id=f"job-{self.envios}")

    def consultar(self, id_trabalho):
        return Resposta(
            estado="pronto", id=id_trabalho, saidas=["https://tein.exemplo/v.mp4"], custo=2.05
        )


def _roteiro():
    from tests.geracao.test_no_video_ugc import _v3

    return _v3().model_dump(mode="json", exclude={"imagem_url", "audio_url", "resolucao"})


def preparar_video(nome, item="video_480", entradas=None):
    with sessao() as s:
        from app.nucleo.lojas import criar_loja_com_dona

        loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
        cr.ativar_plano(s, loja.id, "social_media", f"mp-vid-{loja.id}")
        quadro = midia.enviar(
            s,
            loja_id=loja.id,
            conteudo=PNG,
            tipo="resultado",
            content_type="image/png",
            origem="geracao",
            autor=ERI,
        )
        chave = f"vid-{loja.id}-1"
        pedidos.criar_pedido(
            s,
            loja_id=loja.id,
            item=item,
            dados={
                "entradas": entradas if entradas is not None else [_roteiro()],
                "primeiro_quadro_midia_id": quadro.id,
            },
            chave_unica=chave,
        )
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == chave))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
        return loja.id, trabalho


@pytest.fixture
def tein(ambiente, monkeypatch):
    t = TeinSimulada()
    monkeypatch.setitem(executores.FORNECEDORES, "tein", lambda: t)
    monkeypatch.setattr(executores, "BAIXAR", lambda url: MP4)
    return t


def test_video_gera_baixa_para_o_r2_e_guarda_o_custo_cobrado(tein):
    loja_id, trabalho = preparar_video("Exec Video")
    resultado = executores.executar_video(trabalho)
    assert tein.uploads == 1 and tein.envios == 1
    assert resultado.custo_real == Decimal("2.05")
    with sessao() as s:
        assert midia.ler(s, resultado.dados["midias"][0], loja_id) == MP4
        concluir(s, trabalho.id, resultado)
        assert cr.saldo(s, loja_id).disponivel == 180 - 15


def test_dois_angulos_conferem_os_dois_roteiros_antes_de_gastar(tein):
    ruim = {**_roteiro(), "planos": [{**_roteiro()["planos"][0], "fala": "x " * 60}]}
    _, trabalho = preparar_video(
        "Exec 2 angulos", item="video_2_angulos", entradas=[_roteiro(), ruim]
    )
    with pytest.raises(Exception):  # noqa: B017 - qualquer barreira serve: nada pode ter saído
        executores.executar_video(trabalho)
    assert tein.envios == 0


# --- foto de produto -----------------------------------------------------------------------

PRODUTO = {
    "peca_nome": "shirt",
    "detalhes": "terracotta linen shirt, pointed collar, tone-on-tone buttons, no pocket",
    "cena": "mesa",
    "opcoes": 2,
}


def preparar_produto(nome, **extra):
    with sessao() as s:
        from app.nucleo.lojas import criar_loja_com_dona

        loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
        cr.ativar_plano(s, loja.id, "estudio", f"mp-prod-{loja.id}")
        peca = midia.enviar(
            s,
            loja_id=loja.id,
            conteudo=PNG,
            tipo="peca",
            content_type="image/png",
            origem="lojista",
            autor=ERI,
        )
        chave = f"prod-{loja.id}-1"
        pedidos.criar_pedido(
            s,
            loja_id=loja.id,
            item="foto_produto",
            dados={**PRODUTO, "peca_midia_id": peca.id, **extra},
            chave_unica=chave,
        )
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == chave))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
        return loja.id, trabalho, peca.id


def test_foto_produto_extrai_uma_vez_e_faz_2_cenas(ambiente):
    loja_id, trabalho, _ = preparar_produto("Exec Produto")
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 3  # 1 extração + 2 cenas
    assert len(resultado.dados["midias"]) == 2 and resultado.dados["extraida_midia_id"]
    assert resultado.custo_real == Decimal("0.06")


def test_foto_produto_reaproveita_a_peca_ja_extraida(ambiente):
    _, trabalho, peca_id = preparar_produto("Exec Produto 2")
    trabalho.dados["extraida_midia_id"] = peca_id
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 2  # só as cenas
    assert resultado.dados["extraida_midia_id"] == peca_id


def test_cena_livre_sem_descricao_e_barrada_antes_de_gastar(ambiente):
    _, trabalho, _ = preparar_produto("Exec Produto 3", cena="livre", cena_livre="chao")
    with pytest.raises(ValueError):
        executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 0


# --- criar influencer ----------------------------------------------------------------------

INFLUENCER = {
    "genero": "homem",
    "idade": 27,
    "corpo": "tall and slim build",
    "roupa": "a plain white crew-neck t-shirt and black shorts",
    "oculos": "black rectangular eyeglasses",
    "aparencia": "a wide, softly rounded face with full cheeks and short dark stubble beard",
}


def preparar_influencer(nome, item="influencer_principal", consentir=True, **dados):
    with sessao() as s:
        from app.nucleo.lojas import criar_loja_com_dona

        loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Eri"}, ERI)
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
        if consentir:
            registrar_aceite(s, dona.id, "clone", "v1", Autor("pessoa", dona.id))
        cr.ativar_plano(s, loja.id, "estudio", f"mp-inf-{loja.id}")
        ids = [
            midia.enviar(
                s,
                loja_id=loja.id,
                conteudo=PNG,
                tipo="influencer",
                content_type="image/png",
                origem="lojista",
                autor=ERI,
            ).id
            for _ in range(4)
        ]
        chave = f"inf-{loja.id}-1"
        extra = (
            {"pessoa_id": dona.id, "fotos_midia_ids": ids}
            if dados.get("modo") == "da_pessoa"
            else {}
        )
        if dados.get("modo") == "vistas":
            extra = {"anterior_midia_id": ids[0]}
        pedidos.criar_pedido(
            s, loja_id=loja.id, item=item, dados={**INFLUENCER, **extra, **dados}, chave_unica=chave
        )
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == chave))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
        return loja.id, trabalho


def test_influencer_nova_gera_a_principal(ambiente):
    _, trabalho = preparar_influencer(
        "Inf Nova", modo="nova", aparencia="short dark wavy hair, brown eyes, light stubble"
    )
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and len(resultado.dados["midias"]) == 1


def test_influencer_da_pessoa_com_consentimento(ambiente):
    _, trabalho = preparar_influencer("Inf Pessoa", modo="da_pessoa")
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and resultado.dados["modo"] == "da_pessoa"


def test_influencer_da_pessoa_sem_consentimento_nao_gasta(ambiente):
    _, trabalho = preparar_influencer("Inf Sem Ok", consentir=False, modo="da_pessoa")
    with pytest.raises(PermissionError):
        executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 0


def test_vistas_geram_close_e_costas(ambiente):
    _, trabalho = preparar_influencer("Inf Vistas", modo="vistas")
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 2 and len(resultado.dados["midias"]) == 2


def test_lote_aceito_e_tentativa_caida_nao_paga_duas_vezes(ambiente, monkeypatch):
    """E36 (06/11): a nova tentativa retoma o MESMO lote pelo id guardado no trabalho."""
    _, trabalho = preparar_influencer("Inf E36", modo="nova", aparencia="short dark wavy hair")
    consultas_que_caem = {"n": 1}
    original = ambiente.consultar

    def consultar(id_trabalho):
        if consultas_que_caem["n"]:
            consultas_que_caem["n"] -= 1
            raise TimeoutError("caiu esperando o lote")
        return original(id_trabalho)

    monkeypatch.setattr(ambiente, "consultar", consultar)
    with pytest.raises(TimeoutError):
        executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1
    with sessao() as s:
        envios = s.get(Trabalho, trabalho.id).dados["envios"]
    assert [e["id"] for e in envios.values()] == ["lote-1"]

    with sessao() as s:  # o trabalhador relê o trabalho na nova tentativa
        trabalho = s.get(Trabalho, trabalho.id)
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and len(resultado.dados["midias"]) == 1
