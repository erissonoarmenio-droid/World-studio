"""Google Gemini API: foto (Nano Banana), voz (TTS) e juiz.

Dois modos:
- direto: generateContent devolve o resultado na hora (Resposta pronta, sem id);
- lote (E16): batchGenerateContent devolve o nome do lote (id) e o resultado sai na consulta.
  Metade do preço e ~2 min; é o modo padrão das fotos.
"""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import ErroFornecedor, Resposta, chamar
from app.geracao.nos.base import Pedido

BASE = "https://generativelanguage.googleapis.com/v1beta"
TEMPO = httpx.Timeout(400.0, connect=15.0)  # foto 2K e TTS podem passar de 60 s


def _partes(resposta: dict) -> list:
    candidatos = resposta.get("candidates") or []
    if not candidatos:
        return []
    return (candidatos[0].get("content") or {}).get("parts") or []


class Google:
    nome = "google"

    def __init__(
        self,
        chave: SecretStr,
        modo: Literal["direto", "lote"] = "direto",
        cliente: httpx.Client | None = None,
    ) -> None:
        self.modo = modo
        self._cliente = cliente or httpx.Client(timeout=TEMPO)
        self._cabecalho = {"x-goog-api-key": chave.get_secret_value()}

    def enviar(self, pedido: Pedido) -> Resposta:
        if self.modo == "lote":
            corpo = {
                "batch": {
                    "display_name": f"{pedido.no}-world",
                    "input_config": {
                        "requests": {
                            "requests": [{"request": pedido.payload, "metadata": {"key": "1"}}]
                        }
                    },
                }
            }
            r = chamar(
                self._cliente,
                "POST",
                f"{BASE}/models/{pedido.modelo}:batchGenerateContent",
                json=corpo,
                headers=self._cabecalho,
            )
            nome = r.json().get("name")
            if not nome:
                raise ErroFornecedor("o Google respondeu sem o nome do lote", incerto=True)
            return Resposta(estado="na_fila", id=nome)
        r = chamar(
            self._cliente,
            "POST",
            f"{BASE}/models/{pedido.modelo}:generateContent",
            json=pedido.payload,
            headers=self._cabecalho,
        )
        return self._de_resposta(r.json())

    def consultar(self, id_trabalho: str) -> Resposta:
        r = chamar(self._cliente, "GET", f"{BASE}/{id_trabalho}", headers=self._cabecalho)
        lote = r.json()
        estado = (lote.get("metadata") or {}).get("state") or lote.get("state", "")
        if lote.get("error") or estado in ("BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED"):
            return Resposta(estado="falhou", id=id_trabalho, erro=str(lote.get("error", estado)))
        if not lote.get("done") and estado != "BATCH_STATE_SUCCEEDED":
            return Resposta(estado="na_fila", id=id_trabalho)
        respostas = ((lote.get("response") or {}).get("inlinedResponses") or {}).get(
            "inlinedResponses"
        ) or []
        if not respostas:
            return Resposta(estado="falhou", id=id_trabalho, erro="lote pronto sem resposta")
        primeira = respostas[0]
        if primeira.get("error"):
            return Resposta(estado="falhou", id=id_trabalho, erro=str(primeira["error"]))
        resposta = self._de_resposta(primeira.get("response") or {})
        return Resposta(resposta.estado, id_trabalho, resposta.saidas, resposta.erro)

    @staticmethod
    def _de_resposta(corpo: dict) -> Resposta:
        partes = _partes(corpo)
        if not partes:
            motivo = ((corpo.get("candidates") or [{}])[0]).get("finishReason", "sem conteúdo")
            return Resposta(estado="falhou", erro=f"sem resultado ({motivo})")
        return Resposta(estado="pronto", saidas=partes)
