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
            modo="da_pessoa", fotos=[FOTO] * 3, oculos="black rectangular eyeglasses", **BASE
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
        EntradaInfluencer(modo="da_pessoa", fotos=[FOTO], **BASE)  # menos de 3 fotos
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
