"""Claude (API da Anthropic): o cérebro do diretor. Só texto/JSON, resposta imediata.

Chave só pelo config (ANTHROPIC_API_KEY); nunca em log ou erro.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import ErroFornecedor, chamar

URL = "https://api.anthropic.com/v1/messages"
MODELO = "claude-sonnet-5-5"
VERSAO = "2023-06-01"


class ClienteClaude:
    nome = "claude"

    def __init__(self, chave: SecretStr, cliente: httpx.Client | None = None) -> None:
        self._chave = chave
        self._http = cliente or httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0))

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
        resposta = chamar(
            self._http,
            "POST",
            URL,
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
