"""creditos: assinaturas, lotes, livro-caixa e reservas

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-05 19:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assinaturas",
        sa.Column("loja_id", sa.BigInteger(), nullable=False),
        sa.Column("plano", sa.String(length=20), nullable=False),
        sa.Column("situacao", sa.String(length=12), nullable=False),
        sa.Column("inicio_ciclo", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renova_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apagar_dados_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "avisos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plano IN ('estudio', 'social_media')", name=op.f("ck_assinaturas_plano_valido")
        ),
        sa.CheckConstraint(
            "situacao IN ('ativa', 'vencendo', 'vencida', 'pausada', 'cancelada')",
            name=op.f("ck_assinaturas_situacao_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"], ["lojas.id"], name=op.f("fk_assinaturas_loja_id_lojas"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("loja_id", name=op.f("pk_assinaturas")),
    )
    op.create_index(op.f("ix_assinaturas_renova_em"), "assinaturas", ["renova_em"], unique=False)

    op.create_table(
        "lotes_credito",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("loja_id", sa.BigInteger(), nullable=False),
        sa.Column("origem", sa.String(length=10), nullable=False),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("creditos", sa.Integer(), nullable=False),
        sa.Column("saldo", sa.Integer(), nullable=False),
        sa.Column("vence_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "origem IN ('plano', 'extra', 'ajuste', 'estorno')",
            name=op.f("ck_lotes_credito_origem_valida"),
        ),
        sa.CheckConstraint(
            "saldo >= 0 AND saldo <= creditos", name=op.f("ck_lotes_credito_saldo_no_limite")
        ),
        sa.CheckConstraint("creditos > 0", name=op.f("ck_lotes_credito_creditos_positivos")),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name=op.f("fk_lotes_credito_loja_id_lojas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lotes_credito")),
        sa.UniqueConstraint("referencia", name=op.f("uq_lotes_credito_referencia")),
    )
    op.create_index(op.f("ix_lotes_credito_loja_id"), "lotes_credito", ["loja_id"], unique=False)
    op.create_index(
        "ix_lotes_credito_com_saldo",
        "lotes_credito",
        ["loja_id", "vence_em"],
        unique=False,
        postgresql_where=sa.text("saldo > 0"),
    )

    op.create_table(
        "reservas_credito",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("loja_id", sa.BigInteger(), nullable=False),
        sa.Column("chave_unica", sa.String(length=120), nullable=False),
        sa.Column("item", sa.String(length=30), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("creditos", sa.Integer(), nullable=False),
        sa.Column(
            "estado", sa.String(length=10), server_default=sa.text("'reservada'"), nullable=False
        ),
        sa.Column("partes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fornecedor", sa.String(length=30), nullable=False),
        sa.Column("custo_estimado", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("custo_real", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("fechada_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('reservada', 'debitada', 'estornada')",
            name=op.f("ck_reservas_credito_estado_valido"),
        ),
        sa.CheckConstraint(
            "creditos >= 0", name=op.f("ck_reservas_credito_creditos_nao_negativos")
        ),
        sa.CheckConstraint("quantidade > 0", name=op.f("ck_reservas_credito_quantidade_positiva")),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name=op.f("fk_reservas_credito_loja_id_lojas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservas_credito")),
        sa.UniqueConstraint("chave_unica", name=op.f("uq_reservas_credito_chave_unica")),
    )
    op.create_index(
        op.f("ix_reservas_credito_loja_id"), "reservas_credito", ["loja_id"], unique=False
    )
    op.create_index(
        "ix_reservas_credito_fornecedor_dia",
        "reservas_credito",
        ["fornecedor", "dia"],
        unique=False,
    )

    op.create_table(
        "lancamentos_credito",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "quando", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("loja_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.String(length=14), nullable=False),
        sa.Column("creditos", sa.Integer(), nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=True),
        sa.Column("reserva_id", sa.BigInteger(), nullable=True),
        sa.Column("quem", sa.String(length=12), nullable=False),
        sa.Column("motivo", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('entrada', 'reserva', 'estorno', 'ajuste_saida', 'vencimento')",
            name=op.f("ck_lancamentos_credito_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["loja_id"],
            ["lojas.id"],
            name=op.f("fk_lancamentos_credito_loja_id_lojas"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lote_id"],
            ["lotes_credito.id"],
            name=op.f("fk_lancamentos_credito_lote_id_lotes_credito"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reserva_id"],
            ["reservas_credito.id"],
            name=op.f("fk_lancamentos_credito_reserva_id_reservas_credito"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lancamentos_credito")),
    )
    op.create_index(
        "ix_lancamentos_credito_loja_quando",
        "lancamentos_credito",
        ["loja_id", "quando"],
        unique=False,
    )

    # Livro-caixa só acrescenta. A única mudança aceita é o banco soltar o lote/reserva
    # apagados (ON DELETE SET NULL) sem mexer em mais nada.
    op.execute(
        """
        CREATE FUNCTION lancamentos_somente_acrescenta() RETURNS trigger AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'lote_id' - 'reserva_id') = (to_jsonb(OLD) - 'lote_id' - 'reserva_id')
               AND (NEW.lote_id IS NULL OR NEW.lote_id = OLD.lote_id)
               AND (NEW.reserva_id IS NULL OR NEW.reserva_id = OLD.reserva_id) THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'lancamentos de credito nao podem ser editados';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER lancamentos_somente_acrescenta BEFORE UPDATE ON lancamentos_credito "
        "FOR EACH ROW EXECUTE FUNCTION lancamentos_somente_acrescenta()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS lancamentos_somente_acrescenta ON lancamentos_credito")
    op.execute("DROP FUNCTION IF EXISTS lancamentos_somente_acrescenta()")
    op.drop_index("ix_lancamentos_credito_loja_quando", table_name="lancamentos_credito")
    op.drop_table("lancamentos_credito")
    op.drop_index("ix_reservas_credito_fornecedor_dia", table_name="reservas_credito")
    op.drop_index(op.f("ix_reservas_credito_loja_id"), table_name="reservas_credito")
    op.drop_table("reservas_credito")
    op.drop_index(
        "ix_lotes_credito_com_saldo",
        table_name="lotes_credito",
        postgresql_where=sa.text("saldo > 0"),
    )
    op.drop_index(op.f("ix_lotes_credito_loja_id"), table_name="lotes_credito")
    op.drop_table("lotes_credito")
    op.drop_index(op.f("ix_assinaturas_renova_em"), table_name="assinaturas")
    op.drop_table("assinaturas")
