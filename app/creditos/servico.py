"""Créditos da loja: plano, saldo, reserva → débito ou estorno, validade, liga/desliga.

Regras (spec-api-bot-pagamento §1 e trajeto 1.1):
- Toda geração passa por `reservar` ANTES de ir para a fila. Pronto → `confirmar`.
  Falhou → `estornar` (os créditos voltam para o mesmo lote).
- A mesma `chave_unica` nunca reserva duas vezes (o pedido repetido devolve a mesma reserva).
- Gasta primeiro o lote que vence antes. Lote vencido não conta no saldo.
- Só gera com a loja ativa ou vencendo. Vencida, pausada ou cancelada: nada é gerado, mas
  tudo fica guardado e volta na hora ao renovar.
- Teto diário por fornecedor: se o pedido passaria do teto, para (`TetoAtingido`).
- Custo real acima de 1,3× o estimado vira evento de alerta para o Eri.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import obter_config
from app.creditos import tabela
from app.nucleo.erros import (
    Conflito,
    DadosInvalidos,
    LojaDesligada,
    NaoEncontrado,
    SemCreditos,
    TetoAtingido,
)
from app.nucleo.eventos import ERI, SISTEMA, Autor, registrar_evento
from app.nucleo.modelos import Assinatura, Lancamento, Loja, Lote, Reserva

BRASILIA = ZoneInfo("America/Sao_Paulo")
SITUACOES_QUE_GERAM = ("ativa", "vencendo")


def _agora() -> datetime:
    return datetime.now(UTC)


def dia_em_brasilia(momento: datetime) -> date:
    return momento.astimezone(BRASILIA).date()


def mais_um_mes(momento: datetime) -> datetime:
    """Mesmo dia do mês seguinte; 31/01 → 28/02 (ou 29)."""
    ano, mes = (momento.year + 1, 1) if momento.month == 12 else (momento.year, momento.month + 1)
    dia = min(momento.day, calendar.monthrange(ano, mes)[1])
    return momento.replace(year=ano, month=mes, day=dia)


# --- consultas ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Saldo:
    disponivel: int  # o que dá para gastar agora
    reservado: int  # separado para pedidos ainda em andamento
    vence_logo: int  # quanto vence nos próximos 3 dias
    proximo_vencimento: datetime | None


def obter_assinatura(sessao: Session, loja_id: int, travar: bool = False) -> Assinatura | None:
    consulta = select(Assinatura).where(Assinatura.loja_id == loja_id)
    if travar:
        consulta = consulta.with_for_update()
    return sessao.scalar(consulta)


def saldo(sessao: Session, loja_id: int, agora: datetime | None = None) -> Saldo:
    agora = agora or _agora()
    lotes = list(
        sessao.scalars(
            select(Lote)
            .where(Lote.loja_id == loja_id, Lote.saldo > 0, Lote.vence_em > agora)
            .order_by(Lote.vence_em)
        )
    )
    reservado = sessao.scalar(
        select(func.coalesce(func.sum(Reserva.creditos), 0)).where(
            Reserva.loja_id == loja_id, Reserva.estado == "reservada"
        )
    )
    limite = agora + timedelta(days=tabela.DIAS_AVISO_VENCIMENTO)
    return Saldo(
        disponivel=sum(lt.saldo for lt in lotes),
        reservado=int(reservado or 0),
        vence_logo=sum(lt.saldo for lt in lotes if lt.vence_em <= limite),
        proximo_vencimento=lotes[0].vence_em if lotes else None,
    )


def preco(item: str, plano: str | None, quantidade: int = 1) -> int:
    """Quantos créditos o pedido custa para a lojista."""
    if item not in tabela.PRECO_CREDITOS:
        raise DadosInvalidos(f"item desconhecido: {item!r}")
    if quantidade < 1 or quantidade > 20:
        raise DadosInvalidos("quantidade fora do limite (1 a 20)")
    if item in tabela.ITENS_SO_SOCIAL_MEDIA and plano != "social_media":
        raise DadosInvalidos("esse item é só do plano Social Media")
    return tabela.PRECO_CREDITOS[item] * quantidade


def custo_estimado(item: str, quantidade: int = 1) -> tabela.CustoFornecedor:
    c = tabela.CUSTO_FORNECEDOR[item]
    return tabela.CustoFornecedor(c.fornecedor, c.usd * quantidade)


def teto_diario(fornecedor: str) -> Decimal | None:
    extra = obter_config().tetos_diarios_usd
    if fornecedor in extra:
        return Decimal(str(extra[fornecedor]))
    return tabela.TETO_DIARIO_USD.get(fornecedor)


def gasto_do_dia(sessao: Session, fornecedor: str, dia: date) -> Decimal:
    """Soma do custo (real, se já existe; senão o estimado) de tudo que não foi estornado."""
    total = sessao.scalar(
        select(
            func.coalesce(func.sum(func.coalesce(Reserva.custo_real, Reserva.custo_estimado)), 0)
        ).where(
            Reserva.fornecedor == fornecedor,
            Reserva.dia == dia,
            Reserva.estado != "estornada",
        )
    )
    return Decimal(total or 0)


def extrato(sessao: Session, loja_id: int, limite: int = 50) -> list[Lancamento]:
    """Últimos lançamentos da loja, do mais novo para o mais antigo."""
    return list(
        sessao.scalars(
            select(Lancamento)
            .where(Lancamento.loja_id == loja_id)
            .order_by(Lancamento.quando.desc(), Lancamento.id.desc())
            .limit(limite)
        )
    )


# --- entradas: plano, extra, ajuste ---------------------------------------------------------


def _loja(sessao: Session, loja_id: int) -> Loja:
    loja = sessao.get(Loja, loja_id)
    if loja is None:
        raise NaoEncontrado("loja não encontrada")
    return loja


def _novo_lote(
    sessao: Session,
    *,
    loja_id: int,
    origem: str,
    creditos: int,
    vence_em: datetime,
    autor: Autor,
    motivo: str,
    referencia: str | None = None,
    reserva_id: int | None = None,
) -> Lote:
    lote = Lote(
        loja_id=loja_id,
        origem=origem,
        referencia=referencia,
        creditos=creditos,
        saldo=creditos,
        vence_em=vence_em,
    )
    sessao.add(lote)
    sessao.flush()
    sessao.add(
        Lancamento(
            loja_id=loja_id,
            tipo="estorno" if origem == "estorno" else "entrada",
            creditos=creditos,
            lote_id=lote.id,
            reserva_id=reserva_id,
            quem=autor.tipo,
            motivo=motivo[:200],
        )
    )
    sessao.flush()
    return lote


def _sincronizar_loja(sessao: Session, assinatura: Assinatura) -> None:
    loja = _loja(sessao, assinatura.loja_id)
    loja.plano = assinatura.plano
    loja.situacao = assinatura.situacao


def ativar_plano(
    sessao: Session,
    loja_id: int,
    plano: str,
    referencia: str,
    autor: Autor = SISTEMA,
    agora: datetime | None = None,
) -> Assinatura:
    """Pagamento do plano aprovado (ou Eri liberando na mão): abre/renova o ciclo e põe os
    créditos do mês. A mesma `referencia` (id do pagamento) nunca libera duas vezes."""
    agora = agora or _agora()
    if plano not in tabela.PLANOS:
        raise DadosInvalidos(f"plano desconhecido: {plano!r}")
    if not referencia or len(referencia) > 120:
        raise DadosInvalidos("referência do pagamento vazia ou longa demais")
    _loja(sessao, loja_id)
    assinatura = obter_assinatura(sessao, loja_id, travar=True)
    usado = sessao.scalar(select(Lote).where(Lote.referencia == referencia))
    if usado is not None:
        if usado.loja_id != loja_id or assinatura is None:
            raise Conflito("esse pagamento já foi usado em outra loja")
        return assinatura

    renovacao_antecipada = (
        assinatura is not None
        and assinatura.plano == plano
        and assinatura.situacao in SITUACOES_QUE_GERAM
        and assinatura.renova_em > agora
    )
    # Pagou antes de vencer: o ciclo novo começa quando o atual acaba.
    inicio = assinatura.renova_em if renovacao_antecipada else agora
    renova_em = mais_um_mes(inicio)

    if assinatura is None:
        assinatura = Assinatura(loja_id=loja_id, plano=plano, avisos=[])
        sessao.add(assinatura)
    assinatura.plano = plano
    assinatura.inicio_ciclo = inicio
    assinatura.renova_em = renova_em
    assinatura.situacao = "ativa"
    assinatura.cancelada_em = None
    assinatura.apagar_dados_em = None
    sessao.flush()
    _sincronizar_loja(sessao, assinatura)

    p = tabela.PLANOS[plano]
    _novo_lote(
        sessao,
        loja_id=loja_id,
        origem="plano",
        creditos=p.creditos_mes,
        vence_em=renova_em,
        autor=autor,
        motivo=f"plano {p.nome}",
        referencia=referencia,
    )
    registrar_evento(
        sessao,
        acao="plano_ativado",
        autor=autor,
        loja_id=loja_id,
        detalhes={
            "plano": plano,
            "creditos": p.creditos_mes,
            "renova_em": renova_em.isoformat(),
            "antecipada": renovacao_antecipada,
        },
    )
    return assinatura


def comprar_extra(
    sessao: Session,
    loja_id: int,
    pacote: str,
    referencia: str,
    autor: Autor = SISTEMA,
    agora: datetime | None = None,
) -> Lote:
    """Pacote extra pago: vale 90 dias. Só com o plano ativo."""
    agora = agora or _agora()
    if pacote not in tabela.PACOTES_EXTRAS:
        raise DadosInvalidos(f"pacote desconhecido: {pacote!r}")
    assinatura = obter_assinatura(sessao, loja_id, travar=True)
    existente = sessao.scalar(select(Lote).where(Lote.referencia == referencia))
    if existente is not None:
        if existente.loja_id != loja_id:
            raise Conflito("esse pagamento já foi usado em outra loja")
        return existente
    if assinatura is None or assinatura.situacao not in SITUACOES_QUE_GERAM:
        raise LojaDesligada("pacote extra só com o plano ativo")
    p = tabela.PACOTES_EXTRAS[pacote]
    lote = _novo_lote(
        sessao,
        loja_id=loja_id,
        origem="extra",
        creditos=p.creditos,
        vence_em=agora + timedelta(days=tabela.DIAS_VALIDADE_EXTRA),
        autor=autor,
        motivo=f"pacote {p.nome}",
        referencia=referencia,
    )
    registrar_evento(
        sessao,
        acao="extra_comprado",
        autor=autor,
        loja_id=loja_id,
        detalhes={"pacote": pacote, "creditos": p.creditos},
    )
    return lote


def _tirar_dos_lotes(
    sessao: Session, loja_id: int, creditos: int, agora: datetime
) -> list[dict[str, int]]:
    """Tira créditos dos lotes, do que vence antes para o que vence depois.
    Levanta SemCreditos sem mexer em nada se não der."""
    lotes = list(
        sessao.scalars(
            select(Lote)
            .where(Lote.loja_id == loja_id, Lote.saldo > 0, Lote.vence_em > agora)
            .order_by(Lote.vence_em, Lote.id)
            .with_for_update()
        )
    )
    disponivel = sum(lt.saldo for lt in lotes)
    if disponivel < creditos:
        faltam = creditos - disponivel
        raise SemCreditos(
            f"saldo insuficiente: precisa de {creditos}, tem {disponivel}", faltam=faltam
        )
    partes: list[dict[str, int]] = []
    restante = creditos
    for lote in lotes:
        if restante == 0:
            break
        tirar = min(lote.saldo, restante)
        lote.saldo -= tirar
        restante -= tirar
        partes.append({"lote_id": lote.id, "creditos": tirar})
    sessao.flush()
    return partes


def ajustar(
    sessao: Session,
    loja_id: int,
    creditos: int,
    motivo: str,
    autor: Autor = ERI,
    agora: datetime | None = None,
) -> int:
    """Eri dá (+) ou tira (−) créditos na mão, sempre com motivo. Devolve o saldo novo."""
    agora = agora or _agora()
    motivo = (motivo or "").strip()
    if not motivo:
        raise DadosInvalidos("ajuste de créditos precisa de motivo")
    if creditos == 0 or abs(creditos) > 1000:
        raise DadosInvalidos("ajuste precisa ser entre 1 e 1000 créditos (para mais ou menos)")
    _loja(sessao, loja_id)
    obter_assinatura(sessao, loja_id, travar=True)
    if creditos > 0:
        _novo_lote(
            sessao,
            loja_id=loja_id,
            origem="ajuste",
            creditos=creditos,
            vence_em=agora + timedelta(days=tabela.DIAS_VALIDADE_AJUSTE),
            autor=autor,
            motivo=motivo,
        )
    else:
        for parte in _tirar_dos_lotes(sessao, loja_id, -creditos, agora):
            sessao.add(
                Lancamento(
                    loja_id=loja_id,
                    tipo="ajuste_saida",
                    creditos=-parte["creditos"],
                    lote_id=parte["lote_id"],
                    quem=autor.tipo,
                    motivo=motivo[:200],
                )
            )
        sessao.flush()
    registrar_evento(
        sessao,
        acao="creditos_ajustados",
        autor=autor,
        loja_id=loja_id,
        detalhes={"creditos": creditos, "motivo": motivo[:200]},
    )
    return saldo(sessao, loja_id, agora).disponivel


# --- pedidos: reservar → confirmar ou estornar -----------------------------------------------


def reservar(
    sessao: Session,
    loja_id: int,
    item: str,
    chave_unica: str,
    quantidade: int = 1,
    autor: Autor = SISTEMA,
    agora: datetime | None = None,
) -> Reserva:
    """Separa os créditos do pedido antes de gerar. Mesmo pedido repetido → mesma reserva."""
    agora = agora or _agora()
    if not chave_unica or len(chave_unica) > 120:
        raise DadosInvalidos("chave do pedido vazia ou longa demais")

    existente = sessao.scalar(select(Reserva).where(Reserva.chave_unica == chave_unica))
    if existente is not None:
        if existente.loja_id != loja_id or existente.item != item:
            raise Conflito("essa chave de pedido já foi usada para outra coisa")
        return existente

    assinatura = obter_assinatura(sessao, loja_id, travar=True)  # um pedido por vez por loja
    if assinatura is None or assinatura.situacao not in SITUACOES_QUE_GERAM:
        situacao = assinatura.situacao if assinatura else "sem plano"
        raise LojaDesligada(f"a loja está {situacao}: não gera nada até renovar")

    creditos = preco(item, assinatura.plano, quantidade)
    custo = custo_estimado(item, quantidade)
    dia = dia_em_brasilia(agora)
    teto = teto_diario(custo.fornecedor)
    if teto is not None:
        gasto = gasto_do_dia(sessao, custo.fornecedor, dia)
        if gasto + custo.usd > teto:
            raise TetoAtingido(
                f"o gasto de hoje com {custo.fornecedor} passaria do teto "
                f"(US$ {gasto} + {custo.usd} > {teto})"
            )

    partes = _tirar_dos_lotes(sessao, loja_id, creditos, agora) if creditos else []
    reserva = Reserva(
        loja_id=loja_id,
        chave_unica=chave_unica,
        item=item,
        quantidade=quantidade,
        creditos=creditos,
        estado="reservada",
        partes=partes,
        fornecedor=custo.fornecedor,
        custo_estimado=custo.usd,
        dia=dia,
    )
    sessao.add(reserva)
    sessao.flush()
    for parte in partes:
        sessao.add(
            Lancamento(
                loja_id=loja_id,
                tipo="reserva",
                creditos=-parte["creditos"],
                lote_id=parte["lote_id"],
                reserva_id=reserva.id,
                quem=autor.tipo,
                motivo=item,
            )
        )
    sessao.flush()
    registrar_evento(
        sessao,
        acao="creditos_reservados",
        autor=autor,
        loja_id=loja_id,
        detalhes={"reserva_id": reserva.id, "item": item, "creditos": creditos},
        custo=custo.usd,
    )
    return reserva


def _reserva(sessao: Session, chave_unica: str) -> Reserva:
    reserva = sessao.scalar(
        select(Reserva).where(Reserva.chave_unica == chave_unica).with_for_update()
    )
    if reserva is None:
        raise NaoEncontrado("reserva não encontrada")
    return reserva


def confirmar(
    sessao: Session,
    chave_unica: str,
    custo_real: Decimal | None = None,
    agora: datetime | None = None,
) -> Reserva:
    """Pedido entregue: os créditos ficam gastos de vez e o custo real é guardado."""
    agora = agora or _agora()
    reserva = _reserva(sessao, chave_unica)
    if reserva.estado == "debitada":
        return reserva
    if reserva.estado == "estornada":
        raise Conflito("essa reserva já foi devolvida; não pode ser debitada")
    if custo_real is not None and custo_real < 0:
        raise DadosInvalidos("custo real não pode ser negativo")
    reserva.estado = "debitada"
    reserva.custo_real = custo_real
    reserva.fechada_em = agora
    sessao.flush()
    registrar_evento(
        sessao,
        acao="creditos_debitados",
        loja_id=reserva.loja_id,
        detalhes={"reserva_id": reserva.id, "item": reserva.item, "creditos": reserva.creditos},
        custo=custo_real,
    )
    if (
        custo_real is not None
        and reserva.custo_estimado > 0
        and custo_real > reserva.custo_estimado * tabela.LIMITE_ALERTA_CUSTO
    ):
        registrar_evento(
            sessao,
            acao="custo_acima_do_estimado",
            loja_id=reserva.loja_id,
            detalhes={
                "reserva_id": reserva.id,
                "fornecedor": reserva.fornecedor,
                "estimado": str(reserva.custo_estimado),
                "real": str(custo_real),
            },
            custo=custo_real,
        )
    return reserva


def estornar(
    sessao: Session,
    chave_unica: str,
    motivo: str,
    autor: Autor = SISTEMA,
    agora: datetime | None = None,
) -> Reserva:
    """Pedido falhou: os créditos voltam para os lotes de onde saíram. Se o lote já venceu,
    voltam num lote novo de 30 dias (a lojista não perde por falha nossa)."""
    agora = agora or _agora()
    reserva = _reserva(sessao, chave_unica)
    if reserva.estado == "estornada":
        return reserva
    if reserva.estado == "debitada":
        raise Conflito("pedido já entregue; para devolver, o Eri faz um ajuste com motivo")
    for parte in reserva.partes:
        lote = sessao.get(Lote, parte["lote_id"], with_for_update=True)
        if lote is not None and lote.vence_em > agora:
            lote.saldo += parte["creditos"]
            sessao.add(
                Lancamento(
                    loja_id=reserva.loja_id,
                    tipo="estorno",
                    creditos=parte["creditos"],
                    lote_id=lote.id,
                    reserva_id=reserva.id,
                    quem=autor.tipo,
                    motivo=motivo[:200],
                )
            )
        else:
            _novo_lote(
                sessao,
                loja_id=reserva.loja_id,
                origem="estorno",
                creditos=parte["creditos"],
                vence_em=agora + timedelta(days=tabela.DIAS_VALIDADE_ESTORNO),
                autor=autor,
                motivo=motivo,
                reserva_id=reserva.id,
            )
    reserva.estado = "estornada"
    reserva.fechada_em = agora
    sessao.flush()
    registrar_evento(
        sessao,
        acao="creditos_estornados",
        autor=autor,
        loja_id=reserva.loja_id,
        detalhes={"reserva_id": reserva.id, "creditos": reserva.creditos, "motivo": motivo[:200]},
    )
    return reserva


# --- liga/desliga e rotinas diárias -----------------------------------------------------------


def pausar(sessao: Session, loja_id: int, motivo: str, autor: Autor = ERI) -> Assinatura:
    assinatura = obter_assinatura(sessao, loja_id, travar=True)
    if assinatura is None:
        raise NaoEncontrado("essa loja ainda não tem plano")
    if assinatura.situacao == "cancelada":
        raise Conflito("loja cancelada não pode ser pausada")
    assinatura.situacao = "pausada"
    sessao.flush()
    _sincronizar_loja(sessao, assinatura)
    registrar_evento(
        sessao, acao="loja_pausada", autor=autor, loja_id=loja_id, detalhes={"motivo": motivo}
    )
    return assinatura


def _situacao_pela_data(assinatura: Assinatura, agora: datetime) -> str:
    if agora >= assinatura.renova_em:
        return "vencida"
    if assinatura.renova_em - agora <= timedelta(days=tabela.DIAS_AVISO_VENCIMENTO):
        return "vencendo"
    return "ativa"


def retomar(
    sessao: Session, loja_id: int, autor: Autor = ERI, agora: datetime | None = None
) -> Assinatura:
    agora = agora or _agora()
    assinatura = obter_assinatura(sessao, loja_id, travar=True)
    if assinatura is None or assinatura.situacao != "pausada":
        raise Conflito("a loja não está pausada")
    assinatura.situacao = _situacao_pela_data(assinatura, agora)
    sessao.flush()
    _sincronizar_loja(sessao, assinatura)
    registrar_evento(
        sessao,
        acao="loja_retomada",
        autor=autor,
        loja_id=loja_id,
        detalhes={"situacao": assinatura.situacao},
    )
    return assinatura


def cancelar(
    sessao: Session, loja_id: int, autor: Autor = ERI, agora: datetime | None = None
) -> Assinatura:
    """Cancelamento definitivo: para tudo; os dados ficam guardados 60 dias e depois são
    apagados (LGPD). Renovar antes disso traz tudo de volta."""
    agora = agora or _agora()
    assinatura = obter_assinatura(sessao, loja_id, travar=True)
    if assinatura is None:
        raise NaoEncontrado("essa loja ainda não tem plano")
    assinatura.situacao = "cancelada"
    assinatura.cancelada_em = agora
    assinatura.apagar_dados_em = agora + timedelta(
        days=tabela.DIAS_GUARDAR_DADOS_DEPOIS_DE_CANCELAR
    )
    sessao.flush()
    _sincronizar_loja(sessao, assinatura)
    registrar_evento(
        sessao,
        acao="loja_cancelada",
        autor=autor,
        loja_id=loja_id,
        detalhes={"apagar_dados_em": assinatura.apagar_dados_em.isoformat()},
    )
    return assinatura


@dataclass(frozen=True)
class Aviso:
    loja_id: int
    tipo: str  # "vence_em_3_dias" | "venceu" | "apagar_dados"
    quando: datetime


def rotina_diaria(sessao: Session, agora: datetime | None = None) -> list[Aviso]:
    """Roda 1× por dia (e pode rodar mais sem estragar nada):
    zera lotes vencidos, atualiza ativa/vencendo/vencida e devolve os avisos a mandar
    (cada aviso sai uma vez só por ciclo)."""
    agora = agora or _agora()
    # 1) Lotes vencidos com saldo: o saldo vira lançamento de vencimento.
    for lote in sessao.scalars(
        select(Lote).where(Lote.saldo > 0, Lote.vence_em <= agora).with_for_update()
    ):
        sessao.add(
            Lancamento(
                loja_id=lote.loja_id,
                tipo="vencimento",
                creditos=-lote.saldo,
                lote_id=lote.id,
                quem="sistema",
                motivo=f"créditos de {lote.origem} venceram",
            )
        )
        lote.saldo = 0
    sessao.flush()

    # 2) Situação de cada assinatura e avisos.
    avisos: list[Aviso] = []
    for a in sessao.scalars(select(Assinatura).with_for_update()):
        ciclo = a.renova_em.date().isoformat()
        if a.situacao == "cancelada":
            marca = f"apagar:{ciclo}"
            if a.apagar_dados_em and agora >= a.apagar_dados_em and marca not in a.avisos:
                avisos.append(Aviso(a.loja_id, "apagar_dados", agora))
                a.avisos = [*a.avisos, marca]
            continue
        if a.situacao == "pausada":
            continue
        nova = _situacao_pela_data(a, agora)
        if nova != a.situacao:
            a.situacao = nova
            _sincronizar_loja(sessao, a)
            registrar_evento(
                sessao, acao="situacao_mudou", loja_id=a.loja_id, detalhes={"situacao": nova}
            )
        marca = None
        if nova == "vencendo":
            marca, tipo = f"3dias:{ciclo}", "vence_em_3_dias"
        elif nova == "vencida":
            marca, tipo = f"venceu:{ciclo}", "venceu"
        if marca and marca not in a.avisos:
            avisos.append(Aviso(a.loja_id, tipo, agora))
            a.avisos = [*a.avisos, marca][-12:]
    sessao.flush()
    return avisos
