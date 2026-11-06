import json
from pathlib import Path

import pytest

from app.geracao.nos.base import PedidoBloqueado
from app.geracao.nos.foto import EntradaFoto, Imagem, NoFoto

F = json.loads((Path(__file__).parent / "casos" / "foto_google_2910.json").read_text())
REF = Imagem(dados_b64="aW5mbHVlbmNlcg==")
ANC = Imagem(mime="image/png", dados_b64="YW5jb3JhIGMx")


def entrada(c: str, **troca) -> EntradaFoto:
    dados = dict(
        influencer=REF,
        idade=25,
        aparencia=F["aparencia"],
        peca=F["peca"],
        cenario=F["cenario"],
        cena=F["casos"][c]["cena"],
        sequencia=True,
        e_ancora=c == "c1",
        ancora=None if c == "c1" else ANC,
    )
    return EntradaFoto(**(dados | troca))


@pytest.mark.parametrize("c", ["c1", "c2", "c4", "c5"])
def test_pedidos_de_2910_passam_e_saem_identicos(c):
    pedido, rel = NoFoto().preparar(entrada(c))
    assert pedido.prompt == F["casos"][c]["prompt_2910"]
    assert not rel.bloqueado, rel.resumo()
    assert [f.regra_id for f in rel.avisos] == (
        ["foto.cinco_dedos_mao_citada"] if c in ("c1", "c5") else []
    )
    partes = pedido.payload["contents"][0]["parts"]
    assert len(partes) == (2 if c == "c1" else 3)


def test_espelho_de_2910_sem_one_single_e_barrado_e_corrigido_passa():
    with pytest.raises(PedidoBloqueado) as erro:
        NoFoto().preparar(entrada("c3"))
    assert [f.regra_id for f in erro.value.relatorio.falhas] == ["foto.um_espelho_so"]
    cena = F["casos"]["c3"]["cena"].replace("the boutique's tall mirror", "ONE single tall mirror")
    _, rel = NoFoto().preparar(entrada("c3", cena=cena))
    assert not rel.bloqueado


def test_sequencia_sem_ancora_bloqueia():
    with pytest.raises(PedidoBloqueado) as erro:
        NoFoto().preparar(entrada("c4", ancora=None))
    assert "foto.ancora_na_sequencia" in {f.regra_id for f in erro.value.relatorio.falhas}


def test_pedido_pela_atlas_e_recusado():
    no = NoFoto()
    p = no.montar_pedido(entrada("c1"), fornecedor="atlas")
    assert "foto.so_google" in {f.regra_id for f in no.checar(p).falhas if f.nivel == "bloqueia"}


def test_cena_de_maos_sem_five_fingers_bloqueia():
    cena = "SCENE: she waves with one hand at the camera."
    with pytest.raises(PedidoBloqueado) as erro:
        NoFoto().preparar(entrada("c5", cena=cena))
    assert "foto.cinco_dedos_nas_maos" in {f.regra_id for f in erro.value.relatorio.falhas}


def test_influencer_menor_ou_ancora_errada_sao_recusadas():
    with pytest.raises(ValueError):
        entrada("c2", idade=17)
    with pytest.raises(ValueError):
        entrada("c1", ancora=ANC)


def test_corpo_novo_troca_a_trava_do_corpo():
    from app.geracao.nos.foto import EntradaFoto, Imagem, NoFoto

    im = Imagem(dados_b64="xxxxxxxxxx")
    e = EntradaFoto(
        influencer=im,
        idade=25,
        peca="She wears a white t-shirt.",
        cenario="a boutique",
        cena="SCENE: full body.",
        corpo="hourglass figure, fuller bust and hips, defined waist",
    )
    p, rel = NoFoto().preparar(e)
    assert "body and age" not in p.prompt and "Body: hourglass figure" in p.prompt
    ruim = e.model_copy(update={"corpo": "sexy busty body"})
    assert "foto.corpo_sem_sexualizar" in {
        f.regra_id for f in NoFoto().checar(NoFoto().montar_pedido(ruim)).falhas
    }


def test_homem_troca_pronomes_e_passa_nas_regras():
    """06/11: influencer homem (o Eri). Mulher sai idêntica; homem sem 'she/her/woman'."""
    pedido_m, _ = NoFoto().preparar(entrada("c2"))
    pedido_h, rel = NoFoto().preparar(entrada("c2", genero="homem"))
    assert pedido_m.prompt == F["casos"]["c2"]["prompt_2910"]
    assert not rel.bloqueado, rel.resumo()
    import re

    assert not re.search(r"\b(she|her|herself|woman)\b", pedido_h.prompt, re.I)
    assert "the same man" in pedido_h.prompt.lower()


def test_foto_da_peca_real_e_tracos_do_rosto():
    """06/11: a peça ia só por texto; agora a foto da peça entra como imagem (Fit Check)."""
    import re

    p, rel = NoFoto().preparar(
        entrada("c2", genero="homem", tracos="a wide, softly rounded face", peca_fotos=[REF, REF])
    )
    assert not rel.bloqueado, rel.resumo()
    t = p.prompt
    assert "Images 3 to 4 = photos of the real garment" in t  # 1 rosto, 2 âncora, 3–4 peça
    assert "person from image 1" in t and "embroidery or print" in t
    assert "Key features to keep: a wide, softly rounded face" in t and "more olive" in t
    assert not re.search(r"\b(she|her|woman)\b", t, re.I)
    assert len(p.payload["contents"][0]["parts"]) == 5
