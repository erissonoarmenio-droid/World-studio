"""Backup diário do banco (tarefa 13).

- Todo dia, a partir das 3h (Brasília), faz uma cópia completa do banco com
  `pg_dump` e guarda no bucket de backup do R2, fora do Render.
- Uma cópia por dia (`banco/AAAA-MM-DD.dump`). Se o arquivo do dia já existe,
  não faz de novo. Guarda 14 dias e apaga os mais antigos.
- Roda dentro do servidor, numa thread que olha a cada 10 min (sem custo extra no
  Render). Se o servidor estava desligado às 3h, faz assim que voltar.
- Com mais de uma cópia do servidor rodando, uma trava do Postgres garante que só
  uma faz o backup.
- Restaurar: ver docs/restaurar.md.

Manual: `python -m app.nucleo.backup --agora`
"""

import argparse
import logging
import os
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import make_url, text

from app.config import obter_config
from app.nucleo.db import obter_engine
from app.nucleo.db import sessao as abrir_sessao
from app.nucleo.eventos import registrar_evento

log = logging.getLogger("estudio.backup")

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
HORA = 3
GUARDAR_DIAS = 14
PASTA = "banco/"
TRAVA_PG = 7_301_301  # número fixo da trava do Postgres para o backup
INTERVALO = 600.0  # segundos entre as conferências
ATRASO_MAXIMO = timedelta(hours=30)


def chave_do_dia(dia: date) -> str:
    return f"{PASTA}{dia:%Y-%m-%d}.dump"


def dia_da_chave(chave: str) -> date | None:
    try:
        return date.fromisoformat(chave.removeprefix(PASTA).removesuffix(".dump"))
    except ValueError:
        return None


