"""Voz da pessoa real no vídeo (09/11): método fixo "voz-para-voz" (E28, medido em 31/10).

Por que não "vídeo sem voz + voz por cima": a boca fica parada ou fora do tempo, e o
lip-sync depois (Sync-3) foi reprovado pelo Eri (30/10). O caminho medido é:
1. O Seedance gera o vídeo FALANDO (a boca sai no tempo certo).
2. Tira o áudio do vídeo → ElevenLabs troca só o timbre pela voz clonada da pessoa
   (voice changer, `eleven_multilingual_sts_v2`) — ritmo 94% igual, palavras 100% (31/10).
3. Filtro de voz leve (E31) e mistura com o som do lugar, que só aparece nas pausas
   (o som original é "abaixado" enquanto a voz nova fala, para não ouvir a voz antiga).
4. Confere: palavras (transcrição) e ritmo (envelope da voz antiga × nova) antes de entregar.

A voz da pessoa é clonada UMA vez (1–2 min de áudio, com consentimento "clone") e o código
fica guardado para todos os vídeos. Se a pessoa cancelar, a voz é apagada no ElevenLabs.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from pydantic import SecretStr

from app.geracao.edicao import FILTRO_VOZ_LEVE

API = "https://api.elevenlabs.io/v1"
MODELO_TROCA = "eleven_multilingual_sts_v2"
MODELO_TRANSCRICAO = "scribe_v1"
RITMO_MINIMO = 0.90  # envelope da voz nova × antiga (31/10: 0,94)


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:  # pragma: no cover - máquina com ffmpeg instalado
        return "ffmpeg"


def _rodar(args: list[str]) -> None:
    # argumentos montados aqui (caminhos nossos), sem shell
    subprocess.run([_ffmpeg(), "-v", "error", "-y", *args], check=True, timeout=300)  # noqa: S603


class ElevenLabs:
    def __init__(self, chave: SecretStr, cliente: httpx.Client | None = None) -> None:
        self._chave = chave
        self._http = cliente or httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0))

    def _post(self, caminho: str, **kw: Any) -> httpx.Response:
        r = self._http.post(
            f"{API}{caminho}", headers={"xi-api-key": self._chave.get_secret_value()}, **kw
        )
        if r.status_code >= 400:  # mensagem do ElevenLabs, nunca a chave
            raise RuntimeError(f"ElevenLabs {caminho} → {r.status_code}: {r.text[:300]}")
        return r

    def clonar(self, nome: str, audio: bytes, tipo: str) -> str:
        """Clone instantâneo (IVC) com limpeza de ruído. Devolve o voice_id."""
        r = self._post(
            "/voices/add",
            data={
                "name": nome,
                "remove_background_noise": "true",
                "description": "Voz da pessoa real, com consentimento (Desfila)",
            },
            files={"files": ("amostra", audio, tipo)},
        )
        return str(r.json()["voice_id"])

    def trocar(self, voz_id: str, audio_wav: bytes) -> bytes:
        """Voice changer: mesma fala e ritmo, timbre da voz clonada. Devolve mp3."""
        r = self._post(
            f"/voice-changer/{voz_id}",
            params={"output_format": "mp3_44100_128"},
            data={"model_id": MODELO_TROCA, "remove_background_noise": "true"},
            files={"audio": ("fala.wav", audio_wav, "audio/wav")},
        )
        return r.content

    def transcrever(self, audio: bytes) -> str:
        r = self._post(
            "/speech-to-text",
            data={"model_id": MODELO_TRANSCRICAO, "language_code": "por"},
            files={"file": ("fala.mp3", audio, "audio/mpeg")},
        )
        return str(r.json().get("text", ""))


def _envelope(caminho: Path) -> np.ndarray:
    """Energia da fala a cada 20 ms (16 kHz mono)."""
    with tempfile.TemporaryDirectory() as d:
        bruto = Path(d) / "a.raw"
        _rodar(["-i", str(caminho), "-ac", "1", "-ar", "16000", "-f", "s16le", str(bruto)])
        x = np.frombuffer(bruto.read_bytes(), dtype=np.int16).astype(np.float32)
    n = len(x) // 320
    return np.sqrt((x[: n * 320].reshape(n, 320) ** 2).mean(1)) if n else np.zeros(1)


def ritmo(a: Path, b: Path) -> float:
    """Correlação dos envelopes de fala (1 = mesmo ritmo; a boca continua batendo)."""
    ea, eb = _envelope(a), _envelope(b)
    n = min(len(ea), len(eb))
    if n < 10:
        return 0.0
    ea, eb = ea[:n], eb[:n]
    if ea.std() == 0 or eb.std() == 0:
        return 0.0
    return float(np.corrcoef(ea, eb)[0, 1])


def _palavras(t: str) -> list[str]:
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)


def acerto_palavras(esperado: str, ouvido: str) -> float:
    """Fração das palavras do roteiro que aparecem na transcrição, na ordem."""
    alvo, ouv = _palavras(esperado), _palavras(ouvido)
    if not alvo:
        return 1.0
    i = acertos = 0
    for w in alvo:
        j = i
        while j < len(ouv) and ouv[j] != w:
            j += 1
        if j < len(ouv):
            acertos += 1
            i = j + 1
    return acertos / len(alvo)


@dataclass
class VozTrocada:
    video: bytes
    ritmo: float
    palavras: float
    transcricao: str

    @property
    def aprovado(self) -> bool:
        return self.ritmo >= RITMO_MINIMO and self.palavras >= 0.9


def trocar_voz_do_video(
    el: ElevenLabs, voz_id: str, video: bytes, falas: str, ambiente: float = 0.25
) -> VozTrocada:
    """Passos 2–4 do método. `falas` = texto do roteiro (para conferir as palavras)."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "v.mp4").write_bytes(video)
        _rodar(["-i", str(p / "v.mp4"), "-vn", "-ac", "1", "-ar", "44100", str(p / "orig.wav")])
        (p / "nova.mp3").write_bytes(el.trocar(voz_id, (p / "orig.wav").read_bytes()))
        # voz nova tratada (E31) + som do lugar abaixado enquanto ela fala (sem "voz fantasma")
        filtro = (
            f"[1:a]{FILTRO_VOZ_LEVE.replace('loudnorm=I=-14:TP=-1.5:LRA=9', 'volume=1')},"
            "asplit=2[voz][chave];"
            f"[0:a]volume={ambiente}[amb];"
            "[amb][chave]sidechaincompress=threshold=0.015:ratio=20:attack=5:release=350[fundo];"
            "[voz][fundo]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-14:TP=-1.5:LRA=9[a]"
        )
        _rodar([
            "-i", str(p / "v.mp4"), "-i", str(p / "nova.mp3"),
            "-filter_complex", filtro, "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(p / "final.mp4"),
        ])  # fmt: skip
        r = ritmo(p / "orig.wav", p / "nova.mp3")
        ouvido = el.transcrever((p / "nova.mp3").read_bytes())
        return VozTrocada(
            (p / "final.mp4").read_bytes(), round(r, 3), acerto_palavras(falas, ouvido), ouvido
        )
