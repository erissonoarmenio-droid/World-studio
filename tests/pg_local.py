"""Sobe um PostgreSQL temporário para os testes (o mesmo PostgreSQL 16 do Render).

Se a variável TEST_DATABASE_URL existir (ex.: num serviço de integração contínua),
ela é usada e nada é iniciado aqui.
"""

import os
import shutil
import socket
import subprocess  # noqa: S404  (só roda os programas do próprio PostgreSQL)
import tempfile
import time
from pathlib import Path

BIN = Path(os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin"))


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _como_postgres(cmd: list[str]) -> list[str]:
    """O PostgreSQL não roda como root; se estivermos como root, usa o usuário 'postgres'."""
    if os.geteuid() == 0:
        return ["runuser", "-u", "postgres", "--", *cmd]
    return cmd


class PostgresTemporario:
    def __init__(self) -> None:
        self.pasta = Path(tempfile.mkdtemp(prefix="pgteste-"))
        self.porta = _porta_livre()
        if os.geteuid() == 0:
            shutil.chown(self.pasta, "postgres", "postgres")

    def iniciar(self) -> str:
        dados = self.pasta / "dados"
        subprocess.run(  # noqa: S603
            _como_postgres(
                [
                    str(BIN / "initdb"),
                    "-D",
                    str(dados),
                    "-U",
                    "teste",
                    "-A",
                    "trust",
                    "--no-sync",
                    "-E",
                    "UTF8",
                ]
            ),
            check=True,
            capture_output=True,
        )
        subprocess.run(  # noqa: S603
            _como_postgres(
                [
                    str(BIN / "pg_ctl"),
                    "-D",
                    str(dados),
                    "-l",
                    str(self.pasta / "log"),
                    "-o",
                    f"-p {self.porta} -k {self.pasta} -c listen_addresses=127.0.0.1 -c fsync=off",
                    "-w",
                    "start",
                ]
            ),
            check=True,
            capture_output=True,
        )
        url_admin = f"postgresql+psycopg://teste@127.0.0.1:{self.porta}/postgres"
        self._criar_banco(url_admin)
        return f"postgresql+psycopg://teste@127.0.0.1:{self.porta}/world_estudio_teste"

    def _criar_banco(self, url_admin: str) -> None:
        from sqlalchemy import create_engine, text

        engine = create_engine(url_admin, isolation_level="AUTOCOMMIT")
        for _ in range(30):
            try:
                with engine.connect() as c:
                    c.execute(text("CREATE DATABASE world_estudio_teste"))
                break
            except Exception:
                time.sleep(0.2)
        engine.dispose()

    def parar(self) -> None:
        subprocess.run(  # noqa: S603
            _como_postgres(
                [str(BIN / "pg_ctl"), "-D", str(self.pasta / "dados"), "-m", "fast", "stop"]
            ),
            check=False,
            capture_output=True,
        )
        shutil.rmtree(self.pasta, ignore_errors=True)
