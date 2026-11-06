"""Nó influencer (kit de identidade v2)."""

import pytest
from pydantic import ValidationError

from app.geracao.nos.base import PedidoBloqueado
from app.geracao.nos.foto import Imagem
from app.geracao.nos.influencer import EntradaInfluencer, NoInfluencer

FOTO = Imagem(mime="image/png", dados_b64="aGVsbG8gbXVuZG8=")
BASE = dict(
    genero="homem", idade=27, corpo="tall and slim build", roupa="plain white crew-neck t-shirt"
)
TRACOS = (
    "a wide, softly rounded face with full cheeks, thick dark eyebrows, a broad nose with a "
    "rounded tip and short dark stubble"
)


def test_principal_tem_corpo_inteiro_fundo_branco_idade_e_sem_texto():
    p, rel = NoInfluencer().preparar(
        EntradaInfluencer(modo="nova", aparencia="short dark wavy hair, brown eyes", **BASE)
    )
    t = p.prompt.lower()
    assert "full-body" in t and "white" in t and "27 years old" in t and "no text, no logos" in t
    assert " man" in t and p.payload["generationConfig"]["imageConfig"]["imageSize"] == "2K"
    assert not rel.bloqueado


def test_oculos_saem_iguais_e_sem_marca():
    p, _ = NoInfluencer().preparar(
        EntradaInfluencer(
            modo="da_pessoa",
            fotos=[FOTO] * 3,
            aparencia=TRACOS,
            oculos="black rectangular eyeglasses",
            **BASE,
        )
    )
    assert "same eyeglasses" in p.prompt and "no text or logo on the frame" in p.prompt
    assert len(p.payload["contents"][0]["parts"]) == 4  # texto + 3 fotos


def test_regras_de_entrada():
    with pytest.raises(ValidationError):
        EntradaInfluencer(
            modo="nova", fotos=[FOTO], aparencia="cabelo curto escuro e olhos", **BASE
        )
    with pytest.raises(ValidationError):
        EntradaInfluencer(modo="da_pessoa", fotos=[FOTO], aparencia=TRACOS, **BASE)  # só 1 rosto
    with pytest.raises(ValidationError):
        EntradaInfluencer(modo="da_pessoa", fotos=[FOTO] * 3, **BASE)  # sem os traços
    with pytest.raises(ValidationError):
        EntradaInfluencer(modo="nova", aparencia=TRACOS, enquadramento="close", **BASE)
    with pytest.raises(ValidationError):
        EntradaInfluencer(modo="nova", aparencia="x", **{**BASE, "idade": 17})


def test_corpo_sexualizado_e_barrado():
    with pytest.raises(PedidoBloqueado):
        NoInfluencer().preparar(
            EntradaInfluencer(
                modo="nova",
                aparencia="long dark hair and green eyes",
                **{**BASE, "corpo": "sexy busty"},
            )
        )


def test_pessoa_real_close_primeiro_com_pele_travada_e_corpo_separado():
    """06/11: 1ª ficha do Eri saiu com rosto mais fino e pele mais oliva."""
    corpo = Imagem(mime="image/jpeg", dados_b64="Y29ycG8=")
    p, rel = NoInfluencer().preparar(
        EntradaInfluencer(
            modo="da_pessoa",
            fotos=[FOTO] * 4,
            foto_corpo=corpo,
            enquadramento="close",
            aparencia=TRACOS,
            **BASE,
        )
    )
    t = p.prompt.lower()
    assert not rel.bloqueado, rel.resumo()
    assert "close-up portrait" in t and "full-body photo" not in t
    assert "key features to keep: a wide, softly rounded face" in t
    assert "skin tone exactly as in images 1 to 4" in t and "more olive" in t
    assert "image 5 shows his real body" in t and "not for clothing" in t
    partes = p.payload["contents"][0]["parts"]
    assert len(partes) == 6 and partes[-1]["inlineData"]["data"] == "Y29ycG8="

    principal, rel2 = NoInfluencer().preparar(
        EntradaInfluencer(modo="da_pessoa", fotos=[FOTO] * 2, aparencia=TRACOS, **BASE)
    )
    assert "full-body" in principal.prompt.lower() and not rel2.bloqueado
