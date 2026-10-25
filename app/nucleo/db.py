"""Conexão com o banco de dados (PostgreSQL)."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import obter_config

# Nomes previsíveis para índices e restrições (as migrações ficam estáveis).
CONVENCAO_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


@lru_cache
def obter_engine() -> Engine:
    return create_engine(
        obter_config().database_url,
        pool_pre_ping=True,  # descarta conexões mortas (o banco reiniciou, por exemplo)
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
    )


@lru_cache
def _fabrica_sessoes() -> sessionmaker[Session]:
    return sessionmaker(bind=obter_engine(), expire_on_commit=False)


@contextmanager
def sessao() -> Iterator[Session]:
    """Sessão com commit no fim e rollback se algo der errado."""
    s = _fabrica_sessoes()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def banco_ok() -> bool:
    """Teste rápido para o /saude. Nunca deixa o erro vazar para fora."""
    try:
        with obter_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
