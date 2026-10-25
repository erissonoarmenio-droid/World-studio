"""Tarefa 8: palavra-senha da dona (força bruta simulada)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.nucleo.erros import (
    Conflito,
    DadosInvalidos,
    NaoEncontrado,
    PalavraBloqueada,
    PalavraNecessaria,
    SemPermissao,
)
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.pessoas import adicionar_pessoa
from app.nucleo.senha import (
    apagar_mensagem_da_palavra,
    conferir_palavra,
    criar_palavra,
    exigir_palavra,
    fechar_janela,
    janela_aberta,
    liberar_troca,
)

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
PALAVRA = "girassol amarelo"


@pytest.fixture
def cenario(sessao_limpa):
    loja, dona = criar_loja_com_dona(sessao_limpa, {"nome": "Bella"}, {"nome": "Ana"}, ERI)
    func = adicionar_pessoa(sessao_limpa, loja.id, {"nome": "Bia", "papel": "funcionaria"}, ERI)
    return loja, dona, func


def eu(p):
    return Autor("pessoa", p.id)


def test_palavra_so_existe_embaralhada(sessao_limpa, cenario):
    loja, dona, _ = cenario
    registro = criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), dica="flor", agora=T0)
    assert registro.hash.startswith("$argon2id$")
    assert "girassol" not in registro.hash
    linha = sessao_limpa.execute(text("SELECT row_to_json(p)::text FROM palavra_senha p")).scalar()
    assert "girassol" not in linha
    for evento in listar_eventos(sessao_limpa, loja.id):
        assert "girassol" not in str(evento.detalhes)


def test_certa_abre_janela_de_30_min(sessao_limpa, cenario):
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    with pytest.raises(PalavraNecessaria):
        exigir_palavra(sessao_limpa, dona.id, T0)

    # Teclado do celular põe maiúscula e espaço a mais: continua valendo.
    assert conferir_palavra(sessao_limpa, dona.id, "  Girassol   Amarelo ", T0) is True
    exigir_palavra(sessao_limpa, dona.id, T0 + timedelta(minutes=29))
    with pytest.raises(PalavraNecessaria):
        exigir_palavra(sessao_limpa, dona.id, T0 + timedelta(minutes=30))

    conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0)
    fechar_janela(sessao_limpa, dona.id)
    assert janela_aberta(sessao_limpa, dona.id, T0) is False


def test_cinco_erros_bloqueiam_15_min(sessao_limpa, cenario):
    loja, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    for i in range(4):
        assert conferir_palavra(sessao_limpa, dona.id, f"chute{i}", T0) is False
    assert conferir_palavra(sessao_limpa, dona.id, "chute4", T0) is False  # 5º erro

    # Bloqueada: nem a palavra certa passa.
    with pytest.raises(PalavraBloqueada, match="15 min"):
        conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0 + timedelta(seconds=1))
    with pytest.raises(PalavraBloqueada):
        conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0 + timedelta(minutes=14, seconds=59))
    assert conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0 + timedelta(minutes=15)) is True

    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert acoes.count("palavra_errada") == 4
    assert acoes.count("palavra_bloqueada") == 1


def test_forca_bruta_nao_passa_de_5_tentativas_a_cada_15_min(sessao_limpa, cenario):
    """Simulação: um atacante tentando sem parar durante 1 hora."""
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    conferidas = 0
    agora = T0
    while agora < T0 + timedelta(hours=1):
        try:
            conferir_palavra(sessao_limpa, dona.id, f"chute{conferidas}", agora)
            conferidas += 1
        except PalavraBloqueada:
            pass
        agora += timedelta(seconds=30)
    assert conferidas <= 5 * 4  # no máximo 5 por janela de 15 minutos


def test_acerto_zera_os_erros(sessao_limpa, cenario):
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    for _ in range(4):
        conferir_palavra(sessao_limpa, dona.id, "errada", T0)
    conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0)
    for _ in range(4):
        conferir_palavra(sessao_limpa, dona.id, "errada", T0)
    assert conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0) is True  # não bloqueou


def test_erro_fecha_janela_aberta(sessao_limpa, cenario):
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0)
    conferir_palavra(sessao_limpa, dona.id, "errada", T0)
    assert janela_aberta(sessao_limpa, dona.id, T0) is False


def test_funcionaria_nao_cria_nem_usa(sessao_limpa, cenario):
    _, dona, func = cenario
    with pytest.raises(SemPermissao, match="só a dona"):
        criar_palavra(sessao_limpa, func.id, PALAVRA, eu(func))
    with pytest.raises(SemPermissao):
        exigir_palavra(sessao_limpa, func.id)
    # Ninguém cria pela dona, nem o Eri.
    for autor in (eu(func), ERI, SISTEMA):
        with pytest.raises(SemPermissao, match="própria dona"):
            criar_palavra(sessao_limpa, dona.id, PALAVRA, autor)


def test_nao_cria_duas_vezes_sem_liberacao(sessao_limpa, cenario):
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    with pytest.raises(Conflito, match="Eri precisa liberar"):
        criar_palavra(sessao_limpa, dona.id, "outra palavra", eu(dona), agora=T0)


def test_troca_liberada_pelo_eri(sessao_limpa, cenario):
    loja, dona, func = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    for i in range(5):
        conferir_palavra(sessao_limpa, dona.id, f"x{i}", T0)  # bloqueou

    for autor in (eu(dona), eu(func), SISTEMA):
        with pytest.raises(SemPermissao, match="só o Eri"):
            liberar_troca(sessao_limpa, dona.id, autor, T0)
    liberar_troca(sessao_limpa, dona.id, ERI, T0)

    # A liberação vale 24 h.
    criar_palavra(sessao_limpa, dona.id, "nova palavra", eu(dona), agora=T0 + timedelta(hours=1))
    assert conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0 + timedelta(hours=1)) is False
    assert conferir_palavra(sessao_limpa, dona.id, "nova palavra", T0 + timedelta(hours=1))
    # Usada a liberação, não dá para trocar de novo.
    with pytest.raises(Conflito):
        criar_palavra(sessao_limpa, dona.id, "terceira", eu(dona), agora=T0 + timedelta(hours=2))

    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert "troca_palavra_liberada" in acoes and "palavra_trocada" in acoes


def test_liberacao_vencida(sessao_limpa, cenario):
    _, dona, _ = cenario
    criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    liberar_troca(sessao_limpa, dona.id, ERI, T0)
    with pytest.raises(Conflito):
        criar_palavra(sessao_limpa, dona.id, "nova", eu(dona), agora=T0 + timedelta(hours=24))


@pytest.mark.parametrize(
    ("palavra", "dica", "trecho"),
    [
        ("abc", None, "de 4 a 64"),
        ("x" * 65, None, "de 4 a 64"),
        ("girassol", "é girassol", "dica"),
        ("girassol", "x" * 101, "dica"),
    ],
)
def test_palavra_ou_dica_invalida(sessao_limpa, cenario, palavra, dica, trecho):
    _, dona, _ = cenario
    with pytest.raises(DadosInvalidos, match=trecho):
        criar_palavra(sessao_limpa, dona.id, palavra, eu(dona), dica=dica)


def test_sem_palavra_criada(sessao_limpa, cenario):
    _, dona, _ = cenario
    with pytest.raises(NaoEncontrado):
        conferir_palavra(sessao_limpa, dona.id, PALAVRA)
    with pytest.raises(NaoEncontrado):
        liberar_troca(sessao_limpa, dona.id, ERI)
    assert janela_aberta(sessao_limpa, dona.id) is False
    fechar_janela(sessao_limpa, dona.id)  # não quebra


def test_hash_corrompido_conta_como_erro(sessao_limpa, cenario):
    _, dona, _ = cenario
    registro = criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    registro.hash = "lixo"
    assert conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0) is False


def test_hash_antigo_e_atualizado_no_acerto(sessao_limpa, cenario):
    from argon2 import PasswordHasher

    _, dona, _ = cenario
    registro = criar_palavra(sessao_limpa, dona.id, PALAVRA, eu(dona), agora=T0)
    registro.hash = PasswordHasher(time_cost=1, memory_cost=8192).hash(PALAVRA)
    antigo = registro.hash
    assert conferir_palavra(sessao_limpa, dona.id, PALAVRA, T0) is True
    assert registro.hash != antigo


def test_apagar_mensagem(sessao_limpa, cenario):
    loja, dona, _ = cenario
    apagadas = []
    assert apagar_mensagem_da_palavra(sessao_limpa, dona.id, lambda: apagadas.append(1))
    assert apagadas == [1]

    def falha():
        raise RuntimeError("message can't be deleted")

    assert apagar_mensagem_da_palavra(sessao_limpa, dona.id, falha) is False
    assert listar_eventos(sessao_limpa, loja.id)[-1].acao == "mensagem_palavra_nao_apagada"
