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
    _, trabalho = preparar("Exec Produto", item="foto_produto")
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
