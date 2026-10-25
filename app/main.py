"""Ponto de entrada do servidor do estúdio W-orld."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import obter_config
from app.nucleo.db import banco_ok
from app.nucleo.fila.trabalhador import EXECUTORES, Trabalhador


def criar_app() -> FastAPI:
    config = obter_config()
    estado: dict[str, Trabalhador | None] = {"trabalhador": None}

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
        tudo_ok = all(v == "ok" for v in componentes.values())
        return JSONResponse(
            status_code=200 if tudo_ok else 503,
            content={"status": "ok" if tudo_ok else "degradado", "componentes": componentes},
        )

    return app


app = criar_app()
