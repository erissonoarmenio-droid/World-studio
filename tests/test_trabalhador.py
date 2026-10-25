"""Tarefa 10: o trabalhador."""

import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.nucleo.consentimentos import registrar_aceite
from app.nucleo.db import sessao
from app.nucleo.erros import DadosInvalidos
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos
from app.nucleo.fila import enfileirar
from app.nucleo.fila.trabalhador import (
    EXECUTORES,
    Resultado,
    Trabalhador,
    concluir,
    devolver_travados,
    espera,
    falhar,
    limpar_erro,
    pegar_proximo,
    rodar_uma_vez,
    sinal_de_vida,
)
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import Loja, Trabalho

# Depois de "agora": os trabalhos criados no teste já estão liberados nesse horário.
T0 = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)


def nova_loja(s, nome="Bella"):
    loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
    registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
    return loja


def por(s, loja, chave, tipo="teste", dados=None):
    t, _ = enfileirar(
        s, loja_id=loja.id, tipo=tipo, dados=dados or {}, chave_unica=f"t-{chave}", autor=SISTEMA
    )
    return t


@pytest.fixture
def loja_comitada():
    """Loja gravada de verdade (para testes com várias conexões); apagada no fim."""
    with sessao() as s:
        loja_id = nova_loja(s, "Trabalhador").id
    yield loja_id
    with sessao() as s:
        s.delete(s.get(Loja, loja_id))


# --- operações ---------------------------------------------------------------


def test_pegar_marca_rodando_e_trava(sessao_limpa):
    loja = nova_loja(sessao_limpa)
    t = por(sessao_limpa, loja, "p1")
    pego = pegar_proximo(sessao_limpa, ["teste"], T0 + timedelta(days=1))
    assert pego is t
    assert t.estado == "rodando" and t.tentativas == 1
    assert t.travado_ate == T0 + timedelta(days=1, minutes=15)
    assert pegar_proximo(sessao_limpa, ["teste"], T0 + timedelta(days=1)) is None


def test_so_pega_tipos_com_executor_e_ja_liberados(sessao_limpa):
    loja = nova_loja(sessao_limpa)
    por(sessao_limpa, loja, "v1", tipo="video")
    assert pegar_proximo(sessao_limpa, ["teste"]) is None
    assert pegar_proximo(sessao_limpa, []) is None
    t = por(sessao_limpa, loja, "t1")
    t.proximo_horario = datetime.now(UTC) + timedelta(minutes=5)
    sessao_limpa.flush()
    assert pegar_proximo(sessao_limpa, ["teste"]) is None  # ainda não é a hora


def test_concluir_guarda_resultado_e_custo(sessao_limpa):
    loja = nova_loja(sessao_limpa)
    t = por(sessao_limpa, loja, "c1")
    pegar_proximo(sessao_limpa, ["teste"])
    concluir(sessao_limpa, t.id, Resultado({"url": "r2://x"}, Decimal("0.081")))
    assert t.estado == "concluido" and t.custo_real == Decimal("0.081")
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "trabalho_concluido" and ultimo.custo == Decimal("0.081")
    with pytest.raises(DadosInvalidos):
        concluir(sessao_limpa, t.id, Resultado({}))  # já concluído


def test_falha_tenta_ate_3_vezes_com_espera_crescente(sessao_limpa):
    loja = nova_loja(sessao_limpa)
    t = por(sessao_limpa, loja, "f1")
    agora = T0 + timedelta(days=1)
    for tentativa in (1, 2):
        assert pegar_proximo(sessao_limpa, ["teste"], agora) is t
        falhar(sessao_limpa, t.id, "fornecedor fora", agora)
        assert t.estado == "na_fila" and t.tentativas == tentativa
        assert t.proximo_horario == agora + espera(tentativa)
        assert pegar_proximo(sessao_limpa, ["teste"], agora) is None  # esperando
        agora = t.proximo_horario
    pegar_proximo(sessao_limpa, ["teste"], agora)
    falhar(sessao_limpa, t.id, "fornecedor fora", agora)
    assert t.estado == "falhou" and t.tentativas == 3

    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert acoes.count("trabalho_retentativa") == 2 and acoes[-1] == "trabalho_falhou"
    assert espera(1) == timedelta(seconds=30) and espera(2) == timedelta(minutes=2)


