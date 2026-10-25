"""Ponto de entrada do servidor do estúdio W-orld."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import obter_config
from app.nucleo.db import banco_ok


def criar_app() -> FastAPI:
    config = obter_config()
    app = FastAPI(
        title="Estúdio W-orld",
        version=config.versao,
        docs_url=None if config.ambiente == "producao" else "/docs",
        redoc_url=None,
    )

    @app.get("/saude")
    def saude() -> JSONResponse:
        """Diz se o servidor e as peças de que ele depende estão no ar.

        200 quando tudo está ok; 503 quando alguma peça está fora (o Railway usa isso
        para saber se o serviço está saudável). Nunca expõe detalhes internos.
        Armazenamento e fila entram nas próximas tarefas.
        """
        componentes = {"processo": "ok", "banco": "ok" if banco_ok() else "fora"}
        tudo_ok = all(v == "ok" for v in componentes.values())
        return JSONResponse(
            status_code=200 if tudo_ok else 503,
            content={"status": "ok" if tudo_ok else "degradado", "componentes": componentes},
        )

    return app


app = criar_app()
