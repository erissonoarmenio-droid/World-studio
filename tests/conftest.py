import os

import pytest
from sqlalchemy import text

from tests.pg_local import PostgresTemporario


@pytest.fixture(scope="session", autouse=True)
def banco_de_teste():
    """Um banco PostgreSQL só para a rodada de testes, com as migrações aplicadas."""
    pg = None
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pg = PostgresTemporario()
        url = pg.iniciar()
    os.environ["DATABASE_URL"] = url
    os.environ["AMBIENTE"] = "teste"
    os.environ["TRABALHADOR_ATIVO"] = "false"  # os testes chamam o trabalhador direto

    from app.config import obter_config
    from app.nucleo import db

    obter_config.cache_clear()
    db.obter_engine.cache_clear()
    db._fabrica_sessoes.cache_clear()

    from alembic import command
    from alembic.config import Config as ConfigAlembic

    command.upgrade(ConfigAlembic("alembic.ini"), "head")
    yield url
    db.obter_engine().dispose()
    if pg:
        pg.parar()


@pytest.fixture
def sessao_limpa(banco_de_teste):
    """Sessão que desfaz tudo no fim de cada teste (cada teste começa com o banco limpo)."""
    from sqlalchemy.orm import Session

    from app.nucleo.db import obter_engine

    conexao = obter_engine().connect()
    transacao = conexao.begin()
    s = Session(bind=conexao, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        transacao.rollback()
        conexao.close()


def tabelas_do_banco(sessao) -> set[str]:
    linhas = sessao.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).scalars()
    return set(linhas)
