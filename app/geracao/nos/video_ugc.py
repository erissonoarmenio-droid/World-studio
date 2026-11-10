"""Nó vídeo UGC: Seedance 2.5 pelo Método W-orld v3 (claude/metodo-ugc-world.md).

Padrão de referência: o teste v3 "corpo vivo" de 31/10, aprovado por Eri em 01/11
("o vídeo ficou ótimo"). O prompt sai sempre na mesma ordem de blocos e só as entradas
mudam: trava de câmera e luz · contexto · referências marcadas · câmera humana · edição
(jump cuts) · ação com tempo + corpo vivo · atuação · só as falas · som · negativos.

O nó antigo (`video.py`, fórmula v2.2) continua valendo para o Seedance 2.0 fast.
Regras novas daqui: E28 (voz do Seedance é o padrão), E30 (corpo vivo).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.geracao.nos.base import Entrada, Genero, No, Pedido, Regra, normalizar_texto, para_genero
from app.geracao.nos.regras import registrar

MODELO_TEIN = "seedance-2-5"
PRECO_TEIN = {"480p": Decimal("0.1279"), "720p": Decimal("0.2885")}  # por segundo, Tein 30/10
PALAVRAS_POR_SEGUNDO = 2.5  # meta do Sirio; o v3 aprovado teve ~31 palavras em 16 s
NUMEROS = {1: "one", 2: "two", 3: "three", 4: "four"}

# Ações de corpo inteiro que contam como "corpo vivo" (E30): pelo menos uma por plano.
ACOES_DE_CORPO = (
    "walk",
    "step",
    "turn",
    "sway",
    "shift",
    "lean",
    "toss",
    "hold",
    "push",
    "sit",
    "hang",
    "lift",
    "spin",
    "move",
    "reach",
    "pull",
    "bend",
    "crouch",
    "enter",
)
# Travas que deixaram a influencer parada no v2 (E30) — não podem voltar ao prompt.
TRAVAS_DE_CORPO = (
    "gestures are compact",
    "compact gestures",
    "constant hand movement",
    "stands still",
    "standing still while",
    "keeps still",
    "static pose",
    "holds still",
)
PROPAGANDA = (
    "game changer",
    "você precisa",
    "voce precisa",
    "obcecada",
    "imperdível",
    "imperdivel",
    "fresquinha e leve",
    "melhor do mundo",
    "corre que",
    "promoção imperdível",
)
# Palavra curta logo depois do corte é engolida (E33, 01/11: o "Ó" sumiu 3 de 3 vezes).
FRACAS_NO_INICIO = ("ó", "o", "é", "e", "ai", "ah", "oh", "né", "tá", "a", "ué", "hm", "hmm")
MULETAS = ("gente", "olha", "ó", "tipo", "né", "sério", "ai,", "pera", "hmm", "cara", "pô", "mano")

LUZ_PADRAO = "Soft daylight from a window on the left mixed with the store's ceiling downlights"
CONTEXTO_PADRAO = (
    "a young woman who works at a small clothing boutique casually shows a shirt that just "
    "arrived, talking to a friend who is filming her for the shop's Instagram story. It must "
    "feel like a real, slightly messy story, not a fashion commercial."
)

# ── Partes fixas (copiadas do v3 aprovado) ─────────────────────────────────────────────
TRAVA = (
    "Rear smartphone camera held by a friend standing about 1.5–2 metres away, approximately "
    "26mm-equivalent main lens, 30fps, realistic ~1/60 shutter motion blur. {luz}, uneven "
    "light on her face, neutral natural colour, realistic smartphone exposure with small "
    "automatic white-balance and exposure corrections. Photorealistic live-action, raw "
    "smartphone realism. Visible pores, peach fuzz, natural under-eye texture, a little natural "
    "shine on the forehead and nose, tiny skin imperfections. No plastic skin, no beauty filter, "
    "no retouch, no artificial HDR, no oversharpening, no cinematic colour grade. Brazilian "
    "Portuguese. {duracao}s, vertical 9:16."
)
VOZ_REF = (
    "@audio1 — HER VOICE. Reference @audio1 as the exact voice, pacing, breathing and emotional "
    "delivery, including the small laughs. Her mouth follows @audio1 exactly."
)
CAMERA = (
    "CAMERA — not selfie footage; she never touches the camera. The unseen friend films "
    "handheld and is slightly moving: clear breathing bob, small walking sway, slight roll, "
    "constant fine micro-jitter, instinctive reframing, occasional autofocus hunt and exposure "
    "breathing. Never gimbal-smooth, never static. The friend is never visible or heard."
)
CORPO_VIVO = (
    "Her whole body is alive in every shot: she shifts her weight from one leg to the other, "
    "her shoulders stay loose, she sways lightly, her free hand tucks hair behind her ear or "
    "adjusts a sleeve, and her head moves with the sentence. Each shot has one clear full-body "
    "action. She is never planted still."
)
ATUACAO = (
    "ACTING: natural, warm, lightly amused, like talking to a friend. She breathes before "
    "speaking; uneven blinking; her eyes move every 2–3 seconds between the shirt, the lens and "
    "the room, never staring at the lens for more than 2 seconds; tiny head tilts; active "
    "eyebrows; asymmetric smile; small thinking pauses. She does not smile constantly. Hands "
    "and body move naturally with what she says, like a real person who talks with her body. "
    "No presenter delivery, no influencer excitement, no fixed stare."
)
SO_FALAS = (
    "ONLY she speaks and ONLY the lines above, in Brazilian Portuguese, exactly as {fonte}. "
    "No extra words, ad-libs, voiceover or off-screen speech. Mouth relaxed and closed when "
    "not speaking."
)
NEGATIVOS = (
    "STRICT NEGATIVES: no glossy commercial look, no studio key light, no ring-light "
    "catchlights, no skin smoothing. The {peca_nome} never changes {peca_nunca}. Exactly two "
    "arms, five fingers per hand, no fused fingers. No overacting, no giant smile, no repetitive "
    "nods. Never frozen or standing still like a mannequin. No frozen avatar pauses, no fixed "
    "stare. No identity or body drift between cuts. No morphing between cuts. No gimbal, dolly "
    "or artificial shallow focus. No text, subtitles, logos or UI."
)


# ── Perfil de atuação do HOMEM (E45, 10/11) ────────────────────────────────────────────
# Eri (vídeo 52/53): "a fala e a gesticulação, o jeito de falar estão muito femininos".
# Causa: os blocos acima foram escritos a partir da influencer mulher (v3) e o para_genero
# só troca os pronomes. Para homem o perfil inteiro é outro: gestos, energia e voz.
CORPO_VIVO_HOMEM = (
    "His whole body is alive in every shot: he shifts his weight from one leg to the other, "
    "his shoulders stay loose and relaxed, his free hand goes in and out of his pocket, "
    "touches his collar or points briefly at the shirt, and he gives small nods with the "
    "sentence. Each shot has one clear full-body action. He is never planted still."
)
ATUACAO_HOMEM = (
    "ACTING: natural, relaxed and confident, like showing something to a buddy. He breathes "
    "before speaking; uneven blinking; his eyes move every 2–3 seconds between the shirt, the "
    "lens and the room, never staring at the lens for more than 2 seconds; calm, steady head; "
    "brief half-smile; a short laugh through the nose at most once. Low-key energy, economical "
    "gestures that come from the sentence. No head tilting, no swaying, no bouncy or cute "
    "delivery, no presenter delivery, no influencer excitement, no fixed stare."
)
VOZ_HOMEM = (
    "VOICE — a Brazilian man, relaxed and natural, medium-low pitch, calm conversational pace, "
    "steady intonation with few rises at the end of sentences, slightly dry humour; speaks like "
    "a guy talking to a friend, not like a host."
)
# Gestos e jeito que denunciam o perfil feminino num vídeo de homem (bloqueia, E45).
GESTOS_FEMININOS = (
    "tucks hair",
    "behind his ear",
    "behind her ear",
    "sways",
    "sway lightly",
    "head tilt",
    "tilts his head",
    "lightly amused",
    "giggle",
    "playful",
    "flirt",
    "twirl",
    "bats his",
    "asymmetric smile",
    "active eyebrows",
)


def _perfil(genero: str) -> tuple[str, str]:
    """(corpo vivo, atuação) do gênero. Mulher = blocos do v3 aprovado."""
    if genero == "homem":
        return CORPO_VIVO_HOMEM, ATUACAO_HOMEM
    return CORPO_VIVO, ATUACAO


class Plano(BaseModel):
    """Um trecho entre dois cortes secos: o que o corpo faz, a fala e o depois da fala."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inicio: float = Field(ge=0)
    fim: float = Field(gt=0)
    enquadramento: str = ""  # ex.: "Slightly closer", "Chest-up"; vazio no 1º plano = o 1º quadro
    acao: str = Field(min_length=10)  # termina levando à fala, ex.: "... and says:"
    fala: str | None = None
    depois: str = ""

    @field_validator("fala")
    @classmethod
    def _fala_sem_aspas(cls, v: str | None) -> str | None:
        if v is not None and '"' in normalizar_texto(v):
            raise ValueError("a fala não pode ter aspas (o nó coloca)")
        return v


