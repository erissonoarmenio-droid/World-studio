"""Tarefa 5: convite da funcionária (abuso primeiro)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.nucleo.convites import definir_permissao_gastos, gerar_convite, usar_convite
from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado, SemPermissao
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import Convite

AGORA = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def loja_dona(sessao_limpa):
    loja, dona = criar_loja_com_dona(
        sessao_limpa, {"nome": "Bella Moda"}, {"nome": "Ana", "telegram_id": 1}, ERI
    )
    return loja, dona, Autor("pessoa", dona.id)


def test_fluxo_completo_registra_eventos(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    convite, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    assert len(codigo) == 9 and codigo[4] == "-"

    func = usar_convite(sessao_limpa, codigo.lower(), {"nome": "Bia", "telegram_id": 2}, AGORA)
    assert func.papel == "funcionaria" and func.loja_id == loja.id
    assert func.pode_aprovar_gastos is False
    assert convite.usado_por == func.id

    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert acoes[-3:] == ["convite_criado", "pessoa_criada", "convite_usado"]


def test_codigo_nunca_fica_em_texto_no_banco(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    convite, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    limpo = codigo.replace("-", "")
    assert limpo not in convite.codigo_hash
    for evento in listar_eventos(sessao_limpa, loja.id):
        assert limpo not in str(evento.detalhes)


def test_convite_usado_uma_vez_so(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    _, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 2}, AGORA)
    with pytest.raises(DadosInvalidos, match="já foi usado"):
        usar_convite(sessao_limpa, codigo, {"nome": "Caio", "telegram_id": 3}, AGORA)


def test_convite_vencido_e_recusado(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    _, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    quase = AGORA + timedelta(hours=47, minutes=59)
    depois = AGORA + timedelta(hours=48)
    with pytest.raises(DadosInvalidos, match="venceu"):
        usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 2}, depois)
    assert usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 2}, quase)


def test_codigo_inventado_e_recusado(sessao_limpa, loja_dona):
    with pytest.raises(NaoEncontrado):
        usar_convite(sessao_limpa, "AAAA-AAAA", {"nome": "Bia"}, AGORA)


def test_convidada_nao_escolhe_o_papel(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    _, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    with pytest.raises(DadosInvalidos, match="papel"):
        usar_convite(sessao_limpa, codigo, {"nome": "Bia", "papel": "dona"}, AGORA)


def test_telegram_repetido_nao_queima_o_convite(sessao_limpa, loja_dona):
    """Se a entrada falha (Telegram já usado), o convite continua sem uso."""
    loja, _, autor_dona = loja_dona
    convite, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    with pytest.raises(Conflito):
        usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 1}, AGORA)
    assert convite.usado_em is None


def test_so_a_dona_gera_convite(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    _, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    func = usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 2}, AGORA)

    with pytest.raises(SemPermissao):
        gerar_convite(sessao_limpa, loja.id, "funcionaria", Autor("pessoa", func.id), AGORA)
    with pytest.raises(SemPermissao):
        gerar_convite(sessao_limpa, loja.id, "socia", SISTEMA, AGORA)
    # Dona de outra loja também não.
    _, outra_dona = criar_loja_com_dona(sessao_limpa, {"nome": "Outra"}, {"nome": "Cris"}, ERI)
    with pytest.raises(SemPermissao):
        gerar_convite(sessao_limpa, loja.id, "socia", Autor("pessoa", outra_dona.id), AGORA)
    # O Eri pode, para dar suporte no piloto.
    convite, _ = gerar_convite(sessao_limpa, loja.id, "socia", ERI, AGORA)
    assert convite.criado_por is None


def test_convite_so_para_socia_ou_funcionaria(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    with pytest.raises(DadosInvalidos):
        gerar_convite(sessao_limpa, loja.id, "dona", autor_dona, AGORA)


def test_codigos_sao_diferentes(sessao_limpa, loja_dona):
    loja, _, autor_dona = loja_dona
    codigos = {gerar_convite(sessao_limpa, loja.id, "socia", autor_dona)[1] for _ in range(20)}
    assert len(codigos) == 20
    assert sessao_limpa.query(Convite).count() == 20


def test_permissao_de_gastos_so_pela_dona(sessao_limpa, loja_dona):
    loja, dona, autor_dona = loja_dona
    _, codigo = gerar_convite(sessao_limpa, loja.id, "funcionaria", autor_dona, AGORA)
    func = usar_convite(sessao_limpa, codigo, {"nome": "Bia", "telegram_id": 2}, AGORA)

    # A funcionária não se dá permissão; o Eri também não decide isso pela dona.
    for autor in (Autor("pessoa", func.id), ERI, SISTEMA):
        with pytest.raises(SemPermissao):
            definir_permissao_gastos(sessao_limpa, func.id, True, autor)
    assert func.pode_aprovar_gastos is False

    definir_permissao_gastos(sessao_limpa, func.id, True, autor_dona)
    assert func.pode_aprovar_gastos is True
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "permissao_gastos_alterada"
    assert ultimo.detalhes == {"pessoa_id": func.id, "pode_aprovar_gastos": True}

    antes = len(listar_eventos(sessao_limpa, loja.id))
    definir_permissao_gastos(sessao_limpa, func.id, True, autor_dona)  # sem mudança
    assert len(listar_eventos(sessao_limpa, loja.id)) == antes

    definir_permissao_gastos(sessao_limpa, func.id, False, autor_dona)
    assert func.pode_aprovar_gastos is False
    with pytest.raises(DadosInvalidos, match="dona sempre"):
        definir_permissao_gastos(sessao_limpa, dona.id, False, autor_dona)
