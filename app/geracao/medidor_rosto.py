"""Medidor de rosto (07/11, E41/E43): nota 0–100 de quanto a pessoa da foto gerada é a mesma
das fotos reais. Substitui o "juiz por visão" (que dava 7 para tudo, E41).

Como funciona (sem custo por uso, roda no servidor, CPU):
1. Acha o rosto e 5 pontos (olhos, nariz, cantos da boca) com o detector YuNet.
2. Alinha o rosto e tira a "impressão digital" dele (vetor de 128 números) com o SFace.
3. Compara com cada foto real (cosseno). Referência do OpenCV: mesma pessoa ≥ 0,363.
4. Compara também as proporções dos 5 pontos (boca, nariz, largura do rosto), que pegam rosto
   afinado ou "inflado" (E39/E40) mesmo quando a "impressão digital" ainda bate.

Modelos do OpenCV Zoo: YuNet (MIT) e SFace (Apache-2.0) — licenças que permitem uso comercial.
Baixados uma vez para MEDIDOR_MODELOS (padrão /app/modelos, baixados no build do Docker).
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

PASTA = Path(os.environ.get("MEDIDOR_MODELOS", "/app/modelos"))
BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
MODELOS = {
    "yunet.onnx": BASE + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "sface.onnx": BASE + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
MESMA_PESSOA = 0.363  # limiar do SFace (OpenCV) para "mesma pessoa"


def _baixar_modelos() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    for nome, url in MODELOS.items():
        alvo = PASTA / nome
        if alvo.exists() and alvo.stat().st_size > 100_000:
            continue
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 (URL fixa)
            alvo.write_bytes(r.read())


@lru_cache(maxsize=1)
def _reconhecedor() -> Any:
    import cv2

    _baixar_modelos()
    return cv2.FaceRecognizerSF.create(str(PASTA / "sface.onnx"), "")


def _detector(largura: int, altura: int) -> Any:
    import cv2

    _baixar_modelos()
    return cv2.FaceDetectorYN.create(str(PASTA / "yunet.onnx"), "", (largura, altura), 0.7, 0.3, 50)


NOMES = ("boca", "nariz", "olhos até a boca", "largura do rosto", "comprimento do rosto")


@dataclass
class Rosto:
    linha: np.ndarray  # saída do YuNet: x, y, w, h, 5 pontos (10), confiança
    vetor: np.ndarray
    altura_px: int

    @property
    def pontos(self) -> np.ndarray:
        return self.linha[4:14].reshape(5, 2)  # olho dir., olho esq., nariz, boca dir., esq.

    @property
    def proporcoes(self) -> np.ndarray:
        """Medidas divididas pela distância entre os olhos (não dependem do tamanho da foto)."""
        o1, o2, n, b1, b2 = self.pontos
        olhos = float(np.linalg.norm(o2 - o1))
        meio_olhos, meio_boca = (o1 + o2) / 2, (b1 + b2) / 2
        w, h = float(self.linha[2]), float(self.linha[3])
        return np.array(
            [
                np.linalg.norm(b2 - b1) / olhos,
                np.linalg.norm(n - meio_olhos) / olhos,
                np.linalg.norm(meio_boca - meio_olhos) / olhos,
                w / olhos,
                h / w,
            ]
        )

    @property
    def de_frente(self) -> bool:
        """Nariz perto do meio dos olhos = foto de frente (perfil mede errado)."""
        o1, o2, n, _, _ = self.pontos
        olhos = float(np.linalg.norm(o2 - o1))
        return abs(float(n[0] - (o1[0] + o2[0]) / 2)) / olhos < 0.25


def ler_rosto(conteudo: bytes) -> Rosto | None:
    """O maior rosto da foto (ou None se não achar)."""
    import cv2

    img = cv2.imdecode(np.frombuffer(conteudo, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    escala = min(1.0, 1280 / max(h, w))
    if escala < 1:
        img = cv2.resize(img, (int(w * escala), int(h * escala)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    _, rostos = _detector(w, h).detect(img)
    if rostos is None or not len(rostos):
        return None
    linha = max(rostos, key=lambda r: r[2] * r[3])
    rec = _reconhecedor()
    vetor = rec.feature(rec.alignCrop(img, linha)).flatten()
    return Rosto(linha, vetor / np.linalg.norm(vetor), int(linha[3]))


@dataclass
class Medida:
    nota: int  # 0–100: parecença do rosto com as fotos reais (100 = igual à própria foto)
    cosseno: float  # média com as fotos reais; ≥ 0,363 = mesma pessoa (OpenCV)
    proporcao: int  # 0–100: proporções do rosto iguais às reais (de frente)
    diferencas: list[str] = field(default_factory=list)
    achou_rosto: bool = True
    rosto_px: int = 0  # altura do rosto na foto (rosto pequeno mede pior)

    @property
    def aprovado(self) -> bool:
        return self.achou_rosto and self.nota >= NOTA_MINIMA and self.proporcao >= PROP_MINIMA


# limites iniciais; calibrados com as fotos aprovadas e reprovadas pelo Eri (07/11)
NOTA_MINIMA = 60
PROP_MINIMA = 60


def medir(reais: list[bytes], gerada: bytes) -> Medida:
    rr = [r for r in (ler_rosto(b) for b in reais) if r is not None]
    g = ler_rosto(gerada)
    if not rr or g is None:
        return Medida(0, 0.0, 0, ["rosto não encontrado"], achou_rosto=False)
    cos = float(np.mean([r.vetor @ g.vetor for r in rr]))
    # 0,20 (outra pessoa) → 0 · 0,363 (limiar) → ~33 · 0,70 (quase a mesma foto) → 100
    nota = int(round(np.clip((cos - 0.20) / 0.50, 0, 1) * 100))
    frente = [r for r in rr if r.de_frente] or rr
    pr = np.mean([r.proporcoes for r in frente], axis=0)
    desvio = (g.proporcoes - pr) / pr
    diferencas = [
        f"{n} {'maior' if d > 0 else 'menor'} {abs(d) * 100:.0f}%"
        for n, d in zip(NOMES, desvio, strict=True)
        if abs(d) > 0.08
    ]
    proporcao = int(round(np.clip(1 - float(np.abs(desvio).mean()) / 0.15, 0, 1) * 100))
    return Medida(nota, round(cos, 3), proporcao, diferencas, rosto_px=g.altura_px)
