"""Nó rosto_fixo: trava a identidade de uma pessoa real numa foto já gerada (06/11).

Por quê: na foto de cena (cintura para cima, corpo inteiro) o rosto fica pequeno e o modelo
"afina" a pessoa — 3 de 3 no teste do Eri (mídias 16, 18 e 23/24), mesmo com o close aprovado
como referência (cópia de cópia). O close sai fiel; a cena, não.

Método (Sirio: nós fixos + "corrigir só o que precisa, manter todo o resto igual"; Bootcamp:
edição com referência nítida, de frente, mesma luz): uma 2ª passada de edição em cima da foto
pronta, com as FOTOS REAIS do rosto como referência, trocando só o rosto.

- Image 1 = a foto gerada (fica igual: roupa, cabelo, óculos, mãos, fundo, luz, enquadramento).
- Images 2..n = fotos reais do rosto (com consentimento "clone" — o executor confere).
- Mesmo formato da foto de entrada (9:16 ou 3:4), sem recompor.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.geracao.nos.base import Entrada, No, Pedido, Regra, normalizar_texto
from app.geracao.nos.foto import Imagem
from app.geracao.nos.regras import registrar

MODELO = "gemini-nano-banana-2.1"
CUSTO = Decimal("0.04")  # edição 1K; em lote sai pela metade


class EntradaRostoFixo(Entrada):
    base: Imagem  # a foto gerada que vai receber o rosto certo
    rostos: list[Imagem] = Field(min_length=2, max_length=4)  # fotos REAIS do rosto
    tracos: str = Field(min_length=40)  # Fit Check: os traços que mais somem (rosto largo…)
    oculos: str = ""
    formato: Literal["9:16", "3:4"] = "9:16"
    tamanho: Literal["1K", "2K"] = "1K"


def _t(p: Pedido) -> str:
    return normalizar_texto(p.prompt).lower()


REGRAS = registrar(
    "rosto_fixo",
    [
        Regra(
            id="rosto_fixo.so_google",
            nivel="bloqueia",
            faca="Edição de rosto só pelo Google direto.",
            origem="E15 — 30/10",
            checar=lambda p: p.fornecedor == "google",
        ),
        Regra(
            id="rosto_fixo.so_o_rosto",
            nivel="bloqueia",
            faca="Trocar SÓ o rosto; todo o resto da imagem 1 fica igual (roupa, fundo, luz).",
            origem="06/11 — Sirio/Bootcamp: 'manter todo o resto igual'",
            checar=lambda p: "change only the face" in _t(p) and "keep everything else" in _t(p),
        ),
        Regra(
            id="rosto_fixo.nao_afinar",
            nivel="bloqueia",
            faca="Dizer que não pode afinar o rosto e travar a pele como nas fotos reais.",
            origem="06/11 — rosto do Eri afinou em 3 de 3 fotos de cena",
            checar=lambda p: "do not slim" in _t(p) and "skin tone exactly" in _t(p),
        ),
        Regra(
            id="rosto_fixo.mesmo_formato",
            nivel="bloqueia",
            faca="Mesmo formato da foto de entrada (não recompor o quadro).",
            origem="06/11",
            checar=lambda p: (
                p.payload["generationConfig"]["imageConfig"]["aspectRatio"] == p.entrada.formato
            ),
        ),
    ],
)


class NoRostoFixo(No):
    nome = "rosto_fixo"
    regras = REGRAS

    def montar_pedido(self, e: EntradaRostoFixo, fornecedor: str = "google") -> Pedido:
        n = len(e.rostos) + 1
        oculos = (
            f" Keep the same eyeglasses ({e.oculos}) exactly as in image 1, with no text or logo."
            if e.oculos
            else ""
        )
        prompt = (
            f"Edit image 1. Images 2 to {n} are real photos of the same person's face (identity "
            "reference, with consent). Change only the face of the person in image 1 so that "
            f"it matches the real person in images 2 to {n} exactly: face shape and width, "
            "cheeks, jawline, nose, lips, eyebrows, eyes, beard and skin. Key features: "
            f"{e.tracos.strip().rstrip('.')}. Do not slim, lengthen or beautify the face; keep "
            "the full cheeks and the wide jaw of the real photos. Keep the skin tone exactly as "
            f"in images 2 to {n}, with the same warmth and natural redness.{oculos} Keep "
            "everything else in image 1 identical: hair, clothing and every detail of the "
            "garment, pose, hands, body, background, lighting, colours, framing and camera "
            "angle. Same expression direction and head position as in image 1. Photorealistic, "
            "natural skin texture, no beauty filter, no text, no logos."
        )
        imagens = [e.base, *e.rostos]
        partes = [{"text": prompt}] + [
            {"inlineData": {"mimeType": i.mime, "data": i.dados_b64}} for i in imagens
        ]
        payload = {
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": e.formato, "imageSize": e.tamanho},
            },
        }
        return Pedido(
            no=self.nome,
            fornecedor=fornecedor,
            modelo=MODELO,
            entrada=e,
            prompt=prompt,
            payload=payload,
            custo_estimado=CUSTO,
        )