def url_para_pg_dump(database_url: str) -> str:
    """O SQLAlchemy usa 'postgresql+psycopg://'; o pg_dump quer 'postgresql://'."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def ambiente_pg(database_url: str) -> dict[str, str]:
    """Conexão em variáveis PG*: assim a senha não aparece na linha de comando."""
    u = make_url(url_para_pg_dump(database_url))
    query = {k: v if isinstance(v, str) else v[0] for k, v in u.query.items()}
    pares = {
        "PGHOST": u.host or query.get("host"),
        "PGPORT": str(u.port) if u.port else query.get("port"),
        "PGUSER": u.username,
        "PGPASSWORD": u.password,
        "PGDATABASE": u.database,
        "PGSSLMODE": query.get("sslmode"),
    }
    return {k: v for k, v in pares.items() if v}


def dia_devido(agora: datetime) -> date:
    """O dia cujo backup já deveria existir: hoje depois das 3h, senão ontem."""
    local = agora.astimezone(BRASILIA)
    return local.date() if local.hour >= HORA else local.date() - timedelta(days=1)


def existe(cliente: Any, bucket: str, chave: str) -> bool:
    try:
        cliente.head_object(Bucket=bucket, Key=chave)
        return True
    except Exception as erro:
        resposta = getattr(erro, "response", None) or {}
        if str(resposta.get("Error", {}).get("Code", "")) in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def fazer_backup(
    cliente: Any, bucket: str, database_url: str, dia: date, pg_dump: str = "pg_dump"
) -> int:
    """Gera o arquivo e envia. Devolve o tamanho em bytes."""
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = os.path.join(pasta, "banco.dump")
        processo = subprocess.run(  # noqa: S603 (programa e argumentos fixos)
            [pg_dump, "--format=custom", "--no-owner", "--no-privileges", "--file", arquivo],
            env={**os.environ, **ambiente_pg(database_url)},
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if processo.returncode != 0:
            # o stderr do pg_dump não traz a senha; mesmo assim, só as últimas linhas
            raise RuntimeError(f"pg_dump falhou: {processo.stderr.strip()[-300:]}")
        tamanho = os.path.getsize(arquivo)
        if tamanho == 0:
            raise RuntimeError("pg_dump gerou um arquivo vazio")
        cliente.upload_file(arquivo, bucket, chave_do_dia(dia))
    return tamanho


def apagar_antigos(cliente: Any, bucket: str, hoje: date) -> int:
    limite = hoje - timedelta(days=GUARDAR_DIAS)
    apagados = 0
    for pagina in cliente.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PASTA):
        for objeto in pagina.get("Contents", []):
            dia = dia_da_chave(objeto["Key"])
            if dia is not None and dia < limite:
                cliente.delete_object(Bucket=bucket, Key=objeto["Key"])
                apagados += 1
    return apagados


def rodar_se_precisar(
    cliente: Any,
    bucket: str,
    database_url: str,
    agora: datetime | None = None,
    pg_dump: str = "pg_dump",
) -> str:
    """'feito', 'ja_existia' ou 'outro_servidor' (outra cópia está fazendo)."""
    agora = agora or datetime.now(UTC)
    dia = dia_devido(agora)
    if existe(cliente, bucket, chave_do_dia(dia)):
        return "ja_existia"
    with obter_engine().connect() as conexao:
        if not conexao.scalar(text("SELECT pg_try_advisory_lock(:t)"), {"t": TRAVA_PG}):
            return "outro_servidor"
        try:
            if existe(cliente, bucket, chave_do_dia(dia)):
                return "ja_existia"
            tamanho = fazer_backup(cliente, bucket, database_url, dia, pg_dump)
            apagados = apagar_antigos(cliente, bucket, dia)
        finally:
            conexao.execute(text("SELECT pg_advisory_unlock(:t)"), {"t": TRAVA_PG})
            conexao.commit()
    with abrir_sessao() as s:
        registrar_evento(
            s,
            acao="backup_feito",
            detalhes={"dia": dia.isoformat(), "bytes": tamanho, "antigos_apagados": apagados},
        )
    log.info("backup %s feito (%d bytes, %d antigos apagados)", dia, tamanho, apagados)
    return "feito"


class Agendador:
    """Thread que confere a cada 10 min se o backup do dia já foi feito."""

    def __init__(self, cliente: Any, bucket: str, database_url: str, pg_dump: str = "pg_dump"):
        self.cliente, self.bucket, self.database_url, self.pg_dump = (
            cliente,
            bucket,
            database_url,
            pg_dump,
        )
        self.ultimo_ok: datetime | None = None
        self._ultima_falha_avisada: datetime | None = None
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="backup", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()

    def em_dia(self, agora: datetime | None = None) -> bool:
        agora = agora or datetime.now(UTC)
        return self.ultimo_ok is not None and agora - self.ultimo_ok < ATRASO_MAXIMO

    def conferir(self, agora: datetime | None = None) -> None:
        agora = agora or datetime.now(UTC)
        try:
            situacao = rodar_se_precisar(
                self.cliente, self.bucket, self.database_url, agora, self.pg_dump
            )
            if situacao in ("feito", "ja_existia"):
                self.ultimo_ok = agora
        except Exception as erro:
            log.warning("backup falhou: %s", type(erro).__name__)
            # um evento por hora, no máximo, para não lotar o registro
            ultima = self._ultima_falha_avisada
            if ultima is None or agora - ultima > timedelta(hours=1):
                self._ultima_falha_avisada = agora
                try:
                    with abrir_sessao() as s:
                        registrar_evento(
                            s,
                            acao="backup_falhou",
                            detalhes={"erro": f"{type(erro).__name__}: {erro}"[:300]},
                        )
                except Exception:
                    log.exception("não consegui registrar a falha do backup")

    def _laco(self) -> None:
        while not self._parar.is_set():
            self.conferir()
            self._parar.wait(INTERVALO)


def criar_agendador() -> Agendador:
    from app.nucleo.midia import cliente_r2

    config = obter_config()
    return Agendador(cliente_r2(), config.r2_bucket_backup, config.database_url, config.pg_dump)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do banco para o R2")
    parser.add_argument("--agora", action="store_true", help="faz o backup de hoje se faltar")
    args = parser.parse_args()
    if not args.agora:
        parser.print_help()
        return 1
    a = criar_agendador()
    print(rodar_se_precisar(a.cliente, a.bucket, a.database_url, pg_dump=a.pg_dump))
    return 0


if __name__ == "__main__":
    sys.exit(main())
