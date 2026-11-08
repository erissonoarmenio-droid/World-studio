"""Nó provador (07/11, E43): veste a peça da loja na FOTO REAL da pessoa, sem gerar outra pessoa.

Por quê (E43): gerar a pessoa do zero e depois "consertar" o rosto é cópia de cópia — em cada
passo o rosto escorrega (idade E42, largura E39/E40, pele E38). No provador o rosto continua
sendo o da foto real: só a roupa e o fundo mudam (Sirio/Bootcamp: "editar, mudar só o que
precisa, manter todo o resto igual").

- Image 1 = foto real da pessoa (de frente, rosto grande; consentimento "clone" — o executor
  confere).
- Images 2..n = fotos da peça real (inteira + detalhe).
- Saída 9:16 (1º quadro do vídeo); o quadro pode ser estendido, a pessoa fica do mesmo tamanho.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.geracao.nos.base import (
    Entrada,
    Genero,
    No,
    Pedido,
    Regra,
    normalizar_texto,
    para_genero,
    tem_palavra_de_idade,
)
from app.geracao.nos.foto import Imagem
from app.geracao.nos.regras import registrar

MODELO = "gemini-nano-banana-2.1"
CUSTO = Decimal("0.04")


class EntradaProvador(Entrada):
    foto_real: Imagem  # foto real da pessoa, de frente
    peca_fotos: list[Imagem] = Field(min_length=1, max_length=3)
    peca: str = Field(min_length=20)  # descrição da peça (ficha do analista-pecas)
    cenario: str = Field(min_length=10)  # fundo novo
    genero: Genero = "mulher"
    formato: Literal["9:16", "3:4"] = "9:16"
    tamanho: Literal["1K", "2K"] = "1K"

    @model_validator(mode="after")
    def _sem_idade(self) -> EntradaProvador:
        if w := tem_palavra_de_idade(self.peca + " " + self.cenario):
            raise ValueError(f"sem idade ou rugas no texto ('{w}'): o rosto é o da foto (E42)")
        return self


def _t(p: Pedido) -> str:
    return normalizar_texto(p.prompt).lower()


REGRAS = registrar(
    "provador",
    [
        Regra(
            id="provador.so_google",
            nivel="bloqueia",
            faca="Provador só pelo Google direto.",
            origem="E15 — 30/10",
            checar=lambda p: p.fornecedor == "google",
        ),
        Regra(
            id="provador.rosto_da_foto",
            nivel="bloqueia",
            faca="O rosto é o da foto real: não refazer, não retocar, não envelhecer.",
            origem="E43 — 07/11 (cópia de cópia mudava o rosto a cada passo)",
            checar=lambda p: (
                ("keep her face exactly as it is in image 1" in _t(p) or "keep his face" in _t(p))
                and "years old" not in _t(p)
            ),
        ),
        Regra(
            id="provador.so_roupa_e_fundo",
            nivel="bloqueia",
            faca="Mudar só a roupa e o fundo; pose, corpo, cabelo e expressão iguais.",
            origem="E43 — 07/11",
            checar=lambda p: "change only two things" in _t(p),
        ),
    ],
)


class NoProvador(No):
    nome = "provador"
    regras = REGRAS

    def montar_pedido(self, e: EntradaProvador, fornecedor: str = "google") -> Pedido:
        n = len(e.peca_fotos) + 1
        quais = "Image 2" if n == 2 else f"Images 2 to {n}"
        prompt = (
            "Edit image 1. Image 1 is a real photo of a real woman (identity, with consent). "
            "Keep her face exactly as it is in image 1: the same face, face shape and width, "
            "skin tone, freckles, eyes, nose, lips, eyebrows, expression, apparent age and head "
            "position; do not regenerate, retouch, beautify, slim, widen or age the face. Keep "
            "her hair, body, pose and hands as in image 1. "
            "Change only two things. (1) Clothing: dress her in the garment from "
            f"{quais} (photos of the real garment): {e.peca.strip().rstrip('.')}. Reproduce "
            "this exact garment (same colour, fabric, pattern, collar, buttons, pockets and "
            "sleeves); do not simplify or redesign any detail; ignore the surface it lies on. "
            f"(2) Background: replace it with {e.cenario.strip().rstrip('.')}, with light that "
            "matches the light on her face. "
            f"Vertical {e.formato} phone photo: if needed, extend the frame naturally around "
            "her, keeping her at the same size. Photorealistic, natural skin texture, no beauty "
            "filter, no text, no logos."
        )
        prompt = para_genero(prompt, e.genero)
        imagens = [e.foto_real, *e.peca_fotos]
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
