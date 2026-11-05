"""Passo 1.2: pedidos pela porta única (créditos + fila) e a API interna."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app import pedidos
from app.creditos import servico as cr
from app.nucleo.consentimentos import registrar_aceite
from app.nucleo.db import sessao
from app.nucleo.erros import SemConsentimento, SemCreditos
from app.nucleo.eventos import ERI, Autor
from app.nucleo.fila.trabalhador import Resultado, concluir, falhar, pegar_proximo
from app.nucleo.lojas import criar_loja_com_dona

CHAVE = "chave-de-teste-123"


def loja_pronta(s, nome="Bella", termos=True, plano="estudio"):
    loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
    if termos:
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
    if plano:
        cr.ativar_plano(s, loja.id, plano, f"mp-{nome}-{loja.id}")
    return loja


def pedir(s, loja, chave="ped-1", item="foto", **extra):
    return pedidos.criar_pedido(
        s, loja_id=loja.id, item=item, dados={"peca": "4471"}, chave_unica=chave, **extra
    )


# --- serviço ----------------------------------------------------------------------------------


def test_pedido_reserva_e_enfileira_uma_vez_so(sessao_limpa):
    loja = loja_pronta(sessao_limpa)
    situacao, criado = pedir(sessao_limpa, loja)
    assert criado and situacao.estado == "na_fila" and situacao.credito == "reservada"
    assert situacao.creditos == 2
    de_novo, criado = pedir(sessao_limpa, loja)
    assert not criado and de_novo.chave_unica == "ped-1"
    assert cr.saldo(sessao_limpa, loja.id).disponivel == 73


def test_sem_termos_nao_reserva_nada(sessao_limpa):
    loja = loja_pronta(sessao_limpa, termos=False)
    with pytest.raises(SemConsentimento):
        pedir(sessao_limpa, loja)
    assert cr.saldo(sessao_limpa, loja.id).disponivel == 75


def test_sem_saldo_nao_enfileira(sessao_limpa):
    loja = loja_pronta(sessao_limpa)
    for i in range(5):
        pedir(sessao_limpa, loja, chave=f"vid-{i}", item="video_480")
    with pytest.raises(SemCreditos):
        pedir(sessao_limpa, loja, chave="vid-5", item="video_480")


def test_pronto_desconta_de_vez_com_custo_real(sessao_limpa):
    loja = loja_pronta(sessao_limpa)
    pedir(sessao_limpa, loja, item="video_480")
    trabalho = pegar_proximo(sessao_limpa, ["video"])
    assert trabalho.dados["item"] == "video_480" and trabalho.fornecedor == "tein"
    concluir(sessao_limpa, trabalho.id, Resultado({"video": "r2://x.mp4"}, Decimal("2.05")))
    s = pedidos.obter_pedido(sessao_limpa, "ped-1")
    assert (s.estado, s.credito, s.custo_real) == ("pronto", "debitada", Decimal("2.05"))
    assert s.resultado == {"video": "r2://x.mp4"}
    assert cr.saldo(sessao_limpa, loja.id).disponivel == 60


def test_falhou_3_vezes_devolve_os_creditos(sessao_limpa):
    loja = loja_pronta(sessao_limpa)
    pedir(sessao_limpa, loja, item="video_480")
    agora = datetime.now(UTC)
    for tentativa in range(3):
        trabalho = pegar_proximo(sessao_limpa, ["video"], agora=agora + timedelta(hours=tentativa))
        falhar(
            sessao_limpa, trabalho.id, "fornecedor fora", agora=agora + timedelta(hours=tentativa)
        )
    s = pedidos.obter_pedido(sessao_limpa, "ped-1")
    assert (s.estado, s.credito) == ("falhou", "estornada")
    assert cr.saldo(sessao_limpa, loja.id).disponivel == 75


# --- API interna ------------------------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch):
    from app.config import obter_config
    from app.main import criar_app

    monkeypatch.setattr(obter_config(), "chave_interna", SecretStr(CHAVE))
    return TestClient(criar_app())


def test_sem_chave_ou_chave_errada_e_recusado(cliente, monkeypatch):
    assert cliente.get("/interno/lojas/1/saldo").status_code == 401
    assert (
        cliente.get("/interno/lojas/1/saldo", headers={"X-Chave-Interna": "x"}).status_code == 401
    )
    from app.config import obter_config

    monkeypatch.setattr(obter_config(), "chave_interna", None)
    resposta = cliente.get("/interno/lojas/1/saldo", headers={"X-Chave-Interna": CHAVE})
    assert resposta.status_code == 503


def test_api_interna_ponta_a_ponta(cliente):
    h = {"X-Chave-Interna": CHAVE}
    with sessao() as s:
        loja = loja_pronta(s, nome="API Loja", plano=None)
        loja_id = loja.id

    assert cliente.get(f"/interno/lojas/{loja_id}/saldo", headers=h).json()["situacao"] == (
        "sem plano"
    )
    r = cliente.post(
        f"/interno/lojas/{loja_id}/plano",
        headers=h,
        json={"plano": "social_media", "referencia": f"manual-{loja_id}"},
    )
    assert r.status_code == 200 and r.json()["disponivel"] == 180

    novo = {"loja_id": loja_id, "item": "foto", "chave_unica": f"api-{loja_id}-1"}
    r = cliente.post("/interno/pedidos", headers=h, json=novo)
    assert r.status_code == 201 and r.json()["creditos"] == 2
    assert cliente.post("/interno/pedidos", headers=h, json=novo).status_code == 200
    r = cliente.get(f"/interno/pedidos/{novo['chave_unica']}", headers=h)
    assert r.json()["estado"] == "na_fila"

    r = cliente.post(
        f"/interno/lojas/{loja_id}/creditos", headers=h, json={"creditos": -500, "motivo": "teste"}
    )
    assert r.status_code == 402 and r.json()["faltam"] > 0

    assert cliente.post(f"/interno/lojas/{loja_id}/pausar", headers=h, json={}).status_code == 200
    r = cliente.post(
        "/interno/pedidos", headers=h, json={**novo, "chave_unica": f"api-{loja_id}-2"}
    )
    assert r.status_code == 403 and "pausada" in r.json()["motivo"]
    assert cliente.post(f"/interno/lojas/{loja_id}/retomar", headers=h).json()["situacao"] == (
        "ativa"
    )
    r = cliente.post("/interno/pedidos", headers=h, json={**novo, "item": "video_480"})
    assert r.status_code == 409  # mesma chave usada para outra coisa
