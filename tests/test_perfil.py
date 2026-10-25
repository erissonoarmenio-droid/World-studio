"""Tarefa 7: perfil da loja e dados fiscais."""

from datetime import UTC, datetime

import pytest

from app.nucleo.erros import DadosInvalidos, NaoEncontrado, SemPermissao
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import PerfilLoja
from app.nucleo.perfil import atualizar_perfil, ler_perfil, registrar_fiscal, validar_documento
from app.nucleo.pessoas import adicionar_pessoa

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
CNPJ = "11.222.333/0001-81"  # exemplo válido clássico
CPF = "529.982.247-25"  # exemplo válido clássico


@pytest.fixture
def loja_dona(sessao_limpa):
    return criar_loja_com_dona(sessao_limpa, {"nome": "Bella"}, {"nome": "Ana"}, ERI)


# --- perfil ------------------------------------------------------------------


def test_cada_campo_guarda_origem_e_data(sessao_limpa, loja_dona):
    loja, _ = loja_dona
    atualizar_perfil(
        sessao_limpa,
        loja.id,
        {"marca.tom": "descontraído", "marca.cores": ["#ff6699", "#222222"]},
        "instagram",
        SISTEMA,
        T0,
    )
    atualizar_perfil(sessao_limpa, loja.id, {"influencer.nome": "Duda"}, "conversa", SISTEMA)

    perfil = sessao_limpa.get(PerfilLoja, loja.id)
    assert perfil.dados["marca.tom"] == {
        "valor": "descontraído",
        "origem": "instagram",
        "em": T0.isoformat(),
    }
    assert perfil.dados["influencer.nome"]["origem"] == "conversa"
    assert ler_perfil(sessao_limpa, loja.id) == {
        "marca": {"tom": "descontraído", "cores": ["#ff6699", "#222222"]},
        "influencer": {"nome": "Duda"},
    }


def test_eri_corrige_e_a_origem_muda(sessao_limpa, loja_dona):
    loja, _ = loja_dona
    atualizar_perfil(sessao_limpa, loja.id, {"marca.tom": "sério"}, "instagram", SISTEMA, T0)
    atualizar_perfil(sessao_limpa, loja.id, {"marca.tom": "leve"}, "eri", ERI)
    info = sessao_limpa.get(PerfilLoja, loja.id).dados["marca.tom"]
    assert info["valor"] == "leve" and info["origem"] == "eri"


def test_evento_tem_campo_e_origem_mas_nao_o_valor(sessao_limpa, loja_dona):
    loja, _ = loja_dona
    atualizar_perfil(
        sessao_limpa, loja.id, {"respostas.pix": "chave 62999990000"}, "conversa", SISTEMA
    )
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "perfil_atualizado"
    assert ultimo.detalhes == {"campos": ["respostas.pix"], "origem": "conversa"}
    assert "6299" not in str(ultimo.detalhes)


def test_sem_mudanca_nao_gera_evento_e_none_apaga(sessao_limpa, loja_dona):
    loja, _ = loja_dona
    atualizar_perfil(sessao_limpa, loja.id, {"marca.tom": "leve"}, "eri", ERI)
    antes = len(listar_eventos(sessao_limpa, loja.id))
    atualizar_perfil(sessao_limpa, loja.id, {"marca.tom": "leve"}, "eri", ERI)
    atualizar_perfil(sessao_limpa, loja.id, {"marca.nada": None}, "eri", ERI)  # já não existe
    assert len(listar_eventos(sessao_limpa, loja.id)) == antes

    atualizar_perfil(sessao_limpa, loja.id, {"marca.tom": None}, "eri", ERI)
    assert ler_perfil(sessao_limpa, loja.id) == {}
    assert listar_eventos(sessao_limpa, loja.id)[-1].detalhes["campos"] == ["marca.tom"]


@pytest.mark.parametrize(
    ("mudancas", "origem", "trecho"),
    [
        ({"senha.qualquer": "x"}, "eri", "campo de perfil inválido"),
        ({"marca": "x"}, "eri", "campo de perfil inválido"),
        ({"marca.Tom": "x"}, "eri", "campo de perfil inválido"),
        ({"marca.tom": "x"}, "telepatia", "origem"),
        ({"marca.tom": "x" * 5000}, "eri", "grande demais"),
        ({"marca.tom": {1, 2}}, "eri", "não pode ser guardado"),
        ({}, "eri", "nada"),
    ],
)
def test_perfil_recusa_entrada_invalida(sessao_limpa, loja_dona, mudancas, origem, trecho):
    loja, _ = loja_dona
    with pytest.raises(DadosInvalidos, match=trecho):
        atualizar_perfil(sessao_limpa, loja.id, mudancas, origem, ERI)


def test_perfil_de_loja_inexistente(sessao_limpa):
    with pytest.raises(NaoEncontrado):
        atualizar_perfil(sessao_limpa, 999_999, {"marca.tom": "x"}, "eri", ERI)
    assert ler_perfil(sessao_limpa, 999_999) == {}


# --- fiscal ------------------------------------------------------------------


def test_documentos_validos():
    assert validar_documento(CNPJ) == ("cnpj", "11222333000181")
    assert validar_documento(CPF) == ("cpf", "52998224725")


@pytest.mark.parametrize(
    "documento",
    ["11.222.333/0001-82", "529.982.247-24", "111.111.111-11", "00000000000000", "123", ""],
)
def test_documentos_invalidos(documento):
    with pytest.raises(DadosInvalidos, match="inválido"):
        validar_documento(documento)


def test_dona_registra_fiscal_e_evento_nao_tem_o_numero(sessao_limpa, loja_dona):
    loja, dona = loja_dona
    fiscal = registrar_fiscal(
        sessao_limpa, loja.id, CNPJ, Autor("pessoa", dona.id), razao_social=" Bella Moda Ltda "
    )
    assert fiscal.tipo == "cnpj" and fiscal.documento == "11222333000181"
    assert fiscal.razao_social == "Bella Moda Ltda" and fiscal.situacao is None
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "fiscal_registrado" and ultimo.detalhes == {"tipo": "cnpj"}

    # Trocar para CPF substitui o registro (um por loja).
    fiscal2 = registrar_fiscal(sessao_limpa, loja.id, CPF, ERI)
    assert fiscal2 is fiscal and fiscal.tipo == "cpf"


def test_so_dona_ou_eri_registram_fiscal(sessao_limpa, loja_dona):
    loja, _ = loja_dona
    func = adicionar_pessoa(sessao_limpa, loja.id, {"nome": "Bia", "papel": "funcionaria"}, ERI)
    for autor in (Autor("pessoa", func.id), SISTEMA):
        with pytest.raises(SemPermissao):
            registrar_fiscal(sessao_limpa, loja.id, CNPJ, autor)
    with pytest.raises(DadosInvalidos, match="razão social"):
        registrar_fiscal(sessao_limpa, loja.id, CNPJ, ERI, razao_social="X")
