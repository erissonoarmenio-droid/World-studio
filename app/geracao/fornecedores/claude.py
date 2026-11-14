"""Claude (API da Anthropic): o cérebro do diretor. Só texto/JSON, resposta imediata.

Chave só pelo config (ANTHROPIC_API_KEY); nunca em log ou erro.
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import ErroFornecedor, chamar

URL = "https://api.anthropic.com/v1/messages"
MODELO = "claude-sonnet-5-5"
VERSAO = "2023-06-01"
ESPERAS = (2.0, 8.0)  # segundos antes da 2ª e da 3ª tentativa
CHEIO = (429, 500, 502, 503, 529)  # limite de uso ou API sobrecarregada: nada foi feito


class ClienteClaude:
    nome = "claude"

    def __init__(
        self,
        chave: SecretStr,
        cliente: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self._chave = chave
        self._http = cliente or httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))
        self._dormir = dormir

    def _chamar(self, **kwargs: Any) -> httpx.Response:
        """Até 3 tentativas quando a API responde "cheia" (429/5xx/529).

        Diferente da geração de foto e vídeo (envio único, nunca reenviar): aqui é só texto,
        a chamada recusada não criou nada e não foi cobrada. Sem isso, um pico de uso da API
        derrubava o roteiro inteiro e a lojista ficava sem resposta."""
        for espera in (*ESPERAS, None):
            try:
                return chamar(self._http, "POST", URL, **kwargs)
            except ErroFornecedor as erro:
                if espera is None or erro.status not in CHEIO:
                    raise
                self._dormir(espera)
        raise AssertionError("inalcançável")  # pragma: no cover

    def json(
        self,
        sistema: str,
        texto: str,
        imagens: list[tuple[bytes, str]] | None = None,
        modelo: str = MODELO,
        max_tokens: int = 16000,  # 2 roteiros completos: 4000 (09/11) e 8000 (11/11) cortaram
    ) -> dict[str, Any]:
        """Manda texto (+ imagens) e devolve o JSON da resposta (o primeiro objeto {...})."""
        conteudo: list[dict[str, Any]] = []
        for dados, tipo in imagens or []:
            conteudo.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": tipo,
                        "data": base64.b64encode(dados).decode(),
                    },
                }
            )
        conteudo.append({"type": "text", "text": texto})
        resposta = self._chamar(
            headers={
                "x-api-key": self._chave.get_secret_value(),
                "anthropic-version": VERSAO,
                "content-type": "application/json",
            },
            json={
                "model": modelo,
                "max_tokens": max_tokens,
                "system": sistema,
                "messages": [{"role": "user", "content": conteudo}],
            },
        )
        corpo = resposta.json()
        texto_resposta = "".join(
            b.get("text", "") for b in corpo.get("content", []) if b.get("type") == "text"
        )
        if corpo.get("stop_reason") == "max_tokens":
            inicio = texto_resposta[:200].replace("\n", " ")
            raise ErroFornecedor(
                f"resposta do Claude cortada no limite de {max_tokens} tokens "
                f"({len(texto_resposta)} caracteres; começo: {inicio!r})",
                incerto=False,
            )
        return extrair_json(texto_resposta)


def extrair_json(texto: str) -> dict[str, Any]:
    """Pega o JSON da resposta, mesmo se vier dentro de ```json ... ```."""
    bloco = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.S)
    bruto = bloco.group(1) if bloco else texto[texto.find("{") : texto.rfind("}") + 1]
    try:
        return json.loads(bruto)
    except json.JSONDecodeError as erro:
        raise ErroFornecedor("resposta do Claude sem JSON válido", incerto=False) from erro
