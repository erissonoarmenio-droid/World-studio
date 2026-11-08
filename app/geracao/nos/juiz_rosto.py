"""Juiz de rosto: a pessoa real se reconheceria nesta foto? (07/11)

Por quê: o juiz de foto antigo dá uma nota geral de "mesma pessoa" (0–10) e deixou passar o
rosto afinando (E39) e a cabeça inflando (E40) — no teste do Eri só o olho dele pegou. Este juiz
pergunta o que muda de fato: largura e comprimento do rosto, tamanho da cabeça, tom de pele,
traços e idade. Quem aprova é o código (Regra 7: o modelo dá as respostas, a regra decide).

Uso: depois da trava do rosto, uma chamada DIRETA ao Gemini (só leitura, ~US$ 0,003, segundos).
Não reenvia nada sozinho: só marca aprovada/reprovada com os motivos para o Eri ver.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.geracao.nos.base import Pedido, Veredito

MODELO = "gemini-3.8-flash"
CUSTO = Decimal("0.003")
NOTA_MINIMA = 8
IDADE_TOLERANCIA = 4

PROMPT = (
    "Images 1 to {n} are real photos of one person (reference). The LAST image is an "
    "AI-generated photo that must show the same person. Compare only the face and head, "
    "ignoring clothes, background, light and expression. Be strict: answer as if you had to "
    "decide whether this person's friends would recognise them at once. Reply ONLY with JSON: "
    '{{"reconheceria": 0-10, "largura_rosto": "mais_fino"|"igual"|"mais_largo", '
    '"comprimento_rosto": "mais_curto"|"igual"|"mais_longo", '
    '"cabeca_vs_corpo": "menor"|"igual"|"maior", '
    '"tom_pele": "mais_claro"|"igual"|"mais_escuro"|"mais_oliva"|"mais_rosado", '
    '"olhos": "igual"|"diferente", "nariz": "igual"|"diferente", "boca": "igual"|"diferente", '
    '"cabelo": "igual"|"diferente", "idade_ref": n, "idade_foto": n, '
    '"diferencas": ["short description of each visible difference"]}}'
)

CAMPOS_IGUAIS = (
    ("largura_rosto", "rosto"),
    ("comprimento_rosto", "comprimento do rosto"),
    ("cabeca_vs_corpo", "cabeça"),
    ("tom_pele", "pele"),
    ("olhos", "olhos"),
    ("nariz", "nariz"),
    ("boca", "boca"),
)


def pedido_rosto(reais: list[tuple[str, str]], foto: tuple[str, str]) -> Pedido:
    """reais/foto = (mime, base64)."""
    partes: list[dict[str, Any]] = [{"text": PROMPT.format(n=len(reais))}]
    partes += [{"inlineData": {"mimeType": m, "data": d}} for m, d in [*reais, foto]]
    return Pedido(
        no="juiz.rosto",
        fornecedor="google",
        modelo=MODELO,
        entrada=None,
        prompt=PROMPT.format(n=len(reais)),
        payload={
            "contents": [{"parts": partes}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},  # E20: responde em segundos
            },
        },
        custo_estimado=CUSTO,
    )


def veredito_rosto(r: dict[str, Any]) -> Veredito:
    motivos: list[str] = []
    nota = r.get("reconheceria")
    if not isinstance(nota, int | float) or nota < NOTA_MINIMA:
        motivos.append(f"reconheceria {nota} < {NOTA_MINIMA}")
    for campo, nome in CAMPOS_IGUAIS:
        valor = r.get(campo)
        if valor != "igual":
            motivos.append(f"{nome}: {str(valor).replace('_', ' ')}")
    ref, foto = r.get("idade_ref"), r.get("idade_foto")
    numeros = isinstance(ref, int | float) and isinstance(foto, int | float)
    if numeros and abs(foto - ref) > IDADE_TOLERANCIA:  # type: ignore[operator]
        motivos.append(f"idade {foto} × {ref}")
    return Veredito(
        not motivos,
        tuple(motivos),
        {"reconheceria": nota, "diferencas": list(r.get("diferencas") or [])[:5]},
    )
