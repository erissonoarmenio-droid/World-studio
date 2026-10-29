"""Tarefa 13: backup diário do banco para o R2 (simulado com moto) e restauração."""

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, date, datetime

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select

from app.nucleo import backup as mod
from app.nucleo.db import sessao as abrir_sessao
from app.nucleo.modelos import Evento

PG_BIN = "/usr/lib/postgresql/16/bin"
PG_DUMP = f"{PG_BIN}/pg_dump" if os.path.exists(f"{PG_BIN}/pg_dump") else shutil.which("pg_dump")
pytestmark = pytest.mark.skipif(PG_DUMP is None, reason="pg_dump não instalado")
BUCKET = "backup-teste"


@pytest.fixture
def cliente():
    with mock_aws():
        c = boto3.client("s3", region_name="us-east-1")
        c.create_bucket(Bucket=BUCKET)
        yield c


def _url():
    return os.environ["DATABASE_URL"]


def _eventos(acao):
    """O backup grava eventos numa sessão própria (já confirmada), fora do sessao_limpa."""
    with abrir_sessao() as s:
        return list(s.scalars(select(Evento).where(Evento.acao == acao).order_by(Evento.id.desc())))


def _chaves(c):
    return sorted(o["Key"] for o in c.list_objects_v2(Bucket=BUCKET).get("Contents", []))


def test_dia_devido_respeita_as_3h_de_brasilia():
    # 05:59 UTC = 02:59 em Brasília → ainda vale o de ontem
    assert mod.dia_devido(datetime(2026, 10, 29, 5, 59, tzinfo=UTC)) == date(2026, 10, 28)
    assert mod.dia_devido(datetime(2026, 10, 29, 6, 0, tzinfo=UTC)) == date(2026, 10, 29)


def test_url_do_pg_dump_sem_driver():
    url = "postgresql+psycopg://u:s@h:5432/b"
    assert mod.url_para_pg_dump(url) == "postgresql://u:s@h:5432/b"


def test_faz_uma_vez_por_dia_e_registra_evento(cliente, sessao_limpa):
    agora = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    assert mod.rodar_se_precisar(cliente, BUCKET, _url(), agora, PG_DUMP) == "feito"
    assert _chaves(cliente) == ["banco/2026-10-29.dump"]
    assert mod.rodar_se_precisar(cliente, BUCKET, _url(), agora, PG_DUMP) == "ja_existia"
    feitos = _eventos("backup_feito")
    assert feitos and feitos[0].detalhes["bytes"] > 0


def test_guarda_14_dias_e_apaga_os_antigos(cliente):
    for dia in ("2026-10-01", "2026-10-14", "2026-10-15", "2026-10-28"):
        cliente.put_object(Bucket=BUCKET, Key=f"banco/{dia}.dump", Body=b"x")
    cliente.put_object(Bucket=BUCKET, Key="banco/leia-me.txt", Body=b"x")  # não é backup
    assert mod.apagar_antigos(cliente, BUCKET, date(2026, 10, 29)) == 2
    assert _chaves(cliente) == [
        "banco/2026-10-15.dump",
        "banco/2026-10-28.dump",
        "banco/leia-me.txt",
    ]


def test_falha_do_pg_dump_vira_evento_sem_senha(cliente, sessao_limpa):
    a = mod.Agendador(cliente, BUCKET, "postgresql://u:senhasecreta@127.0.0.1:1/x", PG_DUMP)
    a.conferir(datetime(2026, 10, 29, 12, 0, tzinfo=UTC))
    assert not a.em_dia(datetime(2026, 10, 29, 12, 0, tzinfo=UTC))
    falhas = _eventos("backup_falhou")
    assert falhas and "senhasecreta" not in str(falhas[0].detalhes)
    assert _chaves(cliente) == []


def test_agendador_fica_em_dia_depois_do_backup(cliente):
    agora = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    a = mod.Agendador(cliente, BUCKET, _url(), PG_DUMP)
    a.conferir(agora)
    assert a.em_dia(agora)


def test_restaurar_num_banco_vazio_recupera_as_tabelas(cliente, sessao_limpa):
    agora = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    mod.rodar_se_precisar(cliente, BUCKET, _url(), agora, PG_DUMP)
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = os.path.join(pasta, "b.dump")
        cliente.download_file(BUCKET, "banco/2026-10-29.dump", arquivo)
        listagem = subprocess.run(  # noqa: S603 (teste, argumentos fixos)
            [PG_DUMP.replace("pg_dump", "pg_restore"), "--list", arquivo],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    for tabela in ("lojas", "pessoas", "eventos", "trabalhos", "midias", "alembic_version"):
        assert f"TABLE public {tabela}" in listagem or f"TABLE DATA public {tabela}" in listagem
