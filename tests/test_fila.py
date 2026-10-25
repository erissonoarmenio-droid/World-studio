"""Tarefa 9: enfileirar sem gastar duas vezes."""

import threading
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.nucleo.consentimentos import registrar_aceite, revogar
from app.nucleo.db import sessao
from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado, SemConsentimento
from app.nucleo.eventos import ERI, SISTEMA, Autor, listar_eventos
from app.nucleo.fila import enfileirar, obter_trabalho
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import Loja, Trabalho


def nova_loja(s, nome="Bella", termos=True):
    loja, dona = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
    if termos:
        registrar_aceite(s, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
    return loja, dona


def pedir(s, loja, chave="loja:pedido1:foto", **extra):
    args = {"loja_id": loja.id, "tipo": "foto", "dados": {"peca": "4471"}, "chave_unica": chave}
    return enfileirar(s, autor=SISTEMA, **{**args, **extra})


def test_enfileirar_cria_trabalho_e_evento(sessao_limpa):
    loja, _ = nova_loja(sessao_limpa)
    trabalho, criado = pedir(
        sessao_limpa, loja, custo_estimado=Decimal("0.05"), fornecedor="google"
    )
    assert criado is True
    assert trabalho.estado == "na_fila" and trabalho.tentativas == 0
    assert trabalho.fornecedor == "google"
    ultimo = listar_eventos(sessao_limpa, loja.id)[-1]
    assert ultimo.acao == "trabalho_enfileirado"
    assert ultimo.detalhes["custo_estimado"] == "0.05"


def test_mesmo_pedido_duas_vezes_devolve_o_mesmo(sessao_limpa):
    loja, _ = nova_loja(sessao_limpa)
    primeiro, _ = pedir(sessao_limpa, loja)
    segundo, criado = pedir(sessao_limpa, loja)
    assert criado is False and segundo.id == primeiro.id
    total = sessao_limpa.scalar(select(func.count()).select_from(Trabalho))
    assert total == 1
    enfileirados = [
        e for e in listar_eventos(sessao_limpa, loja.id) if e.acao == "trabalho_enfileirado"
    ]
    assert len(enfileirados) == 1


def test_chave_de_outra_loja_e_recusada(sessao_limpa):
    loja1, _ = nova_loja(sessao_limpa, "Loja 1")
    loja2, _ = nova_loja(sessao_limpa, "Loja 2")
    pedir(sessao_limpa, loja1, chave="mesma-chave")
    with pytest.raises(Conflito):
        pedir(sessao_limpa, loja2, chave="mesma-chave")
    with pytest.raises(Conflito):
        pedir(sessao_limpa, loja1, chave="mesma-chave", tipo="video")


def test_sem_termos_e_recusado_com_motivo(sessao_limpa):
    loja, dona = nova_loja(sessao_limpa, termos=False)
    with pytest.raises(SemConsentimento, match="termos"):
        pedir(sessao_limpa, loja)
    registrar_aceite(sessao_limpa, dona.id, "termos_privacidade", "v1", Autor("pessoa", dona.id))
    pedir(sessao_limpa, loja)
    revogar(sessao_limpa, dona.id, "termos_privacidade", Autor("pessoa", dona.id))
    with pytest.raises(SemConsentimento):
        pedir(sessao_limpa, loja, chave="outro-pedido")


@pytest.mark.parametrize(
    ("extra", "trecho"),
    [
        ({"tipo": "bitcoin"}, "tipo"),
        ({"chave": "ab"}, "chave_unica"),
        ({"dados": ["lista"]}, "objeto"),
        ({"dados": {"x": {1, 2}}}, "não podem ser guardados"),
        ({"dados": {"x": "a" * 21_000}}, "grandes demais"),
        ({"custo_estimado": Decimal("-1")}, "negativo"),
    ],
)
def test_entradas_invalidas(sessao_limpa, extra, trecho):
    loja, _ = nova_loja(sessao_limpa)
    with pytest.raises(DadosInvalidos, match=trecho):
        pedir(sessao_limpa, loja, **extra)


def test_loja_nao_ve_trabalho_de_outra(sessao_limpa):
    loja1, _ = nova_loja(sessao_limpa, "Loja 1")
    loja2, _ = nova_loja(sessao_limpa, "Loja 2")
    trabalho, _ = pedir(sessao_limpa, loja1)
    assert obter_trabalho(sessao_limpa, trabalho.id, loja1.id) is trabalho
    with pytest.raises(NaoEncontrado):
        obter_trabalho(sessao_limpa, trabalho.id, loja2.id)
    with pytest.raises(NaoEncontrado):
        pedir(sessao_limpa, Loja(id=999_999))


def test_dois_pedidos_ao_mesmo_tempo_criam_um_so():
    """Concorrência de verdade: 8 conexões pedindo a mesma coisa juntas."""
    with sessao() as s:
        loja, _ = nova_loja(s, "Concorrência")
        loja_id = loja.id

    barreira = threading.Barrier(8)
    resultados, erros = [], []

    def pedir_em_paralelo():
        try:
            barreira.wait()
            with sessao() as s:
                t, criado = enfileirar(
                    s,
                    loja_id=loja_id,
                    tipo="video",
                    dados={},
                    chave_unica="corrida-1",
                    autor=SISTEMA,
                )
                resultados.append((t.id, criado))
        except Exception as e:  # pragma: no cover - só aparece se falhar
            erros.append(e)

    threads = [threading.Thread(target=pedir_em_paralelo) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert not erros
        assert len({tid for tid, _ in resultados}) == 1
        assert sum(criado for _, criado in resultados) == 1
    finally:
        with sessao() as s:
            s.delete(s.get(Loja, loja_id))
