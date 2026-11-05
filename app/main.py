"""Ponto de entrada do servidor do estúdio W-orld."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import obter_config
from app.interno import resposta_de_erro
from app.interno import rota as rota_interna
from app.nucleo.backup import Agendador
from app.nucleo.db import banco_ok
from app.nucleo.erros import ErroNucleo
from app.nucleo.fila.trabalhador import EXECUTORES, Trabalhador


class _CacheR2:
    """O /saude é chamado o tempo todo; confere o R2 no máximo 1 vez por minuto."""

    def __init__(self) -> None:
        # None = nunca conferiu. Não usar 0.0: o relógio monotônico conta desde que a
        # máquina ligou; logo depois de um reinício ele está abaixo de 60 e o R2
        # aparecia "fora" no primeiro minuto sem ser conferido.
        self.quando: float | None = None
        self.ok = False

    def conferir(self) -> bool:
        if self.quando is None or time.monotonic() - self.quando > 60:
            from app.nucleo.midia import armazenamento_midias

            try:
                self.ok = armazenamento_midias().ok()
            except Exception:  # configuração errada (ex.: Account ID inválido) = "fora"
                self.ok = False
            self.quando = time.monotonic()
        return self.ok


def _configurar_logs() -> None:
    """Os registros do estúdio (backup, fila) aparecem no log do Render, sem segredos."""
    log = logging.getLogger("estudio")
    if not log.handlers:
        saida = logging.StreamHandler()
        saida.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        log.addHandler(saida)
        log.setLevel(logging.INFO)
        log.propagate = False


def criar_app() -> FastAPI:
    config = obter_config()
    _configurar_logs()
    estado: dict[str, Trabalhador | None] = {"trabalhador": None}
    backup: dict[str, Agendador | None] = {"agendador": None}
    cache_r2 = _CacheR2()

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        # O trabalhador da fila roda junto com o servidor (decisão de Eri, 25/10).
        if config.trabalhador_ativo:
            from app.geracao.executores import executar_tipo_foto

            # Foto ligada à geração (passo 1.2, parte 4); vídeo, voz e arte vêm depois.
            trabalhador = Trabalhador({**EXECUTORES, "foto": executar_tipo_foto})
            trabalhador.iniciar()
            estado["trabalhador"] = trabalhador
        # Backup diário do banco para o R2 (tarefa 13), também sem custo extra.
        if config.backup_ativo and config.r2_configurado:
            from app.nucleo.backup import criar_agendador

            try:
                agendador = criar_agendador()
                agendador.iniciar()
                backup["agendador"] = agendador
                logging.getLogger("estudio.backup").info("agendador do backup iniciado")
            except Exception:  # R2 mal configurado não pode impedir o servidor de subir
                logging.getLogger("estudio.backup").exception("backup não iniciou")
        yield
        if estado["trabalhador"]:
            estado["trabalhador"].parar()
        if backup["agendador"]:
            backup["agendador"].parar()

    app = FastAPI(
        title="Estúdio W-orld",
        version=config.versao,
        docs_url=None if config.ambiente == "producao" else "/docs",
        redoc_url=None,
        lifespan=ciclo_de_vida,
    )

    app.include_router(rota_interna)
    app.add_exception_handler(ErroNucleo, resposta_de_erro)

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
        if config.backup_ativo and config.r2_configurado:
            agendador = backup["agendador"]
            componentes["backup"] = "ok" if agendador and agendador.em_dia() else "atrasado"
        tudo_ok = all(v == "ok" for v in componentes.values())
        # O código HTTP depende só do que é nosso (processo, banco, fila). Se o R2 cair ou
        # o backup atrasar, o /saude mostra "degradado", mas o Render não derruba o servidor.
        essenciais_ok = all(v == "ok" for k, v in componentes.items() if k not in ("r2", "backup"))
        return JSONResponse(
            status_code=200 if essenciais_ok else 503,
            content={"status": "ok" if tudo_ok else "degradado", "componentes": componentes},
        )

    return app


app = criar_app()
