"""Passo 1.1: créditos (planos, reserva → débito/estorno, validade, liga/desliga, teto)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.creditos import servico as cr
from app.creditos import tabela
from app.nucleo.erros import (
    Conflito,
    DadosInvalidos,
    LojaDesligada,
    SemCreditos,
    TetoAtingido,
)
from app.nucleo.eventos import ERI, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.modelos import Lancamento, Lote

AGORA = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


def loja_com_plano(s, plano="estudio", ref="mp-1", nome="Bella", agora=AGORA):
    loja, _ = criar_loja_com_dona(s, {"nome": nome}, {"nome": "Ana"}, ERI)
    cr.ativar_plano(s, loja.id, plano, ref, agora=agora)
    return loja


# --- tabela (decisões de Eri) ---------------------------------------------------------------


def test_tabela_bate_com_o_combinado():
    assert tabela.PLANOS["estudio"].preco_centavos == 19700
    assert tabela.PLANOS["estudio"].creditos_mes == 75
    assert tabela.PLANOS["social_media"].preco_centavos == 59700
    assert tabela.PLANOS["social_media"].creditos_mes == 180
    assert tabela.PACOTES_EXTRAS["extra_100"].preco_centavos == 19900
    p = tabela.PRECO_CREDITOS
    assert (p["foto"], p["foto_produto"], p["foto_outro_corpo"], p["arte"]) == (2, 2, 2, 1)
    assert (p["video_480"], p["video_2_angulos"], p["video_720"]) == (15, 25, 30)
    assert (p["influencer_principal"], p["influencer_extra"], p["ajuste_rosto"]) == (0, 5, 2)
    assert tabela.AJUSTES_ROSTO_SEM_CUSTO == 3 and tabela.MAX_INFLUENCERS_POR_LOJA == 3


def test_margem_minima_de_2x_no_credito_mais_barato():
    """Pior caso: crédito do pacote de 100 (R$ 1,99), menos ~4% de taxa do cartão, dólar a 5,40."""
    real_por_credito = Decimal("1.99") * Decimal("0.96")
    for item, creditos in tabela.PRECO_CREDITOS.items():
        if creditos == 0:
            continue
        custo_reais = tabela.CUSTO_FORNECEDOR[item].usd * Decimal("5.40")
        assert creditos * real_por_credito >= 2 * custo_reais, item


def test_mais_um_mes_no_fim_do_mes():
    assert cr.mais_um_mes(datetime(2027, 1, 31, tzinfo=UTC)).date().isoformat() == "2027-02-28"
    assert cr.mais_um_mes(datetime(2026, 12, 15, tzinfo=UTC)).date().isoformat() == "2027-01-15"


# --- plano ------------------------------------------------------------------------------------


def test_ativar_plano_poe_creditos_e_liga_a_loja(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    assert loja.plano == "estudio" and loja.situacao == "ativa"
    saldo = cr.saldo(sessao_limpa, loja.id, AGORA)
    assert saldo.disponivel == 75 and saldo.reservado == 0
    assert saldo.proximo_vencimento == datetime(2026, 12, 10, 15, 0, tzinfo=UTC)
    assert "plano_ativado" in [e.acao for e in listar_eventos(sessao_limpa, loja.id)]


def test_mesmo_pagamento_nunca_libera_duas_vezes(sessao_limpa):
    loja = loja_com_plano(sessao_limpa, ref="mp-777")
    cr.ativar_plano(sessao_limpa, loja.id, "estudio", "mp-777", agora=AGORA)
    assert cr.saldo(sessao_limpa, loja.id, AGORA).disponivel == 75
    outra, _ = criar_loja_com_dona(sessao_limpa, {"nome": "Outra"}, {"nome": "Bia"}, ERI)
    with pytest.raises(Conflito):
        cr.ativar_plano(sessao_limpa, outra.id, "estudio", "mp-777", agora=AGORA)


def test_renovacao_antecipada_comeca_quando_o_ciclo_acaba(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    a = cr.ativar_plano(sessao_limpa, loja.id, "estudio", "mp-2", agora=AGORA + timedelta(days=25))
    assert a.inicio_ciclo == datetime(2026, 12, 10, 15, 0, tzinfo=UTC)
    assert a.renova_em == datetime(2027, 1, 10, 15, 0, tzinfo=UTC)
    # Os 75 do mês atual continuam até 10/12; os 75 novos valem até 10/01.
    assert cr.saldo(sessao_limpa, loja.id, AGORA + timedelta(days=25)).disponivel == 150


def test_extra_so_com_plano_ativo_e_vale_90_dias(sessao_limpa):
    loja, _ = criar_loja_com_dona(sessao_limpa, {"nome": "Sem plano"}, {"nome": "Ana"}, ERI)
    with pytest.raises(LojaDesligada):
        cr.comprar_extra(sessao_limpa, loja.id, "extra_30", "mp-x", agora=AGORA)
    loja = loja_com_plano(sessao_limpa, nome="Com plano")
    lote = cr.comprar_extra(sessao_limpa, loja.id, "extra_30", "mp-x2", agora=AGORA)
    assert lote.creditos == 30 and lote.vence_em == AGORA + timedelta(days=90)
    assert cr.comprar_extra(sessao_limpa, loja.id, "extra_30", "mp-x2", agora=AGORA) is lote


# --- reservar → confirmar / estornar --------------------------------------------------------


def test_reserva_confirma_e_nao_duplica(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    r = cr.reservar(sessao_limpa, loja.id, "foto", "pedido-1", agora=AGORA)
    assert r.creditos == 2 and r.estado == "reservada"
    assert cr.reservar(sessao_limpa, loja.id, "foto", "pedido-1", agora=AGORA) is r
    s = cr.saldo(sessao_limpa, loja.id, AGORA)
    assert (s.disponivel, s.reservado) == (73, 2)

    cr.confirmar(sessao_limpa, "pedido-1", custo_real=Decimal("0.04"), agora=AGORA)
    assert r.estado == "debitada" and r.custo_real == Decimal("0.04")
    s = cr.saldo(sessao_limpa, loja.id, AGORA)
    assert (s.disponivel, s.reservado) == (73, 0)
    assert cr.confirmar(sessao_limpa, "pedido-1", agora=AGORA) is r  # repetir não faz nada


def test_mesma_chave_para_outra_coisa_e_recusada(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "foto", "pedido-1", agora=AGORA)
    with pytest.raises(Conflito):
        cr.reservar(sessao_limpa, loja.id, "video_480", "pedido-1", agora=AGORA)


def test_estorno_devolve_e_nao_pode_debitar_depois(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v1", agora=AGORA)
    assert cr.saldo(sessao_limpa, loja.id, AGORA).disponivel == 60
    cr.estornar(sessao_limpa, "v1", "fornecedor falhou", agora=AGORA)
    assert cr.saldo(sessao_limpa, loja.id, AGORA).disponivel == 75
    with pytest.raises(Conflito):
        cr.confirmar(sessao_limpa, "v1", agora=AGORA)


def test_nao_estorna_pedido_ja_entregue(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "foto", "f1", agora=AGORA)
    cr.confirmar(sessao_limpa, "f1", agora=AGORA)
    with pytest.raises(Conflito):
        cr.estornar(sessao_limpa, "f1", "mudou de ideia", agora=AGORA)


def test_sem_creditos_diz_quantos_faltam(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    for i in range(5):
        cr.reservar(sessao_limpa, loja.id, "video_480", f"v{i}", agora=AGORA)
    with pytest.raises(SemCreditos) as erro:
        cr.reservar(sessao_limpa, loja.id, "video_480", "v5", agora=AGORA)
    assert erro.value.faltam == 15
    assert cr.saldo(sessao_limpa, loja.id, AGORA).disponivel == 0


def test_arte_so_no_social_media(sessao_limpa):
    estudio = loja_com_plano(sessao_limpa, ref="a")
    with pytest.raises(DadosInvalidos):
        cr.reservar(sessao_limpa, estudio.id, "arte", "arte-1", agora=AGORA)
    social = loja_com_plano(sessao_limpa, plano="social_media", ref="b", nome="Social")
    assert cr.reservar(sessao_limpa, social.id, "arte", "arte-2", agora=AGORA).creditos == 1


def test_mesma_peca_em_3_corpos_e_influencer_principal_gratis(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    assert (
        cr.reservar(sessao_limpa, loja.id, "influencer_principal", "inf-1", agora=AGORA).creditos
        == 0
    )
    assert (
        cr.reservar(sessao_limpa, loja.id, "influencer_extra", "inf-2", agora=AGORA).creditos == 5
    )
    r = cr.reservar(sessao_limpa, loja.id, "foto_outro_corpo", "corpos", quantidade=3, agora=AGORA)
    assert r.creditos == 6
    assert cr.saldo(sessao_limpa, loja.id, AGORA).disponivel == 75 - 5 - 6


def test_gasta_primeiro_o_que_vence_antes(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)  # 75, vence em 30 dias
    cr.comprar_extra(sessao_limpa, loja.id, "extra_30", "mp-e", agora=AGORA)  # 30, vence em 90
    r = cr.reservar(sessao_limpa, loja.id, "video_480", "v1", agora=AGORA)
    lote_plano = sessao_limpa.scalar(select(Lote).where(Lote.origem == "plano"))
    assert r.partes == [{"lote_id": lote_plano.id, "creditos": 15}]


def test_custo_muito_acima_do_estimado_avisa_o_eri(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v1", agora=AGORA)
    cr.confirmar(sessao_limpa, "v1", custo_real=Decimal("3.10"), agora=AGORA)  # > 2,15 × 1,3
    acoes = [e.acao for e in listar_eventos(sessao_limpa, loja.id)]
    assert "custo_acima_do_estimado" in acoes


# --- teto diário ------------------------------------------------------------------------------


def test_teto_diario_da_tein_para_o_7o_video(sessao_limpa, monkeypatch):
    from app.config import obter_config

    monkeypatch.setattr(obter_config(), "tetos_diarios_usd", {"tein": 15.0})  # o padrão real
    loja = loja_com_plano(sessao_limpa, plano="social_media")
    for i in range(6):  # 6 × 2,15 = 12,90
        cr.reservar(sessao_limpa, loja.id, "video_480", f"v{i}", agora=AGORA)
    with pytest.raises(TetoAtingido):  # 7 × 2,15 = 15,05 > 15
        cr.reservar(sessao_limpa, loja.id, "video_480", "v6", agora=AGORA)
    # Estornado não conta no teto; no dia seguinte zera.
    cr.estornar(sessao_limpa, "v0", "falhou", agora=AGORA)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v6", agora=AGORA)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v7", agora=AGORA + timedelta(days=1))


def test_teto_pode_ser_trocado_pela_configuracao(sessao_limpa, monkeypatch):
    from app.config import obter_config

    monkeypatch.setattr(obter_config(), "tetos_diarios_usd", {"tein": 3.0})
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v1", agora=AGORA)
    with pytest.raises(TetoAtingido):
        cr.reservar(sessao_limpa, loja.id, "video_480", "v2", agora=AGORA)


# --- validade e liga/desliga ------------------------------------------------------------------


def test_creditos_do_plano_vencem_na_renovacao(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    depois = AGORA + timedelta(days=31)
    assert cr.saldo(sessao_limpa, loja.id, depois).disponivel == 0
    cr.rotina_diaria(sessao_limpa, depois)
    ultimo = cr.extrato(sessao_limpa, loja.id)[0]
    assert ultimo.tipo == "vencimento" and ultimo.creditos == -75


def test_estorno_para_lote_vencido_volta_num_lote_novo(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    cr.reservar(sessao_limpa, loja.id, "video_480", "v1", agora=AGORA + timedelta(days=29))
    depois = AGORA + timedelta(days=30, hours=1)  # o lote do plano venceu no meio do vídeo
    cr.ativar_plano(sessao_limpa, loja.id, "estudio", "mp-2", agora=depois)
    cr.estornar(sessao_limpa, "v1", "falhou", agora=depois)
    assert cr.saldo(sessao_limpa, loja.id, depois).disponivel == 75 + 15


def test_loja_sem_plano_pausada_ou_vencida_nao_gera(sessao_limpa):
    sem, _ = criar_loja_com_dona(sessao_limpa, {"nome": "Sem"}, {"nome": "Ana"}, ERI)
    with pytest.raises(LojaDesligada):
        cr.reservar(sessao_limpa, sem.id, "foto", "x", agora=AGORA)

    loja = loja_com_plano(sessao_limpa, ref="p", nome="Pausa")
    cr.pausar(sessao_limpa, loja.id, "teste")
    assert loja.situacao == "pausada"
    with pytest.raises(LojaDesligada):
        cr.reservar(sessao_limpa, loja.id, "foto", "y", agora=AGORA)
    cr.retomar(sessao_limpa, loja.id, agora=AGORA)
    assert loja.situacao == "ativa"
    cr.reservar(sessao_limpa, loja.id, "foto", "y", agora=AGORA)

    cr.rotina_diaria(sessao_limpa, AGORA + timedelta(days=31))
    assert loja.situacao == "vencida"
    with pytest.raises(LojaDesligada):
        cr.reservar(sessao_limpa, loja.id, "foto", "z", agora=AGORA + timedelta(days=31))


def test_avisos_de_vencimento_saem_uma_vez(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    tres_dias_antes = AGORA + timedelta(days=27, hours=1)
    avisos = cr.rotina_diaria(sessao_limpa, tres_dias_antes)
    assert [(a.loja_id, a.tipo) for a in avisos] == [(loja.id, "vence_em_3_dias")]
    assert loja.situacao == "vencendo"
    assert cr.rotina_diaria(sessao_limpa, tres_dias_antes + timedelta(hours=5)) == []

    venceu = AGORA + timedelta(days=30, hours=1)
    assert [a.tipo for a in cr.rotina_diaria(sessao_limpa, venceu)] == ["venceu"]
    assert cr.rotina_diaria(sessao_limpa, venceu + timedelta(days=1)) == []

    # Renovou: volta a gerar na hora e o ciclo novo terá os próprios avisos.
    cr.ativar_plano(sessao_limpa, loja.id, "estudio", "mp-2", agora=venceu + timedelta(days=2))
    assert loja.situacao == "ativa"


def test_cancelar_guarda_dados_60_dias_e_renovar_traz_de_volta(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    a = cr.cancelar(sessao_limpa, loja.id, agora=AGORA)
    assert a.apagar_dados_em == AGORA + timedelta(days=60)
    assert [x.tipo for x in cr.rotina_diaria(sessao_limpa, AGORA + timedelta(days=61))] == [
        "apagar_dados"
    ]
    cr.ativar_plano(sessao_limpa, loja.id, "estudio", "mp-volta", agora=AGORA + timedelta(days=10))
    assert a.situacao == "ativa" and a.apagar_dados_em is None


# --- ajuste do Eri e livro-caixa ---------------------------------------------------------------


def test_ajuste_do_eri_precisa_de_motivo(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    with pytest.raises(DadosInvalidos):
        cr.ajustar(sessao_limpa, loja.id, 10, "  ", agora=AGORA)
    assert cr.ajustar(sessao_limpa, loja.id, 10, "presente do piloto", agora=AGORA) == 85
    assert cr.ajustar(sessao_limpa, loja.id, -5, "corrigir erro", agora=AGORA) == 80
    with pytest.raises(SemCreditos):
        cr.ajustar(sessao_limpa, loja.id, -500, "demais", agora=AGORA)


def test_livro_caixa_nao_pode_ser_editado(sessao_limpa):
    loja = loja_com_plano(sessao_limpa)
    lanc = sessao_limpa.scalar(select(Lancamento).where(Lancamento.loja_id == loja.id))
    with pytest.raises(DBAPIError):
        sessao_limpa.execute(
            text("UPDATE lancamentos_credito SET creditos = 999 WHERE id = :id"), {"id": lanc.id}
        )
        sessao_limpa.flush()
