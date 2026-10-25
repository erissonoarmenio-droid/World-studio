"""Tabelas do cadastro: lojas, pessoas e o registro de eventos."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.db import Base

PAPEIS = ("dona", "socia", "funcionaria")
TIPOS_AUTOR = ("pessoa", "influencer", "eri", "sistema")


class Loja(Base):
    __tablename__ = "lojas"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    instagram: Mapped[str | None] = mapped_column(String(30), unique=True)
    segmento: Mapped[str | None] = mapped_column(String(60))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(String(2))
    canais_venda: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    horario: Mapped[str | None] = mapped_column(String(200))
    endereco: Mapped[str | None] = mapped_column(String(300))
    # Preenchidos pelo módulo `creditos`.
    plano: Mapped[str | None] = mapped_column(String(30))
    situacao: Mapped[str | None] = mapped_column(String(20))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pessoas: Mapped[list["Pessoa"]] = relationship(back_populates="loja")


class Pessoa(Base):
    __tablename__ = "pessoas"
    __table_args__ = (
        CheckConstraint(f"papel IN {PAPEIS}", name="papel_valido"),
        # Uma única dona por loja.
        Index(
            "uq_pessoas_uma_dona_por_loja",
            "loja_id",
            unique=True,
            postgresql_where=text("papel = 'dona'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    papel: Mapped[str] = mapped_column(String(12))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    whatsapp: Mapped[str | None] = mapped_column(String(13))
    email: Mapped[str | None] = mapped_column(String(254))
    pode_aprovar_gastos: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    loja: Mapped[Loja] = relationship(back_populates="pessoas")


class Evento(Base):
    """Registro de quem fez o quê, quando e quanto custou. Só acrescenta: o banco recusa edição."""

    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(f"quem IN {TIPOS_AUTOR}", name="quem_valido"),
        Index("ix_eventos_loja_quando", "loja_id", "quando"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    quando: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    loja_id: Mapped[int | None] = mapped_column(ForeignKey("lojas.id", ondelete="SET NULL"))
    quem: Mapped[str] = mapped_column(String(12))
    pessoa_id: Mapped[int | None] = mapped_column(BigInteger)  # sem FK: o evento sobrevive à pessoa
    acao: Mapped[str] = mapped_column(String(60), index=True)
    detalhes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    custo: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))


class Convite(Base):
    """Código para uma pessoa entrar na loja. Guardado só como hash; vale uma vez, por 48 h."""

    __tablename__ = "convites"
    __table_args__ = (CheckConstraint("papel IN ('socia', 'funcionaria')", name="papel_valido"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(12))
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True)
    criado_por: Mapped[int | None] = mapped_column(BigInteger)  # pessoa_id da dona (None = Eri)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_por: Mapped[int | None] = mapped_column(ForeignKey("pessoas.id", ondelete="SET NULL"))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


TIPOS_CONSENTIMENTO = (
    "termos_privacidade",
    "dados_agregados",
    "instagram",
    "whatsapp",
    "ordem_fixa",
    "modo_automatico",
    "clone",
)


class Consentimento(Base):
    """Aceite com versão do texto e horário. Revogar marca a data; nada é apagado."""

    __tablename__ = "consentimentos"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS_CONSENTIMENTO}", name="tipo_valido"),
        # No máximo um aceite em vigor por pessoa e tipo.
        Index(
            "uq_consentimentos_um_ativo",
            "pessoa_id",
            "tipo",
            unique=True,
            postgresql_where=text("revogado_em IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id", ondelete="CASCADE"), index=True)
    loja_id: Mapped[int] = mapped_column(ForeignKey("lojas.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(24))
    versao: Mapped[str] = mapped_column(String(20))
    aceito_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revogado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detalhes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class PerfilLoja(Base):
    """A "lista invisível" da influencer: marca, influencer, respostas, preferências.

    `dados` é plano: {"marca.tom": {"valor": ..., "origem": "instagram", "em": "..."}}.
    """

    __tablename__ = "perfil_loja"

    loja_id: Mapped[int] = mapped_column(
        ForeignKey("lojas.id", ondelete="CASCADE"), primary_key=True
    )
    dados: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Fiscal(Base):
    """Dados fiscais. Vazio no piloto; preenchido quando a loja for pagar."""

    __tablename__ = "fiscal"
    __table_args__ = (CheckConstraint("tipo IN ('cpf', 'cnpj')", name="tipo_valido"),)

    loja_id: Mapped[int] = mapped_column(
        ForeignKey("lojas.id", ondelete="CASCADE"), primary_key=True
    )
    tipo: Mapped[str] = mapped_column(String(4))
    documento: Mapped[str] = mapped_column(String(14))
    razao_social: Mapped[str | None] = mapped_column(String(200))
    situacao: Mapped[str | None] = mapped_column(String(40))  # da consulta pública, depois
    conferido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PalavraSenha(Base):
    """Palavra-senha da dona. Só o hash Argon2id; ninguém consegue ler a palavra."""

    __tablename__ = "palavra_senha"

    pessoa_id: Mapped[int] = mapped_column(
        ForeignKey("pessoas.id", ondelete="CASCADE"), primary_key=True
    )
    hash: Mapped[str] = mapped_column(String(200))
    dica: Mapped[str | None] = mapped_column(String(100))
    tentativas_erradas: Mapped[int] = mapped_column(server_default=text("0"))
    bloqueada_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valida_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    troca_liberada_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CodigoRecuperacao(Base):
    """Código de 6 números por e-mail para recuperar a palavra (depois do piloto)."""

    __tablename__ = "codigos_recuperacao"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id", ondelete="CASCADE"), index=True)
    hash: Mapped[str] = mapped_column(String(200))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tentativas: Mapped[int] = mapped_column(server_default=text("0"))
    usado: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
