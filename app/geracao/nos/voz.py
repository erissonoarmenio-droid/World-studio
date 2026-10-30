"""Nó voz: Gemini TTS com a receita D da pesquisa (29/10, escolhida por Eri em 30/10).

Formato fixo: preâmbulo "Synthesize speech... Do NOT speak them" + AUDIO PROFILE + SCENE +
### PERFORMANCE + #### TRANSCRIPT. Só a fala e a voz mudam.
Conferência depois de gerar: palavras ≥ 90% (transcrição) e duração ≤ 1,8× o esperado.
"""

from __future__ import annotations

import difflib
import re
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.geracao.nos.base import Entrada, No, Pedido, Regra, Veredito, normalizar_texto
from app.geracao.nos.regras import registrar

MODELO = "gemini-3.1-flash-tts-preview"  # receita D medida neste modelo
MODELO_IRMAO = "gemini-3.8-flash-tts"  # cota diária separada (E13)
CUSTO = Decimal("0.002")  # por fala de ~4 s (29/10)
CARACTERES_POR_SEGUNDO = 14
LIMITE_PALAVRAS = 0.90
LIMITE_DURACAO = 1.8
Voz = Literal["Kore"]  # cardápio aprovado; voz nova entra aqui depois de medida

RECEITA = (
    "Synthesize speech for the performance defined below. The profile, scene and performance "
    "notes are direction only. Do NOT speak them. Speak ONLY the lines under #### TRANSCRIPT."
    "\n\n# AUDIO PROFILE: Ju\n## Moça de 25 anos, dona de uma lojinha de roupa no Brasil. "
    "Não é locutora, nunca fez propaganda.\n\n## SCENE\nFim de tarde na loja vazia. Ela segura "
    "o celular perto do rosto e grava um story rapidinho, meio rindo, como se mandasse um áudio "
    "pra melhor amiga.\n\n### PERFORMANCE\nStyle: dá pra ouvir o sorriso, mas sem empolgação de "
    "vendedora; jeito de conversa, meio despreocupado.\nPace: fala corrida, emendando as "
    "palavras, sem pausas longas; o tom não cai no fim das frases.\nVoice: perto do microfone, "
    "volume baixo, português do Brasil bem coloquial.\n\n#### TRANSCRIPT\n"
)
# Começos que funcionaram (E2): conector ou vocativo antes da primeira vírgula.
CONECTORES = {"e", "gente", "olha", "ó", "então", "oi", "nossa", "mas", "tipo", "ai", "aí"}


class EntradaVoz(Entrada):
    fala: str = Field(min_length=2, max_length=400)
    voz: Voz = "Kore"
    duracao_max: float | None = Field(default=None, gt=0)  # duração do clipe, se houver

    @field_validator("fala")
    @classmethod
    def _limpa(cls, v: str) -> str:
        return normalizar_texto(v)


def segundos_esperados(fala: str) -> float:
    return len(fala) / CARACTERES_POR_SEGUNDO


def _comeca_com_conector(p: Pedido) -> bool:
    primeira = re.split(r"[,.!?]", p.entrada.fala, maxsplit=1)[0].split()
    return len(primeira) > 1 or primeira[0].lower() in CONECTORES


REGRAS = registrar(
    "voz",
    [
        Regra(
            id="voz.sem_reticencias",
            nivel="bloqueia",
            faca='NÃO usar "..." na fala; vírgula no lugar (frase corrida).',
            origem="E3 — 29/10 (pausas mecânicas em 3 de 5)",
            checar=lambda p: "..." not in p.entrada.fala and "…" not in p.entrada.fala,
        ),
        Regra(
            id="voz.comeca_com_conector",
            nivel="aviso",  # medido 1 vez só; a conferência de palavras pega o que escapar
            faca='Começar com conector ou vocativo ("E ó, andando..."), nunca palavra solta.',
            origem='E2 — 29/10 (primeira palavra engolida: "Andar" → "Dá", 2 de 2)',
            checar=_comeca_com_conector,
        ),
        Regra(
            id="voz.formato_fixo",
            nivel="bloqueia",
            faca="Formato fixo: preâmbulo + ### PERFORMANCE + #### TRANSCRIPT com só a fala.",
            origem="E1 — 29/10 (leu a instrução em 6 de 10 no formato antigo; 0 de 10 no novo)",
            checar=lambda p: (
                p.prompt.startswith("Synthesize speech")
                and "### PERFORMANCE" in p.prompt
                and p.prompt.split("#### TRANSCRIPT\n", 1)[-1] == p.entrada.fala
            ),
        ),
        Regra(
            id="voz.fala_cabe",
            nivel="bloqueia",
            faca="A fala cabe no clipe: ~14 caracteres por segundo ≤ duração − 1 s.",
            origem="regra 2 — 29/10 / fórmula §5",
            checar=lambda p: (
                p.entrada.duracao_max is None
                or segundos_esperados(p.entrada.fala) <= p.entrada.duracao_max - 1
            ),
        ),
    ],
)


class NoVoz(No):
    nome = "voz"
    regras = REGRAS

    def montar_pedido(self, entrada: EntradaVoz, modelo: str = MODELO) -> Pedido:
        prompt = RECEITA + entrada.fala
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": entrada.voz}}
                },
            },
        }
        return Pedido(
            no=self.nome,
            fornecedor="google",
            modelo=modelo,
            entrada=entrada,
            prompt=prompt,
            payload=payload,
            custo_estimado=CUSTO,
        )


def _palavras(texto: str) -> list[str]:
    return re.sub(r"[^a-zà-ú ]", " ", texto.lower()).split()


def conferir_voz(fala: str, transcricao: str, duracao_s: float) -> Veredito:
    """Juiz da voz: compara a transcrição do áudio com a fala e mede a duração."""
    sim = difflib.SequenceMatcher(None, _palavras(fala), _palavras(transcricao)).ratio()
    razao = duracao_s / segundos_esperados(fala)
    motivos = []
    if sim < LIMITE_PALAVRAS:
        motivos.append(f"palavras {sim:.0%} < 90% (fala trocada ou engolida)")
    if razao > LIMITE_DURACAO:
        motivos.append(f"duração {razao:.1f}× > 1,8× (leu a instrução ou pausou demais)")
    return Veredito(
        aprovado=not motivos,
        motivos=tuple(motivos),
        notas={"palavras": round(sim, 2), "duracao_x": round(razao, 2)},
    )
