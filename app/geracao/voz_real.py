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

import json
import re
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
MODELO_FALA = "eleven_v3"  # voz-guia: entende marcas de jeito ([calm], [casual])
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


@dataclass(frozen=True)
class Ajuste:
    """Ajustes da troca (10/11, pesquisa): padrão do ElevenLabs (0,5/0,75) soou mecânico.
    Diálogo: estabilidade ~0,45, semelhança ~0,8; estilo 0 quando a entrada já é expressiva."""

    estabilidade: float = 0.45
    semelhanca: float = 0.80
    estilo: float = 0.0
    limpar_entrada: bool = False


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

    def trocar(self, voz_id: str, audio_wav: bytes, ajuste: Ajuste | None = None) -> bytes:
        """Voice changer: mesma fala e ritmo, timbre da voz clonada. Devolve mp3."""
        a = ajuste or Ajuste()
        r = self._post(
            f"/voice-changer/{voz_id}",
            params={"output_format": "mp3_44100_128"},
            data={
                "model_id": MODELO_TROCA,
                "remove_background_noise": "true" if a.limpar_entrada else "false",
                "voice_settings": json.dumps(
                    {
                        "stability": a.estabilidade,
                        "similarity_boost": a.semelhanca,
                        "style": a.estilo,
                        "use_speaker_boost": True,
                    }
                ),
            },
            files={"audio": ("fala.wav", audio_wav, "audio/wav")},
        )
        return r.content

    def falar(self, voz_id: str, texto: str, modelo: str = MODELO_FALA) -> bytes:
        """Texto → fala com a voz clonada (voz-guia). eleven_v3 entende marcas como [calm]."""
        corpo: dict[str, Any] = {
            "text": texto,
            "model_id": modelo,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }
        if modelo != MODELO_FALA:
            corpo["text"] = re.sub(r"\[[^\]]*\]\s*", "", texto)  # marcas só no v3
        try:
            r = self._post(
                f"/text-to-speech/{voz_id}",
                params={"output_format": "mp3_44100_128"},
                json=corpo,
            )
        except RuntimeError:
            if modelo != MODELO_FALA:
                raise
            return self.falar(voz_id, texto, "eleven_multilingual_v2")  # v3 indisponível
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
    el: ElevenLabs,
    voz_id: str,
    video: bytes,
    falas: str,
    ambiente: float = 0.25,
    ajuste: Ajuste | None = None,
) -> VozTrocada:
    """Passos 2–4 do método. `falas` = texto do roteiro (para conferir as palavras)."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "v.mp4").write_bytes(video)
        _rodar(["-i", str(p / "v.mp4"), "-vn", "-ac", "1", "-ar", "44100", str(p / "orig.wav")])
        (p / "nova.mp3").write_bytes(el.trocar(voz_id, (p / "orig.wav").read_bytes(), ajuste))
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


# ── Voz-guia (11/11): o Seedance copia ritmo e ENTONAÇÃO do @audio1 (E28) ─────────────
# Eri (10/11, vídeo 56): "melhor, mas ainda meio afeminado". A troca de voz muda o timbre e
# mantém a melodia da atuação do Seedance. Com a voz-guia (as falas ditas pelo clone, num
# jeito calmo de homem), a atuação já nasce com a melodia certa; depois a troca de voz.
JEITO_GUIA = {
    "homem": "[calm] [casual] ",
    "mulher": "[warm] [casual] ",
}


def _duracao(caminho: Path) -> float:
    with tempfile.TemporaryDirectory() as d:
        bruto = Path(d) / "a.raw"
        _rodar(["-i", str(caminho), "-ac", "1", "-ar", "16000", "-f", "s16le", str(bruto)])
        return bruto.stat().st_size / 32000


def montar_voz_guia(
    el: ElevenLabs,
    voz_id: str,
    falas: list[tuple[float, float, str]],
    duracao: float,
    genero: str = "homem",
    folga: float = 0.25,
) -> tuple[bytes, list[str]]:
    """Cada fala gerada pelo clone e colocada no início do seu plano. Devolve (mp3, avisos)."""
    avisos: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        entradas: list[str] = []
        atrasos: list[str] = []
        fim_anterior = 0.0
        for i, (inicio, fim, texto) in enumerate(falas):
            arq = p / f"f{i}.mp3"
            arq.write_bytes(el.falar(voz_id, JEITO_GUIA.get(genero, "") + texto))
            dur = _duracao(arq)
            comeco = max(inicio + folga, fim_anterior + 0.1)
            if comeco + dur > fim + 0.3:
                avisos.append(f"fala {i + 1} passa do plano ({dur:.1f}s em {fim - inicio:.1f}s)")
            fim_anterior = comeco + dur
            entradas += ["-i", str(arq)]
            ms = int(comeco * 1000)
            atrasos.append(f"[{i}:a]adelay={ms}|{ms},aresample=44100[a{i}]")
        mix = ";".join(atrasos) + ";" + "".join(f"[a{i}]" for i in range(len(falas)))
        mix += f"amix=inputs={len(falas)}:normalize=0,apad=whole_dur={duracao}[o]"
        saida = p / "guia.mp3"
        _rodar(
            [
                *entradas,
                "-filter_complex",
                mix,
                "-map",
                "[o]",
                "-t",
                str(duracao),
                "-ac",
                "1",
                str(saida),
            ]
        )
        if fim_anterior > duracao:
            avisos.append("as falas passam do fim do vídeo")
        return saida.read_bytes(), avisos