class EntradaUGC(Entrada):
    """O que muda de um vídeo para outro. Tudo o mais vem do Método W-orld v3."""

    planos: list[Plano] = Field(min_length=1, max_length=5)
    duracao: int = Field(ge=4, le=16)
    peca_nome: str = Field(min_length=3)  # "shirt"
    peca: str = Field(min_length=10)  # "light orange linen shirt (short sleeves, ...)"
    peca_nunca: str = Field(min_length=5)  # "colour, collar, buttons or fabric; no pocket appears"
    corpo: str = "curvy body proportions"
    cenario: str = "The store room stays as in @image1."
    contexto: str = CONTEXTO_PADRAO
    luz: str = LUZ_PADRAO
    som_peca: str = "soft fabric rustle, wooden hanger click"
    resolucao: Literal["480p", "720p"] = "480p"
    genero: Genero = "mulher"  # "homem": pronomes trocados no prompt (06/11)
    imagem_url: str | None = None
    audio_url: str | None = None  # trilha das falas: só tom e ritmo (o Seedance refaz a voz, E28)

    @model_validator(mode="after")
    def _planos_em_ordem(self) -> EntradaUGC:
        for p in self.planos:
            if p.fim <= p.inicio:
                raise ValueError("cada plano termina depois de começar")
        return self


