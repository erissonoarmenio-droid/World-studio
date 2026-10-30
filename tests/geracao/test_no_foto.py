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
