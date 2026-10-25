"""Tarefa 4: lojas, pessoas e registro de eventos."""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos, registrar_evento
from app.nucleo.lojas import criar_loja_com_dona, editar_loja, obter_loja
from app.nucleo.pessoas import (
    adicionar_pessoa,
    editar_pessoa,
    obter_pessoa,
    obter_pessoa_por_telegram,
)

LOJA = {
    "nome": "Bella Moda",
    "instagram": "@Bella.Moda",
    "segmento": "moda feminina",
    "cidade": "Goiânia",
    "uf": "go",
    "canais_venda": ["loja física", " Instagram ", ""],
}
DONA = {"nome": "Ana Souza", "telegram_id": 111, "whatsapp": "(62) 99999-0000"}


def criar(sessao, **extra):
    return criar_loja_com_dona(sessao, {**LOJA, **extra}, DONA, ERI)


# --- criar e ler -------------------------------------------------------------


def test_criar_loja_com_dona_registra_dois_eventos(sessao_limpa):
    loja, dona = criar(sessao_limpa)

    assert loja.instagram == "bella.moda"  # sem @ e minúsculo
    assert loja.uf == "GO"
    assert loja.canais_venda == ["loja física", "Instagram"]
    assert dona.papel == "dona" and dona.pode_aprovar_gastos is True
    assert dona.whatsapp == "62999990000"

    eventos = listar_eventos(sessao_limpa, loja.id)
    assert [e.acao for e in eventos] == ["loja_criada", "pessoa_criada"]
    assert all(e.quem == "eri" for e in eventos)
    assert obter_loja(sessao_limpa, loja.id) is loja


def test_evento_nao_guarda_dado_pessoal(sessao_limpa):
    loja, dona = criar(sessao_limpa)
    editar_pessoa(sessao_limpa, dona.id, {"email": "Ana@Loja.com"}, Autor("pessoa", dona.id))
    for evento in listar_eventos(sessao_limpa, loja.id):
        texto = str(evento.detalhes)
        assert "Ana" not in texto and "999" not in texto and "@" not in texto


def test_buscar_por_telegram(sessao_limpa):
    _, dona = criar(sessao_limpa)
    assert obter_pessoa_por_telegram(sessao_limpa, 111) is dona
    assert obter_pessoa_por_telegram(sessao_limpa, 999) is None


# --- regras de unicidade -----------------------------------------------------


def test_telegram_e_unico(sessao_limpa):
    criar(sessao_limpa)
    with pytest.raises(Conflito, match="Telegram"):
        criar_loja_com_dona(
            sessao_limpa, {"nome": "Outra"}, {"nome": "Bia", "telegram_id": 111}, ERI
        )


def test_telegram_unico_tambem_no_banco(sessao_limpa):
    """Mesmo se alguém passar por fora das funções, o banco recusa."""
    loja, _ = criar(sessao_limpa)
    with pytest.raises(IntegrityError, match="uq_pessoas_telegram_id"):
        sessao_limpa.execute(
            text(
                "INSERT INTO pessoas (loja_id, nome, papel, telegram_id) "
                "VALUES (:l, 'X', 'socia', 111)"
            ),
            {"l": loja.id},
        )


def test_uma_dona_por_loja(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    with pytest.raises(Conflito, match="dona"):
        adicionar_pessoa(sessao_limpa, loja.id, {"nome": "Outra Dona"}, ERI)


def test_instagram_unico(sessao_limpa):
    criar(sessao_limpa)
    with pytest.raises(Conflito, match="Instagram"):
        criar_loja_com_dona(
            sessao_limpa, {"nome": "Cópia", "instagram": "bella.moda"}, {"nome": "Bia"}, ERI
        )


def test_primeira_pessoa_precisa_ser_dona(sessao_limpa):
    with pytest.raises(DadosInvalidos, match="dona"):
        criar_loja_com_dona(sessao_limpa, LOJA, {"nome": "Bia", "papel": "funcionaria"}, ERI)


# --- validação ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("loja", "trecho"),
    [
        ({"nome": "A"}, "nome"),
        ({"nome": "Loja", "uf": "XX"}, "UF"),
        ({"nome": "Loja", "instagram": "tem espaço"}, "Instagram"),
        ({"nome": "Loja", "campo_estranho": 1}, "campo_estranho"),
        ({"nome": "Loja", "canais_venda": ["x" * 41]}, "canal"),
    ],
)
def test_loja_invalida_e_recusada_com_motivo(sessao_limpa, loja, trecho):
    with pytest.raises(DadosInvalidos, match=trecho):
        criar_loja_com_dona(sessao_limpa, loja, DONA, ERI)


@pytest.mark.parametrize(
    ("pessoa", "trecho"),
    [
        ({"nome": "Bia", "whatsapp": "123"}, "WhatsApp"),
        ({"nome": "Bia", "email": "sem-arroba"}, "e-mail"),
        ({"nome": "Bia", "telegram_id": -5}, "telegram_id"),
        ({"nome": "Bia", "papel": "chefe"}, "papel"),
    ],
)
def test_pessoa_invalida_e_recusada_com_motivo(sessao_limpa, pessoa, trecho):
    loja, _ = criar(sessao_limpa)
    with pytest.raises(DadosInvalidos, match=trecho):
        adicionar_pessoa(sessao_limpa, loja.id, {"papel": "socia", **pessoa}, ERI)