def _t(x: float) -> str:
    return f"{x:.1f}"


def _plano(p: Plano) -> str:
    partes = [f"{_t(p.inicio)}–{_t(p.fim)}s"]
    if p.enquadramento:
        partes.append(p.enquadramento.rstrip(".") + ".")
    partes.append(p.acao.strip())
    if p.fala is not None:
        partes.append(f'"{p.fala}"')
    if p.depois:
        partes.append(p.depois.strip())
    return " ".join(partes)


def _edicao(e: EntradaUGC) -> str:
    cortes = len(e.planos) - 1
    if cortes == 0:
        return "EDITING — one continuous handheld take, no cuts."
    passos = ", then ".join(
        p.enquadramento.rstrip(".").lower() or "a new angle" for p in e.planos[1:]
    )
    return (
        f"EDITING — {NUMEROS.get(cortes, str(cortes))} casual HARD JUMP CUTS, instantaneous: "
        f"{passos}. No extreme close-up. Never morph or glide between setups."
    )


def montar_prompt(e: EntradaUGC) -> str:
    com_voz = e.audio_url is not None
    referencias = (
        f"@image1 — THE WOMAN AND THE {e.peca_nome.upper()}. First frame. Preserve her exact "
        f"identity, face, hair, apparent age, skin tone and {e.corpo}, and the exact {e.peca} in "
        f"every cut. {e.cenario}"
    )
    if com_voz:
        referencias += "\n" + VOZ_REF
    fonte = "in @audio1" if com_voz else "written"
    corpo_vivo, atuacao = _perfil(e.genero)
    acao = (
        f"ACTION, TIMED (spoken lines exactly as {fonte}). {corpo_vivo}\n"
        + "\nHARD CUT.\n".join(_plano(p) for p in e.planos)
    )
    blocos = [
        TRAVA.format(luz=e.luz, duracao=e.duracao),
        f"Scene context: {e.contexto}",
        referencias,
        CAMERA,
        _edicao(e),
        acao,
        atuacao,
        *([VOZ_HOMEM] if e.genero == "homem" else []),
        SO_FALAS.format(fonte=fonte),
        f"SFX — realistic phone microphone, quiet store room tone, {e.som_peca}, faint street "
        "ambience. No music.",
        NEGATIVOS.format(peca_nome=e.peca_nome, peca_nunca=e.peca_nunca),
    ]
    prompt = "\n\n".join(
        normalizar_texto(b) if "\n" not in b else _normalizar_linhas(b) for b in blocos
    )
    return para_genero(prompt, e.genero)


