"""Nó vídeo: Seedance 2.0 (Atlas), prompt pela fórmula de 12 blocos (v2 de 29/10).

Base: claude/formula-prompt-seedance.md v2.2 e aios/projects/aprendizados-processo-video.md.
O prompt nunca é escrito à mão: só as entradas mudam; as partes fixas e as regras ficam aqui.

Blocos (na ordem): [1] objetivo · [2] papéis das referências (fixo) · [3–4] formato ·
[5] cenário · [6] peça · [7] batidas com a fala · [8] tom e ritmo · [9–11] falhas de
celular, áudio e anti-defeitos (fixo) · [12] vibe.
"""

from __future__ import annotations

import re
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.geracao.nos.base import Entrada, No, Pedido, Regra, normalizar_texto
from app.geracao.nos.regras import registrar

MODELO = "bytedance/seedance-2.0-fast/reference-to-video"
PRECO_POR_SEGUNDO = Decimal("0.072")  # Atlas, 480p, 29/10 (fórmula §6)
PALAVRAS_POR_SEGUNDO = 2.5  # fala lida sem pressa, já com pausas (fórmula §5)
MARCA_FALA = "{fala}"

# Partes fixas (não vêm da loja nem de quem pede)
REFERENCIAS = (
    "@image1 is the first frame and the identity reference: keep this exact woman, "
    "her face, age and hair. @audio1 is her voice: match the tone and pacing of @audio1, "
    "not its words."
)
FIM = (
    "Natural phone quality, not color graded, slight grain, no ring light. "
    "Sound direct from the phone mic, ambient room tone, no music. "
    "Plain objects, no text, no logos. Exactly two arms, five fingers per hand."
)
PROIBIDAS = ("cinematic", "professional", "stunning", "8k", "studio", "perfect", "epic", "premium")
PISTAS_RITMO = ("never rush", "unhurried", "pause", "breath", "between steps")


class EntradaVideo(Entrada):
    """O que muda de um clipe para outro. A fala vem do roteiro, idêntica."""

    fala: str = Field(min_length=2, max_length=300)
    duracao: int = Field(ge=4, le=15)
    objetivo: str  # [1] "Create a talking selfie clip from @image1."
    formato: str  # [3–4] duração, celular, luz, enquadramento
    cenario: str  # [5]
    peca: str  # [6] descrição da peça (do Analista de Peças), "unchanged in every shot"
    batidas: str  # [7] com {fala} no lugar exato da fala
    tom: str  # [8]
    vibe: str  # [12]

    @field_validator("fala")
    @classmethod
    def _fala_sem_aspas(cls, v: str) -> str:
        v = normalizar_texto(v)
        if '"' in v:
            raise ValueError("a fala não pode ter aspas: elas marcam a fala no prompt")
        return v

    @model_validator(mode="after")
    def _uma_marca_de_fala(self) -> EntradaVideo:
        if self.batidas.count(MARCA_FALA) != 1:
            raise ValueError("as batidas precisam ter {fala} exatamente uma vez")
        return self


def _texto(p: Pedido) -> str:
    return normalizar_texto(p.prompt)


def _palavras(texto: str) -> int:
    return len([w for w in texto.split() if w != "—"])


def _enquadramento_possivel(p: Pedido) -> bool:
    t = _texto(p).lower()
    return not ("front camera" in t and ("waist up" in t or "full body" in t))


