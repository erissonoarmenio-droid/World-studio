"""O que todo fornecedor devolve e como os erros chegam ao envio único.

Só a chamada HTTP mora aqui; quem decide se pode enviar é o nó (regras + aprovação).
Chave: só pelo config, nunca em log ou mensagem de erro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

from app.geracao.nos.base import Pedido

Estado = Literal["na_fila", "pronto", "falhou"]
TEMPO_LIMITE = httpx.Timeout(60.0, connect=15.0)


@dataclass(frozen=True)
class Resposta:
    estado: Estado
    id: str | None = None  # id do trabalho no fornecedor (None quando a resposta é imediata)
    saidas: list[Any] = field(default_factory=list)  # URLs ou partes da resposta
    erro: str = ""
    custo: float | None = None  # custo cobrado informado pelo fornecedor (Tein: usage.cost)


class ErroFornecedor(Exception):
    """`incerto=True`: o pedido pode ter sido criado (5xx, tempo esgotado) — não reenviar."""

    def __init__(self, mensagem: str, *, status: int | None = None, incerto: bool) -> None:
        super().__init__(mensagem)
        self.status = status
        self.incerto = incerto


class Fornecedor(Protocol):
    nome: str

    def enviar(self, pedido: Pedido) -> Resposta: ...

    def consultar(self, id_trabalho: str) -> Resposta: ...


def chamar(cliente: httpx.Client, metodo: str, url: str, **kwargs: Any) -> httpx.Response:
    """Uma chamada, sem nova tentativa. Traduz o erro sem expor cabeçalhos (onde vai a chave)."""
    try:
        resposta = cliente.request(metodo, url, **kwargs)
    except httpx.TimeoutException as erro:
        raise ErroFornecedor(f"tempo esgotado em {url}", incerto=True) from erro
    except httpx.TransportError as erro:
        raise ErroFornecedor(f"falha de conexão em {url}", incerto=True) from erro
    if resposta.status_code >= 500 or resposta.status_code == 429 and metodo == "POST":
        # 429 no POST: em geral não criou, mas alguns fornecedores enfileiram; tratar como incerto
        raise ErroFornecedor(
            f"{resposta.status_code} em {url}", status=resposta.status_code, incerto=True
        )
    if resposta.status_code >= 400:
        corpo = resposta.text[:300]
        raise ErroFornecedor(
            f"{resposta.status_code} em {url}: {corpo}", status=resposta.status_code, incerto=False
        )
    return resposta
