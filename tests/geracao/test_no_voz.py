import json
from pathlib import Path

import pytest

from app.geracao.nos.base import PedidoBloqueado
from app.geracao.nos.voz import MODELO_IRMAO, EntradaVoz, NoVoz, conferir_voz

FALAS = json.loads((Path(__file__).parent / "casos" / "voz_falas_2910.json").read_text())


@pytest.mark.parametrize("c", sorted(FALAS["finais"]))
def test_as_5_falas_finais_passam(c):
    pedido, rel = NoVoz().preparar(EntradaVoz(fala=FALAS["finais"][c]))
    assert rel.falhas == []
    assert pedido.prompt.endswith("#### TRANSCRIPT\n" + FALAS["finais"][c])
    voz = pedido.payload["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voz["prebuiltVoiceConfig"]["voiceName"] == "Kore"


@pytest.mark.parametrize("c", ["c1", "c2", "c3", "c4"])
def test_falas_com_reticencias_sao_bloqueadas(c):
    with pytest.raises(PedidoBloqueado) as erro:
        NoVoz().preparar(EntradaVoz(fala=FALAS["antigas"][c]))
    assert "voz.sem_reticencias" in {f.regra_id for f in erro.value.relatorio.falhas}


def test_palavra_solta_no_comeco_so_avisa_e2():
    _, rel = NoVoz().preparar(EntradaVoz(fala="Andar, pegar as coisas, tudo certinho."))
    assert not rel.bloqueado
    assert [f.regra_id for f in rel.avisos] == ["voz.comeca_com_conector"]


def test_fala_que_nao_cabe_no_clipe_bloqueia():
    with pytest.raises(PedidoBloqueado):
        NoVoz().preparar(EntradaVoz(fala=FALAS["finais"]["c1"], duracao_max=5))


def test_voz_fora_do_cardapio_e_recusada():
    with pytest.raises(ValueError):
        EntradaVoz(fala="E ó, oi.", voz="Puck")


def test_modelo_irmao_quando_a_cota_acaba():
    p = NoVoz().montar_pedido(EntradaVoz(fala="E ó, oi."), modelo=MODELO_IRMAO)
    assert p.modelo == MODELO_IRMAO and not NoVoz().checar(p).bloqueado


def test_conferencia_reprova_os_casos_medidos_de_2910():
    lendo_instrucao = conferir_voz(FALAS["finais"]["c1"], FALAS["finais"]["c1"], 28.0)
    assert not lendo_instrucao.aprovado and "duração" in lendo_instrucao.motivos[0]
    engoliu = conferir_voz(
        "Andar, pegar as coisas, tudo certinho.", "Dá pegar as coisas tudo certinho", 2.5
    )
    assert not engoliu.aprovado and "palavras" in engoliu.motivos[0]


def test_conferencia_aprova_fala_certa_no_tempo():
    fala = FALAS["finais"]["c4"]
    assert conferir_voz(fala, "E ó, andando, pegando as coisas, tudo certinho", 3.6).aprovado