def _normalizar_linhas(bloco: str) -> str:
    return "\n".join(normalizar_texto(linha) for linha in bloco.split("\n"))


# ── Leitura do pedido para as regras ───────────────────────────────────────────────────
def _e(p: Pedido) -> EntradaUGC:
    return p.entrada


def _falas(p: Pedido) -> list[str]:
    return [normalizar_texto(pl.fala) for pl in _e(p).planos if pl.fala]


def _palavras(texto: str) -> int:
    return len(re.findall(r"[\wÀ-ÿ]+", texto))


def _aspas_ok(p: Pedido) -> bool:
    falas = _falas(p)
    citados = re.findall(r'"([^"]+)"', p.prompt)
    if any(citados.count(f) != 1 for f in falas):
        return False
    # o resto entre aspas só pode ser palavra-gatilho de alguma fala (ex.: on "sério")
    return all(c in falas or any(c in f for f in falas) for c in citados)


def _tempos_ok(p: Pedido) -> bool:
    pl = _e(p).planos
    if pl[0].inicio != 0 or abs(pl[-1].fim - _e(p).duracao) > 0.05:
        return False
    return all(abs(a.fim - b.inicio) < 0.05 for a, b in zip(pl, pl[1:], strict=False))


def _primeira_palavra(fala: str) -> str:
    m = re.match(r"[\s.…,!?\-]*([\wÀ-ÿ]+)", fala)
    return m.group(1).lower() if m else ""


def _fala_comeca_forte(p: Pedido) -> bool:
    return all(
        _primeira_palavra(pl.fala) not in FRACAS_NO_INICIO for pl in _e(p).planos[1:] if pl.fala
    )


def _corpo_vivo(p: Pedido) -> bool:
    bloco = para_genero(normalizar_texto(_perfil(_e(p).genero)[0]), _e(p).genero)
    return bloco in p.prompt and all(
        any(v in pl.acao.lower() for v in ACOES_DE_CORPO) for pl in _e(p).planos
    )


def _perfil_do_genero(p: Pedido) -> bool:
    """Homem: blocos masculinos + voz de homem, e nenhum gesto feminino nas ações do diretor
    (o bloco masculino diz "no head tilting", então a busca é só nas ações e reações)."""
    e = _e(p)
    if e.genero != "homem":
        return True
    acoes = " ".join(f"{pl.acao} {pl.depois}" for pl in e.planos).lower()
    feminino = normalizar_texto(ATUACAO)[:60]
    return (
        "VOICE — a Brazilian man" in p.prompt
        and para_genero(feminino, "homem") not in p.prompt
        and not any(g in acoes for g in GESTOS_FEMININOS)
    )


