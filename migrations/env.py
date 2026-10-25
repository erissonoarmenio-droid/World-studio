"""Alembic: aplica as migrações no banco apontado por DATABASE_URL."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.nucleo.modelos  # noqa: F401  (registra as tabelas no metadata)
from app.config import obter_config
from app.nucleo.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A URL vem sempre do ambiente; nunca fica escrita no alembic.ini.
config.set_main_option("sqlalchemy.url", obter_config().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def rodar_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def rodar_online() -> None:
    conectavel = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectavel.connect() as conexao:
        context.configure(connection=conexao, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    rodar_offline()
else:
    rodar_online()
