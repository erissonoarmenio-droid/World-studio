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
