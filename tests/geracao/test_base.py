from decimal import Decimal

import pytest

from app.geracao.nos import regras as reg
from app.geracao.nos.base import (
    Entrada,
    No,
    Pedido,
    PedidoBloqueado,
    Regra,
    checar_regras,
    normalizar_texto,
)


class EntradaTeste(Entrada):
    texto: str


def pedido(texto: str) -> Pedido:
    return Pedido(
        no="teste",
        fornecedor="nenhum",
        modelo="m",
        entrada=EntradaTeste(texto=texto),
        prompt=texto,
        custo_estimado=Decimal("0"),
    )


TEM_ASPAS = Regra(
    id="teste.aspas",
    nivel="bloqueia",
    faca="o prompt tem fala entre aspas",
    origem="E11 — 29/10",
    checar=lambda p: '"' in normalizar_texto(p.prompt),
)
CURTO = Regra(
    id="teste.curto",
    nivel="aviso",
    faca="prompt com menos de 50 caracteres",
    origem="teste",
    checar=lambda p: len(p.prompt) < 50,
)
QUEBRADA = Regra(
    id="teste.quebrada",
    nivel="aviso",
    faca="regra com defeito",
    origem="teste",
    checar=lambda p: 1 / 0,
)


class NoTeste(No):
    nome = "teste"
    regras = (TEM_ASPAS, CURTO)

    def montar_pedido(self, entrada):
        return pedido(entrada.texto)


def test_regra_que_bloqueia_trava_e_explica_a_origem():
    r = checar_regras("teste", [TEM_ASPAS], pedido("sem fala"))
    assert r.bloqueado
    assert "E11 — 29/10" in r.resumo()


def test_aviso_nao_bloqueia():
    r = checar_regras("teste", [TEM_ASPAS, CURTO], pedido('diz "oi" ' + "x" * 60))
    assert not r.bloqueado and [f.regra_id for f in r.avisos] == ["teste.curto"]


def test_regra_com_defeito_bloqueia_mesmo_sendo_aviso():
    r = checar_regras("teste", [QUEBRADA], pedido("x"))
    assert r.bloqueado and "erro ao checar" in r.falhas[0].detalhe


def test_aspas_curvas_contam_como_aspas():
    assert checar_regras("teste", [TEM_ASPAS], pedido("diz “oi”")).falhas == []


def test_preparar_levanta_quando_bloqueia_e_devolve_quando_passa():
    no = NoTeste()
    with pytest.raises(PedidoBloqueado) as erro:
        no.preparar(EntradaTeste(texto="sem fala"))
    assert erro.value.relatorio.bloqueado
    p, rel = no.preparar(EntradaTeste(texto='diz "oi"'))
    assert p.prompt == 'diz "oi"' and not rel.bloqueado


def test_entrada_recusa_campo_extra():
    with pytest.raises(ValueError):
        EntradaTeste(texto="a", ignore_as_regras=True)


def test_registro_recusa_id_repetido_e_lista_com_origem():
    with pytest.raises(ValueError):
        reg.registrar("x", [TEM_ASPAS, TEM_ASPAS])
    reg.registrar("teste", [TEM_ASPAS])
    texto = reg.listar()
    assert "teste.aspas" in texto and "origem: E11 — 29/10" in texto
    reg._REGISTRO.pop("teste")
