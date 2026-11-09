"""Voz-para-voz (09/11): conferência de palavras e ritmo, e a montagem com ElevenLabs falso."""

import io
import math
import struct
import wave

from app.geracao import voz_real as vr


def _wav(segundos: list[tuple[float, bool]], taxa: int = 16000) -> bytes:
    """Áudio sintético: trechos de 'fala' (tom 220 Hz) e silêncio."""
    amostras = []
    for dur, fala in segundos:
        for i in range(int(dur * taxa)):
            amostras.append(int(8000 * math.sin(2 * math.pi * 220 * i / taxa)) if fala else 0)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(struct.pack(f"<{len(amostras)}h", *amostras))
    return b.getvalue()


def test_acerto_de_palavras_ignora_acento_e_pontuacao():
    assert vr.acerto_palavras("Esse chambray é levinho, ó!", "esse chambray e levinho o") == 1.0
    assert vr.acerto_palavras("Me chama no direct", "me chama no") == 0.75


def test_ritmo_igual_e_diferente(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    c = tmp_path / "c.wav"
    a.write_bytes(_wav([(0.5, True), (0.5, False), (1.0, True), (0.5, False)]))
    b.write_bytes(_wav([(0.5, True), (0.5, False), (1.0, True), (0.5, False)]))
    c.write_bytes(_wav([(0.5, False), (1.0, True), (0.5, False), (0.5, True)]))
    assert vr.ritmo(a, b) > 0.95
    assert vr.ritmo(a, c) < 0.5


def test_troca_monta_video_e_confere(tmp_path):
    fala = _wav([(0.4, True), (0.3, False), (0.8, True), (0.5, False)])
    video = tmp_path / "v.mp4"
    (tmp_path / "f.wav").write_bytes(fala)
    vr._rodar([
        "-f", "lavfi", "-i", "color=c=gray:s=64x112:d=2", "-i", str(tmp_path / "f.wav"),
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video),
    ])  # fmt: skip

    class Falso:
        def trocar(self, voz_id, audio_wav):
            saida = tmp_path / "n.mp3"
            (tmp_path / "in.wav").write_bytes(audio_wav)
            vr._rodar(["-i", str(tmp_path / "in.wav"), str(saida)])
            return saida.read_bytes()

        def transcrever(self, audio):
            return "gente olha essa camisa"

    r = vr.trocar_voz_do_video(Falso(), "voz1", video.read_bytes(), "Gente, olha essa camisa.")
    assert r.palavras == 1.0 and r.ritmo > 0.9 and r.aprovado
    assert len(r.video) > 1000
