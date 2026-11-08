def test_e42_idade_vem_das_fotos_reais():
    import pytest
    from pydantic import ValidationError

    from app.geracao.nos.rosto_fixo import EntradaRostoFixo, NoRostoFixo

    img = {"mime": "image/jpeg", "dados_b64": "aGVsbG9oZWxsbw=="}
    tracos = "an oval face with softly defined cheekbones, a gently tapered jaw, freckles"
    pedido, _ = NoRostoFixo().preparar(EntradaRostoFixo(base=img, rostos=[img, img], tracos=tracos))
    assert "same apparent age as in images 2 to 3" in pedido.prompt
    assert "years old" not in pedido.prompt
    homem, _ = NoRostoFixo().preparar(
        EntradaRostoFixo(base=img, rostos=[img, img], tracos=tracos, genero="homem")
    )
    assert "He looks exactly the same apparent age" in homem.prompt
    with pytest.raises(ValidationError):
        EntradaRostoFixo(
            base=img, rostos=[img, img], tracos=tracos + "; fine lines of a woman in her forties"
        )
