"""Decart (Lucy VTON): vestir a peça num vídeo já gerado. Reserva (spec: só com veredito do juiz).

POST /v1/jobs/{modelo} multipart (data = vídeo, reference_image = foto da peça, prompt, seed,
resolution); GET /v1/jobs/{id}; resultado em /v1/jobs/{id}/content.
Termos (30/10): resultado é nosso para uso comercial; a Decart pode treinar com o conteúdo.
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import TEMPO_LIMITE, ErroFornecedor, Resposta, chamar
from app.geracao.nos.base import Pedido

BASE = "https://api.decart.ai/v1/jobs"


class Decart:
    nome = "decart"

    def __init__(self, chave: SecretStr, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente or httpx.Client(timeout=TEMPO_LIMITE)
        self._cabecalho = {"x-api-key": chave.get_secret_value()}

    def enviar(self, pedido: Pedido) -> Resposta:
        """O payload traz `campos` (texto) e `arquivos` {campo: (nome, bytes, tipo)}."""
        arquivos = pedido.payload.get("arquivos") or {}
        if "data" not in arquivos or "reference_image" not in arquivos:
            raise ValueError("o pedido de vestir precisa do vídeo (data) e da foto da peça")
        r = chamar(
            self._cliente,
            "POST",
            f"{BASE}/{pedido.modelo}",
            data={k: str(v) for k, v in (pedido.payload.get("campos") or {}).items()},
            files=arquivos,
            headers=self._cabecalho,
        )
        corpo = r.json()
        id_trabalho = corpo.get("job_id") or corpo.get("id")
        if not id_trabalho:
            raise ErroFornecedor("a Decart respondeu sem id", incerto=True)
        return Resposta(estado="na_fila", id=id_trabalho)

    def consultar(self, id_trabalho: str) -> Resposta:
        r = chamar(self._cliente, "GET", f"{BASE}/{id_trabalho}", headers=self._cabecalho)
        status = str(r.json().get("status", "")).lower()
        if status == "completed":
            return Resposta("pronto", id_trabalho, [f"{BASE}/{id_trabalho}/content"])
        if status in ("failed", "error", "canceled"):
            return Resposta("falhou", id_trabalho, erro=status)
        return Resposta("na_fila", id_trabalho)