# --- edição ------------------------------------------------------------------


def test_editar_loja_registra_so_campos_mudados(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    editar_loja(sessao_limpa, loja.id, {"cidade": "Anápolis", "uf": "GO"}, ERI)  # UF igual
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "loja_editada"
    assert ultimo.detalhes == {"campos": ["cidade"]}
    assert loja.cidade == "Anápolis"


def test_editar_sem_mudanca_nao_gera_evento(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    antes = len(listar_eventos(sessao_limpa, loja.id))
    editar_loja(sessao_limpa, loja.id, {"cidade": "Goiânia"}, ERI)
    assert len(listar_eventos(sessao_limpa, loja.id)) == antes


def test_editar_loja_recusa_campos_protegidos_e_vazios(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    with pytest.raises(DadosInvalidos, match="plano"):
        editar_loja(sessao_limpa, loja.id, {"plano": "social_media"}, ERI)
    with pytest.raises(DadosInvalidos, match="nome"):
        editar_loja(sessao_limpa, loja.id, {"nome": None}, ERI)


def test_editar_loja_limpa_canais_e_confere_instagram(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    criar_loja_com_dona(sessao_limpa, {"nome": "Outra", "instagram": "outra"}, {"nome": "Bia"}, ERI)
    editar_loja(sessao_limpa, loja.id, {"canais_venda": None}, ERI)
    assert loja.canais_venda == []
    with pytest.raises(Conflito):
        editar_loja(sessao_limpa, loja.id, {"instagram": "@outra"}, ERI)


def test_funcionaria_nao_ganha_permissao_por_edicao(sessao_limpa):
    loja, _ = criar(sessao_limpa)
    func = adicionar_pessoa(sessao_limpa, loja.id, {"nome": "Bia", "papel": "funcionaria"}, ERI)
    assert func.pode_aprovar_gastos is False
    autor = Autor("pessoa", func.id)
    for proibido in ({"pode_aprovar_gastos": True}, {"papel": "dona"}):
        with pytest.raises(DadosInvalidos, match="não pode ser mudado"):
            editar_pessoa(sessao_limpa, func.id, proibido, autor)
    assert func.pode_aprovar_gastos is False and func.papel == "funcionaria"


def test_editar_pessoa_confere_telegram_e_nome(sessao_limpa):
    loja, dona = criar(sessao_limpa)
    socia = adicionar_pessoa(
        sessao_limpa, loja.id, {"nome": "Bia", "papel": "socia", "telegram_id": 222}, ERI
    )
    with pytest.raises(Conflito):
        editar_pessoa(sessao_limpa, socia.id, {"telegram_id": 111}, ERI)
    editar_pessoa(sessao_limpa, dona.id, {"telegram_id": 111}, ERI)  # o próprio número: ok
    with pytest.raises(DadosInvalidos, match="nome"):
        editar_pessoa(sessao_limpa, socia.id, {"nome": None}, ERI)
    editar_pessoa(sessao_limpa, socia.id, {"nome": "Beatriz"}, ERI)
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.detalhes == {"pessoa_id": socia.id, "campos": ["nome"]}


def test_nao_encontrado(sessao_limpa):
    with pytest.raises(NaoEncontrado):
        obter_loja(sessao_limpa, 999_999)
    with pytest.raises(NaoEncontrado):
        obter_pessoa(sessao_limpa, 999_999)
    with pytest.raises(NaoEncontrado):
        adicionar_pessoa(sessao_limpa, 999_999, {"nome": "Bia", "papel": "socia"}, ERI)


# --- registro de eventos -----------------------------------------------------


def test_evento_com_custo_e_autor_invalido(sessao_limpa):
    evento = registrar_evento(sessao_limpa, acao="teste", custo=Decimal("0.0810"))
    assert evento.quem == "sistema" and evento.custo == Decimal("0.0810")
    with pytest.raises(DadosInvalidos):
        registrar_evento(sessao_limpa, acao="teste", custo=Decimal("-1"))
    with pytest.raises(DadosInvalidos):
        registrar_evento(sessao_limpa, acao="", autor=SISTEMA)
    with pytest.raises(DadosInvalidos):
        Autor("hacker")
    with pytest.raises(DadosInvalidos):
        Autor("pessoa")  # sem pessoa_id
    with pytest.raises(DadosInvalidos):
        Autor("eri", pessoa_id=1)


def test_banco_recusa_editar_evento(sessao_limpa):
    evento = registrar_evento(sessao_limpa, acao="original")
    with pytest.raises(DBAPIError, match="nao podem ser editados"):
        sessao_limpa.execute(
            text("UPDATE eventos SET acao = 'adulterado' WHERE id = :i"), {"i": evento.id}
        )


def test_apagar_loja_mantem_eventos_sem_loja(sessao_limpa):
    """Base para a LGPD (tarefa 12): o banco pode soltar a loja do evento, e só isso."""
    loja, _ = criar(sessao_limpa)
    ids = [e.id for e in listar_eventos(sessao_limpa, loja.id)]
    sessao_limpa.execute(text("DELETE FROM lojas WHERE id = :i"), {"i": loja.id})
    restantes = sessao_limpa.execute(
        text("SELECT loja_id FROM eventos WHERE id = ANY(:ids)"), {"ids": ids}
    ).scalars()
    assert list(restantes) == [None, None]
