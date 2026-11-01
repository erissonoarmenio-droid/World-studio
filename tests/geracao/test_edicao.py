"""Tratamento de voz (E31): o filtro escolhido por Eri e, se houver ffmpeg, o efeito medido."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.geracao.edicao import FILTRO_VOZ_LEVE, comando_tratar_voz, tratar_voz

FFMPEG = shutil.which("ffmpeg")


def test_comando_copia_o_video_e_trata_so_o_audio(tmp_path: Path):
    cmd = comando_tratar_voz(tmp_path / "a.mp4", tmp_path / "b.mp4")
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-af") + 1] == FILTRO_VOZ_LEVE
    assert "loudnorm=I=-14" in FILTRO_VOZ_LEVE


def _rms_na_faixa(mp4: Path, centro: int, largura: int) -> float:
    saida = subprocess.run(  # noqa: S603 - ffmpeg local, caminhos do teste
        [FFMPEG, "-v", "info", "-i", str(mp4), "-af",
         f"bandpass=f={centro}:width_type=h:w={largura},astats=measure_overall=RMS_level",
         "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return float(re.findall(r"RMS level dB: (-?[\d.]+)", saida.stderr)[-1])


@pytest.mark.skipif(FFMPEG is None, reason="sem ffmpeg")
def test_tratamento_levanta_os_agudos(tmp_path: Path):
    # "voz abafada" sintética: ruído rosa passado num passa-baixa de 1,5 kHz
    bruto = tmp_path / "bruto.mp4"
    subprocess.run(  # noqa: S603
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=3",
         "-f", "lavfi", "-i", "anoisesrc=c=pink:d=3:a=0.3,lowpass=f=1500",
         "-shortest", "-c:v", "libx264", "-c:a", "aac", str(bruto)],
        check=True,
    )  # fmt: skip
    tratado = tratar_voz(bruto, tmp_path / "tratado.mp4", ffmpeg=FFMPEG)
    antes = _rms_na_faixa(bruto, 4500, 3000) - _rms_na_faixa(bruto, 650, 700)
    depois = _rms_na_faixa(tratado, 4500, 3000) - _rms_na_faixa(tratado, 650, 700)
    assert depois > antes + 2  # agudos sobem em relação aos médios (no v3 real: +5 dB)
