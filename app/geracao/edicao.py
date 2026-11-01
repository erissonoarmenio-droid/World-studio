"""Edição depois da geração (Método W-orld v3, camada 7). Custo zero: só ffmpeg.

Tratamento de voz (E31, 01/11): a voz do Seedance 2.5 sai abafada — agudos 3–6 kHz 14 dB
abaixo dos médios (celular normal: 6–8 dB). Eri escolheu a versão "leve" ("mais natural"):
agudos ficam ~7 dB abaixo, volume no padrão do Instagram (−14 LUFS).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FILTRO_VOZ_LEVE = (
    "aresample=48000,highpass=f=90,"
    "equalizer=f=280:t=q:w=1.2:g=-3,"  # tira o grave embolado
    "equalizer=f=3200:t=q:w=1:g=3,"  # nitidez da fala
    "equalizer=f=5500:t=q:w=1:g=3,"  # presença
    "highshelf=f=9000:g=2,"  # um pouco de ar
    "acompressor=threshold=-20dB:ratio=3:attack=10:release=120:makeup=2,"
    "loudnorm=I=-14:TP=-1.5:LRA=9"
)


def comando_tratar_voz(entrada: Path, saida: Path, ffmpeg: str = "ffmpeg") -> list[str]:
    """Vídeo copiado como está; só o áudio passa pelo tratamento."""
    return [
        ffmpeg, "-v", "error", "-y", "-i", str(entrada),
        "-af", FILTRO_VOZ_LEVE,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(saida),
    ]  # fmt: skip


def tratar_voz(entrada: Path, saida: Path, ffmpeg: str = "ffmpeg") -> Path:
    # argumentos montados aqui (caminhos nossos), sem shell
    subprocess.run(comando_tratar_voz(entrada, saida, ffmpeg), check=True, timeout=300)  # noqa: S603
    return saida
