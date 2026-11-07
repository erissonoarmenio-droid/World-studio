"""Nó rosto_fixo: trava o rosto da pessoa real numa foto já gerada (06/11)."""

import pytest
from pydantic import ValidationError

from app.geracao.nos.foto import Imagem
from app.geracao.nos.rosto_fixo import EntradaRostoFixo, NoRostoFixo

BASE = Imagem(mime="image/png", dados_b64="YmFzZS1nZXJhZGE=")
REAL = Imagem(mime="image/jpeg", dados_b64="cm9zdG8tcmVhbA==")
TRACOS = "a wide, softly rounded face with full cheeks and a broad, rounded jawline"


def test_troca_so_o_rosto_sem_afinar_no_mesmo_formato():
    p, rel = NoRostoFixo().preparar(
        EntradaRostoFixo(base=BASE, rostos=[REAL] * 3, tracos=TRACOS, oculos="black glasses")
    )
    assert not rel.bloqueado, rel.resumo()
    t = p.prompt.lower()
    assert "change only the face" in t and "keep everything else in image 1 identical" in t
    assert "images 2 to 4 are real photos" in t and "do not slim" in t
    assert "every detail of the garment" in t and "skin tone exactly" in t
    partes = p.payload["contents"][0]["parts"]
    assert partes[1]["inlineData"]["data"] == BASE.dados_b64 and len(partes) == 5
    assert p.payload["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"


def test_precisa_de_2_fotos_reais_e_dos_tracos():
    with pytest.raises(ValidationError):
        EntradaRostoFixo(base=BASE, rostos=[REAL], tracos=TRACOS)
    with pytest.raises(ValidationError):
        EntradaRostoFixo(base=BASE, rostos=[REAL] * 2, tracos="rosto")