def test_travado_ha_15_min_volta_para_a_fila(sessao_limpa):
    loja = nova_loja(sessao_limpa)
    t = por(sessao_limpa, loja, "tr1")
    pegar_proximo(sessao_limpa, ["teste"], T0)
    assert devolver_travados(sessao_limpa, T0 + timedelta(minutes=14)) == 0
    sinal_de_vida(sessao_limpa, t.id, T0 + timedelta(minutes=10))  # vídeo longo avisando
    assert devolver_travados(sessao_limpa, T0 + timedelta(minutes=20)) == 0
    assert devolver_travados(sessao_limpa, T0 + timedelta(minutes=26)) == 1
    assert t.estado == "na_fila" and "travado" in t.erro
    with pytest.raises(DadosInvalidos):
        sinal_de_vida(sessao_limpa, t.id)


def test_erro_nao_guarda_chave_de_api(sessao_limpa):
    assert "sk_839e" not in limpar_erro("401 com chave sk_839e31c8b4ab")
    assert "abc123" not in limpar_erro("GET /v1?key=abc123 falhou")
    assert "eyJhb" not in limpar_erro("Authorization: Bearer eyJhbGciOi")
    assert len(limpar_erro("x" * 5000)) == 2000


# --- com várias conexões de verdade ------------------------------------------


def test_dois_trabalhadores_nunca_pegam_o_mesmo(loja_comitada):
    with sessao() as s:
        loja = s.get(Loja, loja_comitada)
        for i in range(30):
            por(s, loja, f"conc-{i}")

    pegos: list[int] = []
    trava = threading.Lock()
    barreira = threading.Barrier(4)

    def trabalhador():
        barreira.wait()
        while True:
            with sessao() as s:
                t = pegar_proximo(s, ["teste"])
                if t is None:
                    return
                with trava:
                    pegos.append(t.id)

    threads = [threading.Thread(target=trabalhador) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(pegos) == 30 and len(set(pegos)) == 30


def test_rodar_uma_vez_conclui_e_falha(loja_comitada):
    with sessao() as s:
        loja = s.get(Loja, loja_comitada)
        ok_id = por(s, loja, "r-ok", dados={"eco": "oi"}).id
    assert rodar_uma_vez(EXECUTORES) is True
    with sessao() as s:
        t = s.get(Trabalho, ok_id)
        assert t.estado == "concluido" and t.resultado == {"ok": True, "eco": "oi"}

    with sessao() as s:
        ruim_id = por(s, s.get(Loja, loja_comitada), "r-ruim", dados={"falhar": True}).id
    assert rodar_uma_vez(EXECUTORES) is True
    with sessao() as s:
        t = s.get(Trabalho, ruim_id)
        assert t.estado == "na_fila" and t.tentativas == 1 and "falha de teste" in t.erro
    assert rodar_uma_vez(EXECUTORES) is False  # o que falhou espera 30 s


def test_thread_do_trabalhador_e_saude(loja_comitada, monkeypatch):
    monkeypatch.setenv("TRABALHADOR_ATIVO", "true")
    from app.config import obter_config
    from app.ferramentas.teste_fila import main as teste_fila
    from app.main import criar_app

    obter_config.cache_clear()
    try:
        with TestClient(criar_app()) as cliente:  # o 'with' liga o trabalhador
            resposta = cliente.get("/saude").json()
            assert resposta["componentes"]["fila"] == "ok"
            assert teste_fila(espera_max=20) == 0  # o mesmo roteiro da Parada C
    finally:
        monkeypatch.setenv("TRABALHADOR_ATIVO", "false")
        obter_config.cache_clear()


def test_saude_com_trabalhador_parado(monkeypatch):
    monkeypatch.setenv("TRABALHADOR_ATIVO", "true")
    from app.config import obter_config
    from app.main import criar_app
    from app.nucleo.fila import trabalhador as mod

    monkeypatch.setattr(mod.Trabalhador, "iniciar", lambda self: None)  # nunca liga
    obter_config.cache_clear()
    try:
        with TestClient(criar_app()) as cliente:
            r = cliente.get("/saude")
            assert r.status_code == 503 and r.json()["componentes"]["fila"] == "fora"
    finally:
        monkeypatch.setenv("TRABALHADOR_ATIVO", "false")
        obter_config.cache_clear()


def test_laco_sobrevive_a_erro_e_para(monkeypatch):
    from app.nucleo.fila import trabalhador as mod

    chamadas = []

    def ciclo_quebrado(_):
        chamadas.append(1)
        raise RuntimeError("banco fora")

    monkeypatch.setattr(mod, "rodar_uma_vez", ciclo_quebrado)
    t = Trabalhador({}, pausa=0.01)
    t.iniciar()
    threading.Event().wait(0.1)
    assert t.vivo() and len(chamadas) > 1  # continuou tentando
    t.parar()
    assert not t.vivo()
