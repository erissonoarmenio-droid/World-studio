"""Nó foto de produto (sem influencer): 1) extrair a peça → 2) a peça numa cena.

Frente "foto de produto" (01/11). Testado com a camisa terracota de Eri: 2 de 2 extrações e
6 de 6 cenas fiéis de primeira (bolsos, botões, etiquetas reais, nada inventado), ≈ US$ 0,02
por foto no Google em lote. Eri: "pode botar no sistema e sugerir também pro lojista".

O lojista só manda a foto da peça (cabide, manequim, print). A influencer sugere na conversa
as cenas que existem (nunca como menu) — ver `sugestao`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.geracao.nos.base import Entrada, No, Pedido, Regra, normalizar_texto
from app.geracao.nos.foto import Imagem
from app.geracao.nos.regras import registrar

MODELO = "gemini-nano-banana-2.1"
CUSTO = Decimal("0.02")  # por imagem, 1K em lote (metade do direto), medido 01/11

EXTRAIR = (
    "Image 1 is a phone photo of a real {peca_nome} for sale. Extract ONLY the {peca_nome} and "
    "show it as a clean flat lay product photo, seen from directly above, lying perfectly flat "
    "and neatly arranged, front fully visible, on a plain light grey seamless background, soft "
    "even daylight, no hanger, no person, no props. Keep the {peca_nome} EXACTLY as in image 1: "
    "{detalhes}. Keep the existing labels as they are; do not add any new text, logo, pattern, "
    "pocket or detail. Photorealistic, true colours, high detail."
)
TRAVA = (
    "Image 1 = THE EXACT {peca_nome_maiusc} for sale. Keep it EXACTLY as in image 1: {detalhes}. "
    "Keep the existing labels as they are; do not add any new text, logo, pattern, pocket or "
    "detail. "
)
REAL = (
    "Looks like a real, slightly imperfect smartphone photo taken by the shop owner for "
    "Instagram: natural light, true colours, real fabric creases and texture, no CGI look, no "
    "studio lighting, no text, no watermark, no other logos. "
)
CENAS = {  # testadas em 01/11 (2 de 2 aprovadas cada)
    "cama": "SCENE: top-down POV smartphone photo of a bed with soft white rumpled cotton sheets "
    "in morning window light. Two hands (exactly two hands, five fingers each, natural short "
    "nails, no rings) hold the {peca_nome} open by its shoulders just above the sheet, front "
    "facing the camera, filling most of the frame.",
    "mesa": "SCENE: the {peca_nome} neatly folded on a warm natural wooden table, its main "
    "details visible on top, photographed with a phone from slightly above at an angle, soft "
    "morning window light from the left; at the edge of the frame a plain white ceramic mug and "
    "a small green plant, slightly out of focus.",
    "arara": "SCENE: the {peca_nome} on a simple wooden hanger hanging on a thin black metal "
    "clothing rack in a bright minimal clothing boutique with white walls; in the soft "
    "background a green velvet armchair and a round mirror, slightly out of focus; phone photo "
    "at chest height, straight on, the front fully visible and centred.",
}
Cena = Literal["cama", "mesa", "arara", "livre"]
NOMES_CENA = {"cama": "na cama", "mesa": "dobrada na mesa", "arara": "pendurada na arara"}


class EntradaProduto(Entrada):
    etapa: Literal["extrair", "cena"]
    foto: Imagem  # extrair: foto do lojista · cena: a peça já extraída e aprovada
    peca_nome: str = Field(min_length=3)  # "shirt"
    detalhes: str = Field(min_length=20)  # cor, tecido, gola, bolsos, botões, etiquetas
    cena: Cena = "cama"
    cena_livre: str = ""  # quando o lojista pede outro lugar ("no chão com um tênis do lado")
    proporcao: Literal["4:5", "1:1", "9:16"] = "4:5"

    @model_validator(mode="after")
    def _cena_livre_coerente(self) -> EntradaProduto:
        if self.etapa == "cena" and self.cena == "livre" and len(self.cena_livre) < 20:
            raise ValueError("cena livre precisa da descrição do lugar")
        return self


def _t(p: Pedido) -> str:
    return normalizar_texto(p.prompt).lower()


def _e(p: Pedido) -> EntradaProduto:
    return p.entrada


REGRAS = registrar(
    "foto_produto",
    [
        Regra(
            id="produto.google_direto",
            nivel="bloqueia",
            faca="Foto sempre no Google direto, nunca Atlas.",
            origem="E15 — 30/10 (Atlas inventou bolso)",
            checar=lambda p: p.fornecedor == "google" and p.modelo == MODELO,
        ),
        Regra(
            id="produto.peca_exata",
            nivel="bloqueia",
            faca="A peça vai travada: 'EXACTLY as in image 1' + os detalhes dela.",
            origem="frente foto de produto — 01/11 (8 de 8 fiéis com a trava)",
            checar=lambda p: "exactly as in image 1" in _t(p) and _e(p).detalhes.lower() in _t(p),
        ),
        Regra(
            id="produto.sem_texto_novo",
            nivel="bloqueia",
            faca="Só as etiquetas reais da peça; nenhum texto, logo ou detalhe novo.",
            origem="juiz de foto (texto/logo inventado reprova) — 01/11",
            checar=lambda p: "do not add any new text" in _t(p),
        ),
        Regra(
            id="produto.maos_cinco_dedos",
            nivel="bloqueia",
            faca='Cena com mãos: "five fingers".',
            origem="E6/E12 — 29/10",
            checar=lambda p: "hand" not in _t(p) or "five fingers" in _t(p),
        ),
        Regra(
            id="produto.sem_pessoa_na_extracao",
            nivel="bloqueia",
            faca="Na extração: sem cabide, sem pessoa, fundo liso.",
            origem="workflow Thiago Vortex + teste 01/11",
            checar=lambda p: _e(p).etapa != "extrair" or "no person" in _t(p),
        ),
        Regra(
            id="produto.foto_real",
            nivel="bloqueia",
            faca="Cena com cara de foto real de celular do lojista (sem CGI, sem estúdio).",
            origem="Método W-orld (realismo) — 01/11",
            checar=lambda p: (
                _e(p).etapa != "cena" or "real, slightly imperfect smartphone" in _t(p)
            ),
        ),
    ],
)


class NoFotoProduto(No):
    nome = "foto_produto"
    regras = REGRAS

    def montar_pedido(self, entrada: EntradaProduto, fornecedor: str = "google") -> Pedido:
        d = entrada.detalhes.strip().rstrip(".")
        if entrada.etapa == "extrair":
            prompt = EXTRAIR.format(peca_nome=entrada.peca_nome, detalhes=d)
        else:
            cena = (
                f"SCENE: {entrada.cena_livre.strip()}"
                if entrada.cena == "livre"
                else CENAS[entrada.cena].format(peca_nome=entrada.peca_nome)
            )
            if entrada.cena == "livre" and "hand" in cena.lower():
                cena += " Exactly two hands, five fingers each."
            prompt = (
                TRAVA.format(peca_nome_maiusc=entrada.peca_nome.upper(), detalhes=d) + REAL + cena
            )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": entrada.foto.mime,
                                "data": entrada.foto.dados_b64,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": entrada.proporcao, "imageSize": "1K"},
            },
        }
        return Pedido(
            no=self.nome,
            fornecedor=fornecedor,
            modelo=MODELO,
            entrada=entrada,
            prompt=prompt,
            payload=payload,
            custo_estimado=CUSTO,
        )


def sugestao(nome_peca_pt: str, ja_feitas: tuple[str, ...] = ()) -> str:
    """Frase natural da influencer oferecendo fotos só da peça (Eri, 01/11: 'sugerir pro lojista').

    Uma ideia por vez, sem menu; varia conforme o que a loja já recebeu."""
    restantes = [c for c in ("cama", "mesa", "arara") if c not in ja_feitas] or ["cama"]
    a, b = (restantes + restantes)[:2]
    if a == b:
        return (
            f"Ah, e se quiser eu faço também umas fotos só da {nome_peca_pt}, {NOMES_CENA[a]}, "
            "bem com cara de foto de celular. Fica ótimo pro feed!"
        )
    return (
        f"Ah, e se quiser eu faço também umas fotos só da {nome_peca_pt}, tipo {NOMES_CENA[a]} "
        f"ou {NOMES_CENA[b]}, bem com cara de foto de celular. Fica ótimo pro feed, quer?"
    )