REGRAS = registrar(
    "video",
    [
        Regra(
            id="video.fala_entre_aspas",
            nivel="bloqueia",
            faca="A fala do roteiro vai entre aspas no prompt, idêntica ao roteiro, uma vez só.",
            origem="E11 — 29/10 (Seedance trocou as palavras em 4 de 5 clipes)",
            checar=lambda p: re.findall(r'"([^"]+)"', _texto(p)) == [p.entrada.fala],
        ),
        Regra(
            id="video.audio_so_tom",
            nivel="bloqueia",
            faca='O @audio1 serve só para tom e ritmo: "match the tone and pacing of @audio1, '
            'not its words".',
            origem="E11 — 29/10 (o Seedance refaz a voz do áudio, nunca repassa as palavras)",
            checar=lambda p: "not its words" in _texto(p),
        ),
        Regra(
            id="video.papeis_das_referencias",
            nivel="bloqueia",
            faca='Cada referência diz o seu papel: "@image1 is ..." e "@audio1 is ...".',
            origem="E11 — 29/10 / fórmula §3 bloco 2",
            checar=lambda p: "@image1 is" in _texto(p) and "@audio1 is" in _texto(p),
        ),
        Regra(
            id="video.cinco_dedos",
            nivel="bloqueia",
            faca='Sempre "Exactly two arms, five fingers per hand."',
            origem="E12 — 29/10 (dedos deformados ao tocar o rosto) / fórmula §3 bloco 11",
            checar=lambda p: "five fingers per hand" in _texto(p),
        ),
        Regra(
            id="video.palavras_proibidas",
            nivel="bloqueia",
            faca="NÃO usar: " + ", ".join(PROIBIDAS) + ".",
            origem="fórmula §4 (deixam o UGC com cara de comercial)",
            checar=lambda p: not any(w in _texto(p).lower() for w in PROIBIDAS),
        ),
        Regra(
            id="video.fala_cabe",
            nivel="bloqueia",
            faca="A fala cabe no clipe lida sem pressa: palavras / 2,5 ≤ duração − 1 s.",
            origem="fórmula §5 / E11 — 29/10 (fala apertada sai corrida e trocada)",
            checar=lambda p: (
                len(p.entrada.fala.split()) / PALAVRAS_POR_SEGUNDO <= p.entrada.duracao - 1
            ),
        ),
        Regra(
            id="video.enquadramento_possivel",
            nivel="bloqueia",
            faca='NÃO pedir "front camera" junto com "waist up" ou "full body" '
            "(câmera na mão não enquadra isso).",
            origem="checker item 18 — 21/10",
            checar=_enquadramento_possivel,
        ),
        Regra(
            id="video.sem_negative_prompt",
            nivel="bloqueia",
            faca="NÃO usar o parâmetro negative_prompt; a restrição vai dentro do prompt.",
            origem="fórmula §4 (job COMPLETED e erro 422 ao buscar o resultado)",
            checar=lambda p: "negative_prompt" not in p.payload,
        ),
        Regra(
            id="video.sem_musica",
            nivel="bloqueia",
            faca='Sempre "no music" e som do microfone do celular.',
            origem="fórmula §3 bloco 10 (sem isso entra música de banco)",
            checar=lambda p: "no music" in _texto(p).lower(),
        ),
        Regra(
            id="video.sem_texto",
            nivel="bloqueia",
            faca='Sempre "no text, no logos".',
            origem="fórmula §3 bloco 11 / checker item 20",
            checar=lambda p: "no text, no logos" in _texto(p).lower(),
        ),
        Regra(
            id="video.peca_inalterada",
            nivel="bloqueia",
            faca='A peça é descrita e "stays unchanged in every shot".',
            origem="checker item 12 / verificador-fidelidade (peça alterada derruba a entrega)",
            checar=lambda p: "unchanged in every shot" in _texto(p),
        ),
        Regra(
            id="video.batida_silenciosa",
            nivel="aviso",
            faca='Ter uma batida "silent" (respiro sem fala) para o clipe terminar limpo.',
            origem="fórmula §3 bloco 7",
            checar=lambda p: "silent" in _texto(p).lower(),
        ),
        Regra(
            id="video.pista_de_ritmo",
            nivel="aviso",
            faca="Ter uma pista de ritmo (pause, breath, unhurried...).",
            origem="fórmula §3 bloco 8 (sem isso a IA fala rápido demais)",
            checar=lambda p: any(k in _texto(p).lower() for k in PISTAS_RITMO),
        ),
        Regra(
            id="video.falhas_de_celular",
            nivel="aviso",
            faca='"not color graded" e movimento de celular (micro-movement ou wobbles).',
            origem="fórmula §3 bloco 9",
            checar=lambda p: (
                "not color graded" in _texto(p).lower()
                and ("micro-movement" in _texto(p) or "wobbles" in _texto(p))
            ),
        ),
        Regra(
            id="video.tamanho",
            nivel="aviso",
            faca="Prompt com batidas entre 100 e 260 palavras.",
            origem="fórmula §2",
            checar=lambda p: 100 <= _palavras(_texto(p)) <= 260,
        ),
        Regra(
            id="video.abre_com_objetivo",
            nivel="aviso",
            faca='Abrir com o objetivo ("Create ...") e o formato ("filmed on smartphone").',
            origem="fórmula §3 blocos 1 e 4",
            checar=lambda p: _texto(p).startswith("Create") and "filmed on smartphone" in _texto(p),
        ),
    ],
)


class NoVideo(No):
    nome = "video"
    regras = REGRAS

    def montar_pedido(self, entrada: EntradaVideo) -> Pedido:
        batidas = entrada.batidas.replace(MARCA_FALA, f'"{entrada.fala}"')
        blocos = [
            entrada.objetivo,
            REFERENCIAS,
            entrada.formato,
            entrada.cenario,
            entrada.peca,
            batidas,
            entrada.tom,
            FIM,
            entrada.vibe,
        ]
        prompt = normalizar_texto(" ".join(b.strip() for b in blocos))
        payload = {
            "model": MODELO,
            "prompt": prompt,
            "duration": entrada.duracao,
            "resolution": "480p",
            "ratio": "9:16",
            "generate_audio": True,
            "watermark": False,
            # reference_images / reference_audios entram no envio (URLs da mídia no R2)
        }
        return Pedido(
            no=self.nome,
            fornecedor="atlas",
            modelo=MODELO,
            entrada=entrada,
            prompt=prompt,
            payload=payload,
            custo_estimado=PRECO_POR_SEGUNDO * entrada.duracao,
        )
