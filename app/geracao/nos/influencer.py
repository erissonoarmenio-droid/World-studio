"""Nó influencer: cria a imagem principal da influencer da loja (kit de identidade v2).

Método: `claude/metodo-ficha-personagem.md` (24/10) + skill `criar-influencer`.
- Imagem principal = **corpo inteiro de frente, rosto nítido, 2K, 3:4, fundo branco liso**.
  No vídeo só a 1ª imagem chega ao modelo; por isso ela precisa carregar o rosto inteiro.
- Roupa neutra e justa, descrita com o decote (no teste de 24/10 o decote mudou entre vistas).
- Close do rosto e costas saem DEPOIS, a partir da principal aprovada (etapa "vistas").

Três modos:
- `nova`: aparência descrita na conversa (influencer fictícia); sem foto de pessoa real.
- `da_pessoa`: a influencer é a própria lojista (ou o Eri no teste), a partir das fotos dela.
  Só com o consentimento "clone" registrado — o executor confere antes de montar o pedido.
- `ajuste`: a principal anterior + o que mudar ("cabelo mais curto"); o resto fica igual.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.geracao.nos.base import Entrada, No, Pedido, Regra, normalizar_texto
from app.geracao.nos.foto import Imagem
from app.geracao.nos.regras import registrar

MODELO = "gemini-nano-banana-2.1"
CUSTO = Decimal("0.05")  # 2K direto (estimado 24/10); em lote sai pela metade
Genero = Literal["mulher", "homem"]
PALAVRAS = {"mulher": ("woman", "She", "her"), "homem": ("man", "He", "his")}

FUNDO = (
    "Full-body photo from head to toe, facing the camera straight on, standing relaxed with "
    "arms at the sides, face sharp and fully visible, on a plain seamless white studio "
    "background, soft even daylight. "
)
CLOSE = (
    "Close-up portrait from the chest up, facing the camera straight on, face sharp, large in "
    "the frame and fully visible, on a plain seamless white background, soft even daylight. "
)
PELE = (
    "Photorealistic, looks like a real photo: natural skin texture with pores and slight "
    "imperfections, no beauty filter, no CGI look, true colours, no text, no logos, no "
    "watermark. "
)
VISTAS = {
    "close": "Close-up portrait of the same {w} from image 1, head and shoulders, facing the "
    "camera, same face, hair, eyewear and clothing as in image 1, plain white background.",
    "costas": "Full-body photo of the same {w} from image 1 seen from directly behind, same "
    "hair, body and clothing as in image 1, plain white background, soft even daylight.",
}


class EntradaInfluencer(Entrada):
    modo: Literal["nova", "da_pessoa", "ajuste", "vista"]
    genero: Genero = "mulher"
    idade: int = Field(ge=21, le=70)  # sempre adulta (criar-influencer: 25+ no visual)
    aparencia: str = ""  # nova: rosto, cabelo, pele, olhos ("dark wavy shoulder-length hair…")
    corpo: str = Field(min_length=5)  # biótipo, puxado para as clientes da loja
    roupa: str = Field(min_length=10)  # neutra e justa, com o decote ("plain white crew-neck…")
    oculos: str = ""  # "black rectangular eyeglasses" (sem marca escrita)
    fotos: list[Imagem] = Field(default_factory=list, max_length=6)  # da_pessoa: fotos do ROSTO
    foto_corpo: Imagem | None = None  # da_pessoa: corpo inteiro real, só para o biótipo (E26)
    enquadramento: Literal["corpo", "close"] = "corpo"  # da_pessoa: close 1º, aprovar (E5)
    anterior: Imagem | None = None  # ajuste / vista: a principal já gerada
    mudanca: str = ""  # ajuste: o que mudar
    vista: Literal["close", "costas"] | None = None

    @model_validator(mode="after")
    def _coerente(self) -> EntradaInfluencer:
        if self.modo == "nova" and len(self.aparencia) < 15:
            raise ValueError("influencer nova precisa da aparência descrita")
        if self.modo == "nova" and self.fotos:
            raise ValueError("influencer nova não usa foto de pessoa real")
        if self.modo == "da_pessoa" and len(self.fotos) < 2:
            raise ValueError("influencer da pessoa precisa de pelo menos 2 fotos do rosto dela")
        if self.modo == "da_pessoa" and len(self.aparencia) < 40:
            raise ValueError(
                "influencer da pessoa precisa dos traços do rosto descritos (Fit Check, 06/11)"
            )
        if self.modo != "da_pessoa" and (self.foto_corpo or self.enquadramento != "corpo"):
            raise ValueError("foto do corpo e close só no modo da_pessoa")
        if self.modo in ("ajuste", "vista") and self.anterior is None:
            raise ValueError("ajuste e vista partem da imagem principal anterior")
        if self.modo == "ajuste" and len(self.mudanca) < 5:
            raise ValueError("ajuste precisa dizer o que mudar")
        if self.modo == "vista" and self.vista is None:
            raise ValueError("diga qual vista (close ou costas)")
        return self


def _t(p: Pedido) -> str:
    return normalizar_texto(p.prompt).lower()


def _e(p: Pedido) -> EntradaInfluencer:
    return p.entrada


PALAVRAS_PROIBIDAS = ("sexy", "nude", "naked", "cleavage", "lingerie", "busty", "seductive")

REGRAS = registrar(
    "influencer",
    [
        Regra(
            id="influencer.so_google",
            nivel="bloqueia",
            faca="Imagem da influencer só pelo Google direto; nunca pela Atlas.",
            origem="E15 — 30/10",
            checar=lambda p: p.fornecedor == "google",
        ),
        Regra(
            id="influencer.principal_corpo_inteiro",
            nivel="bloqueia",
            faca="A principal é corpo inteiro de frente, rosto nítido, fundo branco liso, 2K.",
            origem="Kit v2 — 24/10 (só a 1ª imagem chega ao vídeo)",
            checar=lambda p: (
                _e(p).modo == "vista"
                or _e(p).enquadramento == "close"  # âncora do rosto; a principal vem depois
                or ("full-body" in _t(p) and "white" in _t(p) and "2k" in str(p.payload).lower())
            ),
        ),
        Regra(
            id="influencer.idade_escrita",
            nivel="bloqueia",
            faca="Escrever a idade (adulta, nunca aparência de menor).",
            origem="E5 — 29/10 + recusas do Atendente (sempre adulta)",
            checar=lambda p: f"{_e(p).idade} years old" in _t(p),
        ),
        Regra(
            id="influencer.roupa_com_decote",
            nivel="aviso",
            faca='Descrever o decote da roupa ("crew-neck", "v-neck"…): não muda entre vistas.',
            origem="Kit v2 — 24/10 (decote mudou entre frente e close)",
            checar=lambda p: any(w in _e(p).roupa.lower() for w in ("neck", "collar", "strap")),
        ),
        Regra(
            id="influencer.sem_texto",
            nivel="bloqueia",
            faca='Sempre "no text, no logos" (óculos e roupa da referência podem ter marca).',
            origem="foto.sem_texto + teste do Eri 05/11 (óculos com marca na haste)",
            checar=lambda p: "no text, no logos" in _t(p),
        ),
        Regra(
            id="influencer.sem_sexualizar",
            nivel="bloqueia",
            faca="Corpo e roupa descritos de forma natural e de moda; nunca termos sexuais.",
            origem="31/10 / limites do estúdio",
            checar=lambda p: (
                not any(
                    w in (_e(p).corpo + " " + _e(p).roupa + " " + _e(p).aparencia).lower()
                    for w in PALAVRAS_PROIBIDAS
                )
            ),
        ),
        Regra(
            id="influencer.oculos_iguais",
            nivel="bloqueia",
            faca="Se usa óculos: mesma armação em toda imagem, sem marca escrita.",
            origem="Teste do Eri 05/11 (desafio dos óculos)",
            checar=lambda p: not _e(p).oculos or "same eyeglasses" in _t(p),
        ),
        Regra(
            id="influencer.pessoa_pele_e_tracos",
            nivel="bloqueia",
            faca=(
                "Rosto de pessoa real: traços descritos um a um e tom de pele travado como nas "
                "fotos (nem mais pálido, nem mais oliva); fotos do rosto separadas do corpo."
            ),
            origem="06/11 — 1ª ficha do Eri: rosto mais fino e pele mais oliva (não parecido)",
            checar=lambda p: (
                _e(p).modo != "da_pessoa"
                or ("skin tone exactly as in" in _t(p) and "key features to keep" in _t(p))
            ),
        ),
    ],
)


class NoInfluencer(No):
    nome = "influencer"
    regras = REGRAS

    def montar_pedido(self, e: EntradaInfluencer, fornecedor: str = "google") -> Pedido:
        w, ele, seu = PALAVRAS[e.genero]
        oculos = (
            f" {ele} wears {e.oculos}; keep the same eyeglasses frame in every image, with no "
            "text or logo on the frame."
            if e.oculos
            else ""
        )
        idade = f" {ele} is {e.idade} years old; keep {seu} age, do not age {seu} face."
        imagens: list[Imagem] = []
        if e.modo == "vista":
            assert e.anterior is not None and e.vista is not None
            imagens = [e.anterior]
            prompt = VISTAS[e.vista].format(w=w) + " " + PELE + idade + oculos
        else:
            if e.modo == "nova":
                quem = f"A {w}: {e.aparencia.strip().rstrip('.')}."
            elif e.modo == "da_pessoa":
                imagens = list(e.fotos)
                n = len(imagens)
                quem = (
                    f"Images 1 to {n} are close-up photos of the same real {w}'s face (identity "
                    f"reference, with consent). Reproduce this exact face so that anyone who knows "
                    f"this person recognises the face at once. Key features to keep: "
                    f"{e.aparencia.strip().rstrip('.')}. Keep {seu} skin tone exactly as in "
                    f"images 1 to {n}, with the same warmth and natural redness; do not make it "
                    f"paler, greyer, more olive or more tanned. Ignore the backgrounds, the colour "
                    f"cast of the room lights and any text or logos in the photos."
                )
                if e.foto_corpo is not None:
                    imagens.append(e.foto_corpo)
                    quem += (
                        f" Image {n + 1} shows {seu} real body: use it only for body build, "
                        f"height and proportions, not for clothing, pose or background."
                    )
            else:  # ajuste
                assert e.anterior is not None
                imagens = [e.anterior]
                quem = (
                    f"Image 1 = this exact {w}. Change ONLY this: {e.mudanca.strip().rstrip('.')}. "
                    f"Keep everything else exactly as in image 1."
                )
            fundo = CLOSE if e.enquadramento == "close" else FUNDO
            prompt = (
                f"{quem} Body: {e.corpo.strip().rstrip('.')}. {ele} wears "
                f"{e.roupa.strip().rstrip('.')}.{oculos}{idade} " + fundo + PELE
            )
        partes = [{"text": prompt}] + [
            {"inlineData": {"mimeType": i.mime, "data": i.dados_b64}} for i in imagens
        ]
        payload = {
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": "3:4", "imageSize": "2K"},
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
