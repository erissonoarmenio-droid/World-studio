import pytest
from pydantic import ValidationError

from app.geracao.nos.provador import EntradaProvador, NoProvador

IMG = {"mime": "image/jpeg", "dados_b64": "aGVsbG9oZWxsbw=="}
BASE = dict(
    foto_real=IMG,
    peca_fotos=[IMG, IMG],
    peca="a long-sleeve white shirt with fine navy stripes and a chest pocket",
    cenario="a bright Brazilian womenswear boutique",
)


def test_provador_muda_so_roupa_e_fundo_e_mantem_o_rosto_real():
    pedido, rel = NoProvador().preparar(EntradaProvador(**BASE))
    assert "Keep her face exactly as it is in image 1" in pedido.prompt
    assert "Images 2 to 3" in pedido.prompt
    assert "years old" not in pedido.prompt
    assert pedido.payload["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
    assert len(pedido.payload["contents"][0]["parts"]) == 4


def test_provador_homem_e_sem_idade_no_texto():
    pedido, _ = NoProvador().preparar(EntradaProvador(**BASE, genero="homem"))
    assert "Keep his face exactly" in pedido.prompt
    with pytest.raises(ValidationError):
        EntradaProvador(**{**BASE, "cenario": "a shop, she looks in her forties"})
