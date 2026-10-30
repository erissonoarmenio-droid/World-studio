"""Contrato comum dos nós de geração (spec `geracao` parte 1).

Fluxo de todo nó:
    entrada → montar_pedido() → checar() → [bloqueado | aprovação → enviar() → conferir()]

`montar_pedido` e `checar` não usam rede: tudo que trava o pedido é testável sem gastar.
Cada regra guarda a ORIGEM (o erro real que a criou, ex. "E11 — 29/10"), para que se
saiba por que ela existe e não seja afrouxada sem motivo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Nivel = Literal["bloqueia", "aviso"]


class SemAprovacao(Exception):
    """Tentativa de enviar um pedido sem o ok explícito de quem paga."""


class PedidoBloqueado(Exception):
    """O pedido falhou numa regra que bloqueia; nada foi enviado nem gasto."""

    def __init__(self, relatorio: Relatorio) -> None:
        self.relatorio = relatorio
        super().__init__(relatorio.resumo())


class Entrada(BaseModel):
    """Base das entradas dos nós: só o que muda a cada pedido. Campos extras são recusados."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Pedido(BaseModel):
    """O que vai para o fornecedor, já montado pelo nó (partes fixas + entradas)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    no: str
    fornecedor: str
    modelo: str
    entrada: Any
    prompt: str = ""
    payload: dict[str, Any] = {}
    custo_estimado: Decimal


@dataclass(frozen=True)
class Regra:
    """Uma linha FAÇA / NÃO FAÇA. `checar` devolve True quando o pedido cumpre a regra."""

    id: str
    nivel: Nivel
    faca: str
    origem: str
    checar: Callable[[Pedido], bool]


@dataclass(frozen=True)
class Falha:
    regra_id: str
    nivel: Nivel
    faca: str
    origem: str
    detalhe: str = ""


@dataclass
class Relatorio:
    no: str
    falhas: list[Falha] = field(default_factory=list)
    conferidas: int = 0

    @property
    def bloqueado(self) -> bool:
        return any(f.nivel == "bloqueia" for f in self.falhas)

    @property
    def avisos(self) -> list[Falha]:
        return [f for f in self.falhas if f.nivel == "aviso"]

    def resumo(self) -> str:
        if not self.falhas:
            return f"{self.no}: {self.conferidas} regras ok"
        linhas = [f"{self.no}: {'BLOQUEADO' if self.bloqueado else 'ok com avisos'}"]
        for f in self.falhas:
            extra = f" ({f.detalhe})" if f.detalhe else ""
            linhas.append(f"- [{f.nivel}] {f.regra_id}: {f.faca}{extra} — origem {f.origem}")
        return "\n".join(linhas)


@dataclass(frozen=True)
class Veredito:
    """Resultado do juiz depois da geração."""

    aprovado: bool
    motivos: tuple[str, ...] = ()
    notas: dict[str, Any] = field(default_factory=dict)


def normalizar_texto(texto: str) -> str:
    """Aspas curvas viram retas, espaços repetidos viram um só, Unicode em forma NFC.

    Sem isso, um prompt com “fala” (aspas tipográficas) escaparia da regra das aspas.
    """
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.translate(str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"}))
    return re.sub(r"[ \t]+", " ", texto).strip()


def checar_regras(no: str, regras: Sequence[Regra], pedido: Pedido) -> Relatorio:
    """Roda todas as regras. Uma regra que quebra ao checar conta como falha que bloqueia:
    na dúvida, não gasta."""
    relatorio = Relatorio(no=no, conferidas=len(regras))
    for regra in regras:
        try:
            ok = bool(regra.checar(pedido))
            detalhe = ""
        except Exception as erro:  # regra com defeito nunca libera o envio
            ok, detalhe = False, f"erro ao checar: {type(erro).__name__}"
            relatorio.falhas.append(Falha(regra.id, "bloqueia", regra.faca, regra.origem, detalhe))
            continue
        if not ok:
            relatorio.falhas.append(Falha(regra.id, regra.nivel, regra.faca, regra.origem, detalhe))
    return relatorio


class No:
    """Base dos nós. Cada nó define `nome`, `regras` e `montar_pedido`."""

    nome: str = "no"
    regras: tuple[Regra, ...] = ()

    def montar_pedido(self, entrada: Entrada) -> Pedido:  # pragma: no cover - abstrato
        raise NotImplementedError

    def checar(self, pedido: Pedido) -> Relatorio:
        return checar_regras(self.nome, self.regras, pedido)

    def preparar(self, entrada: Entrada) -> tuple[Pedido, Relatorio]:
        """Monta e checa; levanta PedidoBloqueado se alguma regra que bloqueia falhar."""
        pedido = self.montar_pedido(entrada)
        relatorio = self.checar(pedido)
        if relatorio.bloqueado:
            raise PedidoBloqueado(relatorio)
        return pedido, relatorio
