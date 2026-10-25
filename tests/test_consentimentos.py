"""Tarefa 6: consentimentos com versão."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.nucleo.consentimentos import (
    consentimento_ativo,
    exigir_termos_aceitos,
    historico,
    registrar_aceite,
    revogar,
)
from app.nucleo.erros import DadosInvalidos, NaoEncontrado, SemConsentimento, SemPermissao
from app.nucleo.eventos import ERI, Autor, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.pessoas import adicionar_pessoa

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def cenario(sessao_limpa):
    loja, dona = criar_loja_com_dona(sessao_limpa, {"nome": "Bella"}, {"nome": "Ana"}, ERI)
    func = adicionar_pessoa(sessao_limpa, loja.id, {"nome": "Bia", "papel": "funcionaria"}, ERI)
    return loja, dona, func


def eu(pessoa):
    return Autor("pessoa", pessoa.id)


def test_sem_termos_a_loja_e_recusada(sessao_limpa, cenario):
    loja, dona, _ = cenario
    with pytest.raises(SemConsentimento, match="termos"):
        exigir_termos_aceitos(sessao_limpa, loja.id)
    registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona), agora=T0)
    exigir_termos_aceitos(sessao_limpa, loja.id)  # agora passa


def test_termos_so_da_funcionaria_nao_bastam(sessao_limpa, cenario):
    loja, _, func = cenario
    registrar_aceite(sessao_limpa, func.id, "termos_privacidade", "v1", eu(func), agora=T0)
    with pytest.raises(SemConsentimento):
        exigir_termos_aceitos(sessao_limpa, loja.id)


def test_revogar_guarda_historico(sessao_limpa, cenario):
    loja, dona, _ = cenario
    registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona), agora=T0)
    revogado = revogar(sessao_limpa, dona.id, "termos_privacidade", eu(dona), T0 + timedelta(1))

    assert revogado.revogado_em == T0 + timedelta(1)
    assert len(historico(sessao_limpa, dona.id)) == 1  # não apagou
    assert consentimento_ativo(sessao_limpa, dona.id, "termos_privacidade") is None
    with pytest.raises(SemConsentimento):
        exigir_termos_aceitos(sessao_limpa, loja.id)
    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert acoes[-2:] == ["consentimento_aceito", "consentimento_revogado"]


def test_versao_nova_substitui_a_anterior(sessao_limpa, cenario):
    _, dona, _ = cenario
    v1 = registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona), agora=T0)
    mesmo = registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona))
    assert mesmo is v1  # aceitar de novo a mesma versão não duplica

    t1 = T0 + timedelta(days=30)
    v2 = registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", " v2 ", eu(dona), agora=t1)
    assert v1.revogado_em == t1 and v2.revogado_em is None and v2.versao == "v2"
    assert [c.versao for c in historico(sessao_limpa, dona.id)] == ["v1", "v2"]


def test_modo_automatico_guarda_o_limite(sessao_limpa, cenario):
    _, dona, _ = cenario
    c = registrar_aceite(
        sessao_limpa,
        dona.id,
        "modo_automatico",
        "v1",
        eu(dona),
        detalhes={"limite_creditos": 40, "periodo": "semana"},
        agora=T0,
    )
    assert c.detalhes["limite_creditos"] == 40
    # Mudar o limite gera um aceite novo (o antigo fica no histórico).
    novo = registrar_aceite(
        sessao_limpa, dona.id, "modo_automatico", "v1", eu(dona), detalhes={"limite_creditos": 60}
    )
    assert novo is not c and c.revogado_em is not None


def test_aceites_da_loja_so_pela_dona(sessao_limpa, cenario):
    _, _, func = cenario
    for tipo in ("modo_automatico", "instagram", "whatsapp", "ordem_fixa", "dados_agregados"):
        with pytest.raises(SemPermissao, match="só a dona"):
            registrar_aceite(sessao_limpa, func.id, tipo, "v1", eu(func), agora=T0)
    # Os pessoais, a funcionária dá por si.
    registrar_aceite(sessao_limpa, func.id, "clone", "v1", eu(func), agora=T0)


def test_ninguem_aceita_por_outra_pessoa(sessao_limpa, cenario):
    _, dona, func = cenario
    for autor in (eu(func), ERI, Autor("sistema")):
        with pytest.raises(SemPermissao, match="própria pessoa"):
            registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", autor, agora=T0)
    registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona), agora=T0)
    with pytest.raises(SemPermissao):
        revogar(sessao_limpa, dona.id, "termos_privacidade", ERI)


def test_entradas_invalidas(sessao_limpa, cenario):
    _, dona, _ = cenario
    with pytest.raises(DadosInvalidos, match="desconhecido"):
        registrar_aceite(sessao_limpa, dona.id, "vender_dados", "v1", eu(dona))
    with pytest.raises(DadosInvalidos, match="versão"):
        registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "  ", eu(dona))
    with pytest.raises(NaoEncontrado):
        revogar(sessao_limpa, dona.id, "clone", eu(dona))


def test_banco_garante_um_ativo_por_tipo(sessao_limpa, cenario):
    loja, dona, _ = cenario
    registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", eu(dona), agora=T0)
    with pytest.raises(IntegrityError, match="uq_consentimentos_um_ativo"):
        sessao_limpa.execute(
            text(
                "INSERT INTO consentimentos (pessoa_id, loja_id, tipo, versao, aceito_em) "
                "VALUES (:p, :l, 'termos_privacidade', 'v9', now())"
            ),
            {"p": dona.id, "l": loja.id},
        )
