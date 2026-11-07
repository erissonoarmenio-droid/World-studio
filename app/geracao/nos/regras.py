"""Registro e listagem das regras FAÇA / NÃO FAÇA de todos os nós.

    uv run python -m app.geracao.nos.regras --listar

Cada nó registra a sua lista ao ser importado. Erro novo medido → regra nova aqui
(com a origem), e um caso de teste que a prove.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from app.geracao.nos.base import Regra

NOS_CONHECIDOS = (
    "video",
    "video_ugc",
    "voz",
    "foto",
    "foto_produto",
    "juiz",
    "vestir",
    "lipsync",
    "influencer",
    "rosto_fixo",
)
_REGISTRO: dict[str, tuple[Regra, ...]] = {}


def registrar(no: str, regras: Sequence[Regra]) -> tuple[Regra, ...]:
    ids = [r.id for r in regras]
    if len(ids) != len(set(ids)):
        raise ValueError(f"regras repetidas no nó {no}")
    _REGISTRO[no] = tuple(regras)
    return _REGISTRO[no]


def carregar_todos() -> dict[str, tuple[Regra, ...]]:
    """Importa os nós que já existem para que registrem as suas regras."""
    for nome in NOS_CONHECIDOS:
        try:
            importlib.import_module(f"app.geracao.nos.{nome}")
        except ModuleNotFoundError as erro:
            if erro.name != f"app.geracao.nos.{nome}":
                raise
    return dict(_REGISTRO)


def listar() -> str:
    linhas = []
    for no, regras in carregar_todos().items():
        linhas.append(f"## nó {no} ({len(regras)} regras)")
        for r in regras:
            linhas.append(f"- [{r.nivel}] {r.id}: {r.faca}  (origem: {r.origem})")
        linhas.append("")
    return "\n".join(linhas) if linhas else "nenhum nó registrado ainda"


if __name__ == "__main__":  # pragma: no cover
    if "--listar" in sys.argv:
        # rodando como __main__ este módulo é carregado duas vezes; os nós registram
        # no módulo importado, então a listagem vem dele.
        from app.geracao.nos import regras as _modulo

        print(_modulo.listar())
    else:
        print("uso: python -m app.geracao.nos.regras --listar")
