"""Juiz cego (E29, 01/11): julga o vídeo como um story qualquer de loja, sem dizer que é nosso
nem que é IA. O juiz antigo sabia que era teste de IA e dava sempre 6.

Calibrado em 01/11 com 7 vídeos × 2 rodadas, contra o olho de Eri:
- aprovados por Eri (v3, sofá ×2): pessoa real 98–100, voz 9–10, corpo 10
- "bom mas robótico" (2.5 v1/v2): pessoa real 95, **voz 4–7**, corpo 8–9
- reprovados (2.0 fast ×2): pessoa real 5–15, voz 2–4, corpo 2–3
A voz é o que separa "bom" de "robótico"; por isso a régua exige voz ≥ 8.
Gemini 3.8 Flash, pensamento 0, vídeo reduzido (360 px, 15 qps, ~0,5 MB). Custo: centavos.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

MODELO = "gemini-3.8-flash"
PROMPT = """This is a short vertical video posted as an Instagram story by a small Brazilian clothing store.
Watch and listen carefully, like a demanding social media viewer. Answer ONLY with JSON:
{"filmado_por_pessoa_real_0a100": <chance that a real person filmed this with a phone, 0-100>,
 "voz_natural_0a10": <does the voice sound like a real person talking casually>,
 "corpo_natural_0a10": <body, face and gestures move like a real person>,
 "camera_real_0a10": <looks like a friend filming with a phone>,
 "pararia_de_rolar_0a10": <would you stop scrolling to watch>,
 "momentos_estranhos": [{"segundo": <s>, "o_que": "<short, in Portuguese>"}],
 "veredito": "<one sentence in Portuguese>"}"""  # noqa: E501

REGUA = {
    "filmado_por_pessoa_real_0a100": 90,
    "voz_natural_0a10": 8,
    "corpo_natural_0a10": 8,
    "camera_real_0a10": 8,
}


def payload(video_mp4: bytes) -> dict[str, Any]:
    return {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "video/mp4",
                            "data": base64.b64encode(video_mp4).decode(),
                        }
                    },
                    {"text": PROMPT},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }


@dataclass(frozen=True)
class VereditoCego:
    aprovado: bool
    motivos: tuple[str, ...]
    notas: dict[str, Any]


def julgar(notas: dict[str, Any]) -> VereditoCego:
    motivos = tuple(
        f"{campo} {notas.get(campo)} < {minimo}"
        for campo, minimo in REGUA.items()
        if float(notas.get(campo, 0)) < minimo
    )
    return VereditoCego(not motivos, motivos, notas)


def melhor(vereditos: list[VereditoCego]) -> VereditoCego | None:
    """Entre as versões aprovadas, a que mais prende ("pararia de rolar")."""
    aprovados = [v for v in vereditos if v.aprovado]
    return max(
        aprovados, key=lambda v: float(v.notas.get("pararia_de_rolar_0a10", 0)), default=None
    )
