from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import criar_app
from tests.conftest import tabelas_do_banco


def test_migracoes_aplicadas(sessao_limpa):
    # A tabela de controle do Alembic existe e aponta para a última versão.
    assert "alembic_version" in tabelas_do_banco(sessao_limpa)
    versao = sessao_limpa.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert versao


def test_saude_com_banco_ok():
    resposta = TestClient(criar_app()).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json()["componentes"]["banco"] == "ok"


def test_saude_com_banco_fora(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "banco_ok", lambda: False)
    resposta = TestClient(main.criar_app()).get("/saude")
    assert resposta.status_code == 503
    assert resposta.json() == {
        "status": "degradado",
        "componentes": {"processo": "ok", "banco": "fora"},
    }


def test_banco_ok_nao_vaza_erro(monkeypatch):
    from app.nucleo import db

    class EngineQuebrada:
        def connect(self):
            raise RuntimeError("senha=segredo host=interno")

    monkeypatch.setattr(db, "obter_engine", lambda: EngineQuebrada())
    assert db.banco_ok() is False


def test_url_do_railway_ganha_driver(monkeypatch):
    from app.config import Config

    for original in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"):
        assert Config(database_url=original).database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_sessao_grava_e_desfaz_em_erro():
    import pytest

    from app.nucleo.db import sessao

    with sessao() as s:
        s.execute(text("CREATE TEMP TABLE IF NOT EXISTS t_sessao (x int)"))
    with pytest.raises(RuntimeError), sessao() as s:
        s.execute(text("SELECT 1"))
        raise RuntimeError("falha no meio")
