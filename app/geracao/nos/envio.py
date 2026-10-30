"""Envio único com aprovação (regra do Sirio: um pedido por geração, sem reenvio sozinho).

    No.preparar(entrada) → (pedido, relatório)   # sem rede, sem gasto
    enviar(no, pedido, aprovacao, fornecedor, registro)   # gasta, uma vez

- Sem aprovação, ou custo acima do aprovado → SemAprovacao (nada sai).
- As regras rodam de novo aqui: pedido mexido depois de checado não passa.
- O registro marca o pedido ANTES da chamada; a segunda chamada do mesmo pedido só consulta
  o status pelo id. Se a primeira deu erro incerto (5xx, tempo esgotado) e não há id, para e
  pede conferência humana no painel do fornecedor — nunca reenvia sozinho.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from app.geracao.fornecedores.base import ErroFornecedor, Fornecedor, Resposta
from app.geracao.nos.base import No, Pedido, PedidoBloqueado, SemAprovacao


class EnvioIncerto(Exception):
    """O pedido já saiu antes e o fornecedor não confirmou; conferir antes de qualquer reenvio."""


@dataclass(frozen=True)
class Aprovacao:
    por: str  # quem aprovou (ex.: "eri", "loja:12")
    custo_max: Decimal  # teto aprovado para este pedido, em US$


@dataclass(frozen=True)
class Envio:
    estado: Literal["enviando", "incerto", "enviado"]
    id_fornecedor: str | None = None


class Registro(Protocol):
    def obter(self, chave: str) -> Envio | None: ...

    def guardar(self, chave: str, envio: Envio) -> None: ...

    def apagar(self, chave: str) -> None: ...


class RegistroEmMemoria:
    """Para testes e scripts. Na fila, o registro é o próprio Trabalho no banco (tarefa 8)."""

    def __init__(self) -> None:
        self._dados: dict[str, Envio] = {}

    def obter(self, chave: str) -> Envio | None:
        return self._dados.get(chave)

    def guardar(self, chave: str, envio: Envio) -> None:
        self._dados[chave] = envio

    def apagar(self, chave: str) -> None:
        self._dados.pop(chave, None)


def chave_do_pedido(pedido: Pedido) -> str:
    corpo = json.dumps(
        {
            "no": pedido.no,
            "fornecedor": pedido.fornecedor,
            "modelo": pedido.modelo,
            "payload": pedido.payload,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(corpo.encode()).hexdigest()


def enviar(
    no: No,
    pedido: Pedido,
    aprovacao: Aprovacao | None,
    fornecedor: Fornecedor,
    registro: Registro,
) -> Resposta:
    if aprovacao is None:
        raise SemAprovacao("pedido sem aprovação: nada foi enviado")
    if pedido.custo_estimado > aprovacao.custo_max:
        raise SemAprovacao(
            f"custo estimado US$ {pedido.custo_estimado} acima do aprovado "
            f"(US$ {aprovacao.custo_max})"
        )
    if fornecedor.nome != pedido.fornecedor:
        raise ValueError(f"pedido é para {pedido.fornecedor}, não para {fornecedor.nome}")
    relatorio = no.checar(pedido)
    if relatorio.bloqueado:
        raise PedidoBloqueado(relatorio)

    chave = chave_do_pedido(pedido)
    anterior = registro.obter(chave)
    if anterior is not None:
        if anterior.id_fornecedor:
            return fornecedor.consultar(anterior.id_fornecedor)
        if anterior.estado == "enviado":
            raise EnvioIncerto("este pedido já foi gerado; o resultado veio na primeira chamada")
        raise EnvioIncerto(
            "este pedido já foi enviado e o fornecedor não confirmou; conferir no painel "
            "antes de reenviar"
        )

    registro.guardar(chave, Envio("enviando"))
    try:
        resposta = fornecedor.enviar(pedido)
    except ErroFornecedor as erro:
        if erro.incerto:
            registro.guardar(chave, Envio("incerto"))
        else:
            registro.apagar(chave)  # recusado com certeza (4xx): nada foi criado
        raise
    except Exception:
        registro.guardar(chave, Envio("incerto"))
        raise
    registro.guardar(chave, Envio("enviado", resposta.id))
    return resposta