REGRAS = registrar(
    "video_ugc",
    [
        Regra(
            id="ugc.modelo_25",
            nivel="bloqueia",
            faca="O Método W-orld v3 é para o Seedance 2.5 (Tein seedance-2-5).",
            origem="Método W-orld v3 — 31/10 (2.0 fast reprovado por Eri: 'chato', 'cara de IA')",
            checar=lambda p: p.payload.get("model") == MODELO_TEIN,
        ),
        Regra(
            id="ugc.tempos_contiguos",
            nivel="bloqueia",
            faca="Os planos começam em 0, emendam sem buraco e o último termina na duração.",
            origem="Bootcamp + v3 aprovado (marcas de tempo por plano) — 31/10",
            checar=_tempos_ok,
        ),
        Regra(
            id="ugc.cortes",
            nivel="bloqueia",
            faca="Tomada única ou 2 a 4 jump cuts (3 a 5 planos).",
            origem="Método W-orld v3 bloco 5 — 31/10",
            checar=lambda p: len(_e(p).planos) == 1 or 3 <= len(_e(p).planos) <= 5,
        ),
        Regra(
            id="ugc.sem_close_extremo",
            nivel="bloqueia",
            faca="Nunca pular para close extremo.",
            origem="juiz do v1 2.5 — 31/10 ('corte brusco para o close')",
            checar=lambda p: (
                "extreme close-up"
                not in " ".join(
                    pl.enquadramento.lower() + " " + pl.acao.lower() for pl in _e(p).planos
                )
            ),
        ),
        Regra(
            id="ugc.corpo_vivo",
            nivel="bloqueia",
            faca="Bloco 'corpo vivo' fixo e uma ação de corpo inteiro em cada plano.",
            origem="E30 — 31/10 (Eri: 'ela fica parada demais'; v3 aprovado em 01/11)",
            checar=_corpo_vivo,
        ),
        Regra(
            id="ugc.perfil_do_genero",
            nivel="bloqueia",
            faca="Homem: perfil de atuação e voz masculinos; nada de gesto/jeito do perfil "
            "feminino (" + ", ".join(GESTOS_FEMININOS[:6]) + "…).",
            origem="E45 — 10/11 (Eri: 'a fala e a gesticulação estão muito femininas')",
            checar=_perfil_do_genero,
        ),
        Regra(
            id="ugc.sem_trava_de_corpo",
            nivel="bloqueia",
            faca="NÃO usar travas que congelam o corpo: " + ", ".join(TRAVAS_DE_CORPO) + ".",
            origem="E30 — 31/10 (as travas do v2 deixaram 12 de 16 s quase sem movimento)",
            checar=lambda p: not any(t in p.prompt.lower() for t in TRAVAS_DE_CORPO),
        ),
        Regra(
            id="ugc.comeca_em_movimento",
            nivel="aviso",
            faca="O 1º plano começa no meio de um movimento (andando, entrando, chegando perto).",
            origem="E30 — 31/10 (v3 aprovado começa andando até a câmera)",
            checar=lambda p: any(
                v in _e(p).planos[0].acao.lower()
                for v in ("mid-movement", "walk", "step", "enter", "arriv")
            ),
        ),
        Regra(
            id="ugc.falas_entre_aspas",
            nivel="bloqueia",
            faca="Cada fala vai entre aspas uma vez só; outras aspas só para palavra da fala.",
            origem="E11 — 29/10 (Seedance troca palavras sem a fala escrita)",
            checar=_aspas_ok,
        ),
        Regra(
            id="ugc.tem_fala",
            nivel="bloqueia",
            faca="Vídeo UGC falado: pelo menos um plano com fala.",
            origem="Método W-orld v3 (formato falado; sem fala usar o nó antigo F-C)",
            checar=lambda p: bool(_falas(p)),
        ),
        Regra(
            id="ugc.fala_comeca_forte",
            nivel="bloqueia",
            faca="Depois de um corte, a fala NÃO começa com palavra curta (ó, é, e, ai, né, tá…): "
            "comece com palavra cheia e use a muleta no meio da frase.",
            origem='E33 — 01/11 (o "Ó" depois do corte sumiu 3 de 3 vezes: v3 e os 2 do sofá)',
            checar=_fala_comeca_forte,
        ),
        Regra(
            id="ugc.palavras_cabem",
            nivel="aviso",
            faca=f"Falas somam até (duração − 2) × {PALAVRAS_POR_SEGUNDO} palavras.",
            origem="Sirio + v3 aprovado (~31 palavras em 16 s) — 31/10",
            checar=lambda p: (
                sum(_palavras(f) for f in _falas(p)) <= (_e(p).duracao - 2) * PALAVRAS_POR_SEGUNDO
            ),
        ),
        Regra(
            id="ugc.sem_propaganda",
            nivel="bloqueia",
            faca="Falas sem frase de propaganda: " + ", ".join(PROPAGANDA) + ".",
            origem="Método W-orld v3 camada 3 / Bootcamp — 31/10",
            checar=lambda p: not any(x in f.lower() for f in _falas(p) for x in PROPAGANDA),
        ),
        Regra(
            id="ugc.muleta",
            nivel="aviso",
            faca="Pelo menos uma muleta de fala de gente (gente, olha, ó, tipo, né, sério…).",
            origem="Método W-orld v3 camada 3 — 31/10",
            checar=lambda p: any(
                re.search(rf"(?<!\w){re.escape(m)}(?!\w)", f.lower())
                for f in _falas(p)
                for m in MULETAS
            ),
        ),
        Regra(
            id="ugc.voz_ref_coerente",
            nivel="bloqueia",
            faca="@audio1 só é citado quando a trilha vai junto (e então vai citado).",
            origem="E28 — 31/10 (voz do Seedance é o padrão; a trilha só dá tom e ritmo)",
            checar=lambda p: ("@audio1" in p.prompt) == ("reference_audio" in p.payload),
        ),
        Regra(
            id="ugc.primeiro_quadro",
            nivel="bloqueia",
            faca="Sempre com o 1º quadro aprovado como @image1.",
            origem="Bootcamp ('o vídeo nunca é melhor que o 1º quadro') — 31/10",
            checar=lambda p: bool(p.payload.get("reference_image")),
        ),
        Regra(
            id="ugc.peca_travada",
            nivel="bloqueia",
            faca="A peça é descrita nas referências e travada nos negativos.",
            origem="E15/E17 + v3 (camisa igual em todos os cortes) — 31/10",
            checar=lambda p: (
                _e(p).peca in p.prompt and f"The {_e(p).peca_nome} never changes" in p.prompt
            ),
        ),
        Regra(
            id="ugc.cinco_dedos",
            nivel="bloqueia",
            faca='Sempre "Exactly two arms, five fingers per hand".',
            origem="E12 — 29/10",
            checar=lambda p: "five fingers per hand" in p.prompt,
        ),
        Regra(
            id="ugc.sem_musica_sem_texto",
            nivel="bloqueia",
            faca="Sem música e sem texto/legenda gerada.",
            origem="fórmula §3 + v3 — 31/10",
            checar=lambda p: "No music." in p.prompt and "No text, subtitles" in p.prompt,
        ),
    ],
)


class NoVideoUGC(No):
    nome = "video_ugc"
    regras = REGRAS

    def montar_pedido(self, entrada: EntradaUGC) -> Pedido:
        prompt = montar_prompt(entrada)
        payload: dict = {
            "model": MODELO_TEIN,
            "prompt": prompt,
            "duration": entrada.duracao,
            "resolution": entrada.resolucao,
            "ratio": "9:16",
            "generate_audio": True,
            "watermark": False,
        }
        if entrada.imagem_url:
            payload["reference_image"] = [entrada.imagem_url]
        if entrada.audio_url:
            payload["reference_audio"] = [entrada.audio_url]
        return Pedido(
            no=self.nome,
            fornecedor="tein",
            modelo=MODELO_TEIN,
            entrada=entrada,
            prompt=prompt,
            payload=payload,
            custo_estimado=PRECO_TEIN[entrada.resolucao] * entrada.duracao,
        )
