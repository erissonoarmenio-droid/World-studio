"""Ponto de entrada do servidor do estúdio W-orld."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import obter_config
from app.nucleo.db import banco_ok
from app.nucleo.fila.trabalhador import EXECUTORES, Trabalhador


class _CacheR2:
    """O /saude é chamado o tempo todo; confere o R2 no máximo 1 vez por minuto."""

    def __init__(self) -> None:
        self.quando = 0.0
        self.ok = False

    def conferir(self) -> bool:
        if time.monotonic() - self.quando > 60:
            from app.nucleo.midia import armazenamento_midias

            try:
                self.ok = armazenamento_midias().ok()
            except Exception:  # configuração errada (ex.: Account ID inválido) = "fora"
                self.ok = False
            self.quando = time.monotonic()
        return self.ok


def criar_app() -> FastAPI:
    config = obter_config()
    estado: dict[str, Trabalhador | None] = {"trabalhador": None}
    cache_r2 = _CacheR2()

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        # O trabalhador da fila roda junto com o servidor (decisão de Eri, 25/10).
        if config.trabalhador_ativo:
            trabalhador = Trabalhador(EXECUTORES)
            trabalhador.iniciar()
            estado["trabalhador"] = trabalhador
        yield
        if estado["trabalhador"]:
            estado["trabalhador"].parar()

    app = FastAPI(
        title="Estúdio W-orld",
        version=config.versao,
        docs_url=None if config.ambiente == "producao" else "/docs",
        redoc_url=None,
        lifespan=ciclo_de_vida,
    )

    @app.get("/saude")
    def saude() -> JSONResponse:
        """Diz se o servidor e as peças de que ele depende estão no ar.

        200 quando tudo está ok; 503 quando alguma peça está fora (o Render usa isso
        para saber se o serviço está saudável). Nunca expõe detalhes internos.
        """
        componentes = {"processo": "ok", "banco": "ok" if banco_ok() else "fora"}
        if config.trabalhador_ativo:
            trabalhador = estado["trabalhador"]
            componentes["fila"] = "ok" if trabalhador and trabalhador.vivo() else "fora"
        if config.r2_configurado:
            componentes["r2"] = "ok" if cache_r2.conferir() else "fora"
        tudo_ok = all(v == "ok" for v in componentes.values())
        # O código HTTP depende só do que é nosso (processo, banco, fila). Se o R2 cair,
        # o /saude mostra "degradado", mas o Render não derruba o servidor por isso.
        essenciais_ok = all(v == "ok" for k, v in componentes.items() if k != "r2")
        return JSONResponse(
            status_code=200 if essenciais_ok else 503,
            content={"status": "ok" if tudo_ok else "degradado", "componentes": componentes},
        )

    return app


app = criar_app()
