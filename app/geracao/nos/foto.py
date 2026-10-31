"""Nó foto: Nano Banana 2.1 pelo Google direto (nunca Atlas — E15), em lote por padrão (E16).

Blocos do diretor-foto que funcionaram em 29/10 (fotos do Google, juiz: mesma pessoa 6,8,
idade ±1, mãos 5/5): identidade · realismo de celular · peça · cenário · âncora · idade · cena.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.geracao.nos.base import Entrada, No, Pedido, Regra, normalizar_texto
from app.geracao.nos.regras import registrar

MODELO = "gemini-nano-banana-2.1"
CUSTO = {"1K": Decimal("0.04"), "2K": Decimal("0.05")}  # estimado (24/10); o lote custa metade
Tamanho = Literal["1K", "2K"]
Mime = Literal["image/jpeg", "image/png"]

REALISMO = (
    "Photorealistic vertical 9:16 frame that looks like a real smartphone photo: natural skin "
    "texture with pores, slight imperfections, soft real store lighting, no beauty filter, "
    "no text, no logos."
)
ANCORA = " Image 2 = the same woman in an earlier photo of this shoot: match this face exactly."


class Imagem(Entrada):
    mime: Mime = "image/jpeg"
    dados_b64: str = Field(min_length=8)


class EntradaFoto(Entrada):
    influencer: Imagem  # Image 1: referência de identidade
    idade: int = Field(ge=21, le=60)  # influencer sempre adulta (criar-influencer: 25+)
    aparencia: str = ""  # ex.: "dark wavy shoulder-length" (cabelo), da ficha da influencer
    # Biótipo da ficha da influencer (31/10, Eri: "violão marcado"). Quando preenchido, o corpo
    # vem deste texto e não da imagem 1 (a referência antiga tem outro corpo).
    corpo: str = ""
    peca: str  # "She wears ..." (ficha da peça)
    cenario: str  # "a small, cozy Brazilian clothing boutique"
    cena: str  # "SCENE: ..." (formato F1–F12 do diretor-foto)
    sequencia: bool = False  # faz parte de uma série de fotos da mesma pessoa
    e_ancora: bool = False  # é a foto âncora (close do rosto) da série
    ancora: Imagem | None = None  # Image 2: a âncora já aprovada pelo juiz
    cenario_foto: Imagem | None = None  # foto do lugar enviada pela loja (fica igual)
    tamanho: Tamanho = "1K"

    @model_validator(mode="after")
    def _ancora_coerente(self) -> EntradaFoto:
        if self.e_ancora and self.ancora is not None:
            raise ValueError("a foto âncora não leva outra âncora")
        return self


def _texto(p: Pedido) -> str:
    return normalizar_texto(p.prompt).lower()


def _ancora_ok(p: Pedido) -> bool:
    e = p.entrada
    if not e.sequencia or e.e_ancora:
        return True
    return e.ancora is not None and "image 2 = the same woman" in _texto(p)


MAOS_EM_FOCO = ("hands open", "open hand", "finger", "palm", "wave", "waving", "show her hand")


def _maos(p: Pedido, chaves: tuple[str, ...]) -> bool:
    cena = p.entrada.cena.lower()
    return not any(k in cena for k in chaves) or "five fingers" in _texto(p)


def _espelho_ok(p: Pedido) -> bool:
    if p.entrada.cenario_foto is not None:  # espelhos reais da loja: vêm da foto, não inventados
        return True
    t = _texto(p)
    return "mirror" not in t or "one single" in t


REGRAS = registrar(
    "foto",
    [
        Regra(
            id="foto.so_google",
            nivel="bloqueia",
            faca="Foto só pelo Google direto; NUNCA pela Atlas.",
            origem="E15 — 30/10 (Nano Banana da Atlas inventou um bolso; decisão de Eri)",
            checar=lambda p: p.fornecedor == "google",
        ),
        Regra(
            id="foto.ancora_na_sequencia",
            nivel="bloqueia",
            faca="Em série de fotos: gerar a âncora (close do rosto), aprovar, e mandá-la como "
            "Image 2 nas outras.",
            origem="E5 — 29/10 (Atlas com 1 referência: idade 28→32–39, mesma pessoa 3–7/10)",
            checar=_ancora_ok,
        ),
        Regra(
            id="foto.idade_escrita",
            nivel="bloqueia",
            faca='Escrever a idade no prompt ("She is N years old ... do not age her").',
            origem="E5 — 29/10 (com idade escrita: 26–28 contra referência ~27)",
            checar=lambda p: f"{p.entrada.idade} years old" in _texto(p),
        ),
        Regra(
            id="foto.cinco_dedos_nas_maos",
            nivel="bloqueia",
            faca='Cena com as mãos em foco (abertas, dedos, aceno) leva "five fingers".',
            origem="E6 — 29/10 (foto 2 da Atlas com 6 dedos; passou no olho, o juiz pegou)",
            checar=lambda p: _maos(p, MAOS_EM_FOCO),
        ),
        Regra(
            id="foto.cinco_dedos_mao_citada",
            nivel="aviso",
            faca='Qualquer mão citada na cena: melhor pôr "five fingers" (não custa nada).',
            origem="E6 — 29/10",
            checar=lambda p: _maos(p, ("hand",)),
        ),
        Regra(
            id="foto.um_espelho_so",
            nivel="bloqueia",
            faca='Se tiver espelho, escrever "ONE single mirror".',
            origem="E7 — 29/10 (regra 5: espelhos duplicados e reflexo incoerente)",
            checar=_espelho_ok,
        ),
        Regra(
            id="foto.corpo_sem_sexualizar",
            nivel="bloqueia",
            faca="Biótipo descrito de forma natural e de moda; NUNCA termos sexuais ou de nudez.",
            origem="31/10 (corpo novo da influencer) / limites do estúdio: sem conteúdo adulto",
            checar=lambda p: (
                not any(
                    w in p.entrada.corpo.lower()
                    for w in ("sexy", "nude", "naked", "cleavage", "lingerie", "busty", "seductive")
                )
            ),
        ),
        Regra(
            id="foto.sem_texto",
            nivel="bloqueia",
            faca='Sempre "no text, no logos".',
            origem="diretor-foto / juiz de foto (texto e logo inventados reprovam)",
            checar=lambda p: "no text, no logos" in _texto(p),
        ),
    ],
)


class NoFoto(No):
    nome = "foto"
    regras = REGRAS

    def montar_pedido(self, entrada: EntradaFoto, fornecedor: str = "google") -> Pedido:
        cabelo = f"hair ({entrada.aparencia})" if entrada.aparencia else "hair"
        if entrada.corpo:
            corpo = entrada.corpo.strip().rstrip(".")
            mantem = f"Keep her exact face, skin, {cabelo} and age. Body: {corpo}."
        else:
            mantem = f"Keep her exact face, skin, {cabelo}, body and age."
        base = (
            f"Image 1 = the woman (identity reference). {mantem} "
            f"{REALISMO} {entrada.peca.strip()} "
            f"Setting: {entrada.cenario.strip().rstrip('.')}."
        )
        ancora = ANCORA if entrada.ancora is not None else ""
        if entrada.cenario_foto is not None:
            n = 3 if entrada.ancora is not None else 2
            ancora += (
                f" Image {n} = the real store room: keep the room exactly as in image {n} "
                "(same furniture, walls, mirrors and light); mirror reflections show only the "
                "empty room, no people."
            )
        idade = (
            f" She is {entrada.idade} years old; keep her youthful {entrada.idade}-year-old "
            "face, do not age her. "
        )
        prompt = base + ancora + idade + entrada.cena.strip()
        imagens = [entrada.influencer] + ([entrada.ancora] if entrada.ancora else [])
        imagens += [entrada.cenario_foto] if entrada.cenario_foto else []
        partes = [{"text": prompt}] + [
            {"inlineData": {"mimeType": i.mime, "data": i.dados_b64}} for i in imagens
        ]
        payload = {
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": "9:16", "imageSize": entrada.tamanho},
            },
        }
        return Pedido(
            no=self.nome,
            fornecedor=fornecedor,
            modelo=MODELO,
            entrada=entrada,
            prompt=prompt,
            payload=payload,
            custo_estimado=CUSTO[entrada.tamanho],
        )
