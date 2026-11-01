"""Nó foto de produto: extrair a peça → cena. Caso real: camisa terracota (01/11)."""

import pytest

from app.geracao.nos.foto import Imagem
from app.geracao.nos.foto_produto import EntradaProduto, NoFotoProduto, sugestao

FOTO = Imagem(mime="image/jpeg", dados_b64="AAAAAAAAAAAA")
DET = (
    "same terracotta colour and matte slubby linen-cotton texture, pointed collar, small brown "
    "buttons, two chest pockets with pointed flaps and one button each, the small black woven "
    "label on the wearer's left chest pocket and the black neck label"
)


def _e(**m):
    d = dict(etapa="cena", foto=FOTO, peca_nome="shirt", detalhes=DET, cena="cama")
    d.update(m)
    return EntradaProduto(**d)


def _ids(r):
    return {f.regra_id for f in r.falhas}


def test_extrair_sem_pessoa_e_com_a_peca_travada():
    p, r = NoFotoProduto().preparar(_e(etapa="extrair"))
    assert r.falhas == []
    assert "flat lay" in p.prompt and "no person" in p.prompt and DET in p.prompt
    assert p.payload["generationConfig"]["imageConfig"]["aspectRatio"] == "4:5"


@pytest.mark.parametrize("cena", ["cama", "mesa", "arara"])
def test_as_tres_cenas_testadas_passam(cena):
    p, r = NoFotoProduto().preparar(_e(cena=cena))
    assert r.falhas == []
    assert "EXACTLY as in image 1" in p.prompt and "real, slightly imperfect smartphone" in p.prompt


def test_cena_livre_com_maos_ganha_cinco_dedos():
    p, r = NoFotoProduto().preparar(
        _e(cena="livre", cena_livre="the shirt held by two hands over a wooden floor with sneakers")
    )
    assert "five fingers" in p.prompt and r.falhas == []


def test_cena_livre_vazia_recusada():
    with pytest.raises(ValueError):
        _e(cena="livre", cena_livre="chão")


def test_atlas_bloqueia():
    no = NoFotoProduto()
    relatorio = no.checar(no.montar_pedido(_e(), fornecedor="atlas"))
    assert relatorio.bloqueado and "produto.google_direto" in _ids(relatorio)


def test_sugestao_natural_sem_menu_e_variando():
    s = sugestao("camisa")
    assert "camisa" in s and "na cama" in s and "dobrada na mesa" in s
    assert "1)" not in s and "\n" not in s
    s2 = sugestao("camisa", ja_feitas=("cama", "mesa"))
    assert "pendurada na arara" in s2 and "na cama" not in s2
