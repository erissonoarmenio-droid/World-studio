"""Tein (plataforma do Sirio): uma API para Seedance, Nano Banana, Gemini etc.

POST /v1/generate → 202 {id, status}; GET /v1/jobs/{id} até succeeded → data[].url e
usage.cost (o custo cobrado de verdade); POST /v1/uploads (multipart `file`) → url.
Termos (lidos em 30/10): a Tein não treina com o nosso conteúdo; o resultado é nosso;
apaga entradas e saídas em 14 dias (baixar na hora); crédito pré-pago sem devolução;
rosto de pessoa real só com consentimento documentado.
"""

from __future__ import annotations

import hashlib
import json

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import TEMPO_LIMITE, ErroFornecedor, Resposta, chamar
from app.geracao.nos.base import Pedido

BASE = "https://api.tein.ai/v1"
PRONTO = {"succeeded"}
FALHOU = {"failed", "expired", "cancelled"}


class Tein:
    nome = "tein"

    def __init__(self, chave: SecretStr, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente or httpx.Client(timeout=TEMPO_LIMITE)
        self._cabecalho = {"Authorization": f"Bearer {chave.get_secret_value()}"}

    def enviar(self, pedido: Pedido) -> Resposta:
        corpo = dict(pedido.payload)
        # Mesmo pedido = mesma chave: a Tein não cobra duas vezes se o envio se repetir.
        corpo.setdefault(
            "idempotency_key",
            hashlib.sha256(json.dumps(pedido.payload, sort_keys=True).encode()).hexdigest()[:40],
        )
        r = chamar(self._cliente, "POST", f"{BASE}/generate", json=corpo, headers=self._cabecalho)
        dados = r.json()
        if not dados.get("id"):
            raise ErroFornecedor("a Tein respondeu sem id", status=r.status_code, incerto=True)
        return self._resposta(dados)

    def consultar(self, id_trabalho: str) -> Resposta:
        r = chamar(self._cliente, "GET", f"{BASE}/jobs/{id_trabalho}", headers=self._cabecalho)
        return self._resposta(r.json())

    def subir_midia(self, conteudo: bytes, nome_arquivo: str, tipo: str) -> str:
        r = chamar(
            self._cliente,
            "POST",
            f"{BASE}/uploads",
            files={"file": (nome_arquivo, conteudo, tipo)},
            headers=self._cabecalho,
        )
        url = r.json().get("url")
        if not url:
            raise ErroFornecedor("upload sem URL na resposta", incerto=False)
        return url

    @staticmethod
    def _resposta(dados: dict) -> Resposta:
        status = str(dados.get("status", "")).lower()
        estado = "pronto" if status in PRONTO else "falhou" if status in FALHOU else "na_fila"
        saidas = [d.get("url") or d for d in (dados.get("data") or [])]
        erro = dados.get("error")
        return Resposta(
            estado=estado,
            id=dados.get("id"),
            saidas=saidas,
            erro=json.dumps(erro, ensure_ascii=False) if erro else "",
            custo=(dados.get("usage") or {}).get("cost"),
        )
