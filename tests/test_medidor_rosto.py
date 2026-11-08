"""Medidor de rosto (07/11): roda só onde os modelos e uma foto de teste existem."""

import io
import os
from pathlib import Path

import pytest

skdata = pytest.importorskip("skimage.data")
PASTA = Path(os.environ.get("MEDIDOR_MODELOS", "/app/modelos"))
pytestmark = pytest.mark.skipif(
    not (PASTA / "sface.onnx").exists(), reason="modelos do medidor não baixados"
)


def _jpg(img) -> bytes:  # noqa: ANN001
    from PIL import Image

    b = io.BytesIO()
    Image.fromarray(img).save(b, "JPEG")
    return b.getvalue()


def test_mesma_foto_100_e_rosto_esticado_perde_proporcao():
    from PIL import Image

    from app.geracao.medidor_rosto import medir

    foto = skdata.astronaut()
    real = _jpg(foto)
    assert medir([real], real).nota == 100
    esticada = _jpg(__import__("numpy").asarray(Image.fromarray(foto).resize((400, 512))))
    m = medir([real], esticada)
    assert m.proporcao < 70
    assert any("comprimento" in d for d in m.diferencas)
