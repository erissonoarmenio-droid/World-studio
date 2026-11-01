"""Conferência depois da geração: palavras do roteiro × o que se ouve no vídeo (E11, E33).

O vídeo só vai ao lojista com ≥ 90% das palavras do roteiro (régua do Método W-orld v3).
A transcrição vem do whisper/juiz; aqui só a comparação, sem rede.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

MINIMO = 0.90


def _palavras(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", texto)


@dataclass(frozen=True)
class Conferencia:
    acerto: float
    faltando: tuple[str, ...]
    sobrando: tuple[str, ...]

    @property
    def aprovado(self) -> bool:
        return self.acerto >= MINIMO


def conferir_palavras(roteiro: list[str], ouvido: str) -> Conferencia:
    esperado = _palavras(" ".join(roteiro))
    real = _palavras(ouvido)
    sm = difflib.SequenceMatcher(a=esperado, b=real, autojunk=False)
    faltando: list[str] = []
    sobrando: list[str] = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            faltando += esperado[a1:a2]
        if op in ("insert", "replace"):
            sobrando += real[b1:b2]
    acerto = 1 - len(faltando) / max(len(esperado), 1)
    return Conferencia(round(acerto, 3), tuple(faltando), tuple(sobrando))
