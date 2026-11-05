"""Tabelas do módulo `creditos`: assinatura da loja, lotes de crédito, livro-caixa e reservas.

- Assinatura: o plano da loja e a situação dela (ativa, vencendo, vencida, pausada, cancelada).
- Lote: um "pacotinho" de créditos com validade (o do mês, um extra, um ajuste do Eri).
  Gasta-se primeiro o lote que vence antes.
- Lançamento: o livro-caixa. Só acrescenta; o banco recusa edição.
- Reserva: créditos separados para um pedido. Pedido pronto → debitada; falhou → estornada.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.db import Base

PLANOS_VALIDOS = ("estudio", "social_media")
SITUACOES = ("ativa", "vencendo", "vencida", "pausada", "cancelada")
ORIGENS_LOTE = ("plano", "extra", "ajuste", "estorno")
TIPOS_LANCAMENTO = ("entrada", "reserva", "estorno", "ajuste_saida", "vencimento")
ESTADOS_RESERVA = ("reservada", "debitada", "estornada")


class Assinatura(Base):
    __tablename__ = "assinaturas"
    __table_args__ = (
        CheckConstraint(f"plano IN {PLANOS_VALIDOS}", name="plano_valido"),
        CheckConstraint(f"situacao IN {SITUACOES}", name="situacao_valida"),
    )

    loja_id: Mapped[int] = mapped_column(
        ForeignKey("lojas.id", ondelete="CASCADE"), primary_key=True
    )
    plano: Mapped[str] = mapped_column(String(20))
    situacao: Mapped[str] = mapped_column(String(12))
    inicio_ciclo: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    renova_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apagar_dados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Avisos já mandados, para não repetir: ["3dias:2026-12-05", "venceu:2026-12-05"].
    avisos: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Lote(Base):
    __tablename__ = "lotes_credito"
    __table_args__ = (
        CheckConstraint(f"origem IN {ORIGENS_LOTE}", name="origem_valida"),
        CheckConstraint("saldo >= 0 AND saldo <= creditos", name="saldo_no_limite"),
        CheckConstraint("creditos > 0", name="creditos_positivos"),
        # Para gastar: lotes da loja com saldo, do que vence antes para o que vence depois.
        Index(
            "ix_lotes_credito_com_saldo",
            "loja_id",
            "vence_em",
            postgresql_where=text("saldo > 0"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    origem: Mapped[str] = mapped_column(String(10))
    # Identificador do pagamento (Mercado Pago) ou do pedido: impede liberar duas vezes.
    referencia: Mapped[str | None] = mapped_column(String(120), unique=True)
    creditos: Mapped[int] = mapped_column(Integer)
    saldo: Mapped[int] = mapped_column(Integer)
    vence_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lancamento(Base):
    """Livro-caixa dos créditos. Só acrescenta: o banco recusa edição."""

    __tablename__ = "lancamentos_credito"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS_LANCAMENTO}", name="tipo_valido"),
        Index("ix_lancamentos_credito_loja_quando", "loja_id", "quando"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    quando: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(14))
    creditos: Mapped[int] = mapped_column(Integer)  # + entra, − sai
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes_credito.id", ondelete="SET NULL"))
    reserva_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservas_credito.id", ondelete="SET NULL")
    )
    quem: Mapped[str] = mapped_column(String(12))
    motivo: Mapped[str | None] = mapped_column(String(200))


class Reserva(Base):
    __tablename__ = "reservas_credito"
    __table_args__ = (
        CheckConstraint(f"estado IN {ESTADOS_RESERVA}", name="estado_valido"),
        CheckConstraint("creditos >= 0", name="creditos_nao_negativos"),
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        Index("ix_reservas_credito_fornecedor_dia", "fornecedor", "dia"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    chave_unica: Mapped[str] = mapped_column(String(120), unique=True)
    item: Mapped[str] = mapped_column(String(30))
    quantidade: Mapped[int] = mapped_column(Integer)
    creditos: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(10), server_default=text("'reservada'"))
    # De quais lotes saiu: [{"lote_id": 1, "creditos": 10}, ...] (para devolver ao lugar certo).
    partes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    fornecedor: Mapped[str] = mapped_column(String(30))
    custo_estimado: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    custo_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    dia: Mapped[date] = mapped_column(Date)  # dia em Brasília, para o teto diário
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
