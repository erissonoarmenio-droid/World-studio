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


# ── Legenda (opcional, Eri 01/11: perguntada uma vez ao lojista) ─────────────────────────
ESTILO_ASS = (
    "[Script Info]\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
    "BorderStyle, Outline, Shadow, Alignment, MarginV\n"
    "Style: L,DejaVu Sans,{fonte},&H00FFFFFF,&H00000000,&H80000000,1,1,{contorno},1,2,{margem}\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Text\n"
)


def _tempo_ass(s: float) -> str:
    h, resto = divmod(max(s, 0.0), 3600)
    m, seg = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{seg:05.2f}"


def gerar_ass(
    palavras: list[tuple[str, float, float]], largura: int = 720, altura: int = 1280
) -> str:
    """Legenda em blocos de até 3 palavras (quebra na pontuação), parte de baixo do quadro,
    fora da área dos botões do Instagram. `palavras` = (texto, início, fim) em segundos."""
    escala = largura / 720
    texto = ESTILO_ASS.format(
        w=largura, h=altura, fonte=round(54 * escala), contorno=round(5 * escala),
        margem=round(300 * escala),
    )  # fmt: skip
    i = 0
    while i < len(palavras):
        grupo = [palavras[i]]
        while (
            len(grupo) < 3 and i + len(grupo) < len(palavras) and grupo[-1][0][-1:] not in ",.?!…"
        ):
            grupo.append(palavras[i + len(grupo)])
        inicio, fim = grupo[0][1], grupo[-1][2]
        if i + len(grupo) < len(palavras):  # fica na tela até a próxima, se a pausa for curta
            prox = palavras[i + len(grupo)][1]
            fim = prox if prox - fim < 0.4 else fim + 0.2
        frase = " ".join(p[0] for p in grupo).strip()
        texto += f"Dialogue: 0,{_tempo_ass(inicio)},{_tempo_ass(fim)},L,{frase}\n"
        i += len(grupo)
    return texto


def comando_legendar(entrada: Path, ass: Path, saida: Path, ffmpeg: str = "ffmpeg") -> list[str]:
    caminho = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return [
        ffmpeg, "-v", "error", "-y", "-i", str(entrada),
        "-vf", f"ass='{caminho}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy",
        str(saida),
    ]  # fmt: skip


def legendar(entrada: Path, palavras: list[tuple[str, float, float]], saida: Path) -> Path:
    ass = saida.with_suffix(".ass")
    ass.write_text(gerar_ass(palavras), encoding="utf-8")
    subprocess.run(comando_legendar(entrada, ass, saida), check=True, timeout=600)  # noqa: S603
    return saida
