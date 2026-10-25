"""Tabela da fila de trabalhos (gerações demoradas)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.db import Base

TIPOS_TRABALHO = ("foto", "foto_especial", "video", "voz", "arte", "story", "teste")
ESTADOS = ("na_fila", "rodando", "concluido", "falhou", "cancelado")


class Trabalho(Base):
    __tablename__ = "trabalhos"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS_TRABALHO}", name="tipo_valido"),
        CheckConstraint(f"estado IN {ESTADOS}", name="estado_valido"),
        CheckConstraint("tentativas >= 0", name="tentativas_positivas"),
        # O trabalhador procura por aqui: o que está na fila e já pode rodar.
        Index(
            "ix_trabalhos_prontos",
            "proximo_horario",
            postgresql_where=text("estado = 'na_fila'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(12), server_default=text("'na_fila'"))
    dados: Mapped[dict[str, Any]] = mapped_column(JSONB)
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    erro: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(server_default=text("0"))
    proximo_horario: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    travado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chave_unica: Mapped[str] = mapped_column(String(120), unique=True)
    custo_estimado: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    custo_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    fornecedor: Mapped[str | None] = mapped_column(String(30))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
