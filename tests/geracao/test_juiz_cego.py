"""Calibração real de 01/11 (7 vídeos × 2 rodadas): o juiz cego concorda com o olho de Eri."""

import pytest

from app.geracao.juiz_cego import julgar, melhor, payload

C = ("filmado_por_pessoa_real_0a100", "voz_natural_0a10", "corpo_natural_0a10",
     "camera_real_0a10", "pararia_de_rolar_0a10")  # fmt: skip
MEDIDO = {  # vídeo: [(real, voz, corpo, câmera, rolar) rodada 1, rodada 2], olho de Eri
    "v3_aprovado": ([(98, 10, 10, 10, 8), (100, 10, 10, 10, 8)], True),
    "sofa_prova": ([(100, 10, 10, 10, 6), (98, 9, 10, 10, 7)], True),
    "sofa_problema": ([(100, 10, 10, 10, 7), (100, 10, 10, 10, 7)], True),
    "v1_25_robotica": ([(95, 7, 9, 9, 6), (95, 4, 9, 9, 5)], False),
    "v2_25_parada": ([(95, 4, 8, 9, 5), (95, 4, 8, 9, 5)], False),
    "rej_20fast_A": ([(10, 2, 2, 3, 2), (15, 2, 3, 4, 2)], False),
    "rej_20fast_B": ([(5, 4, 3, 5, 2), (10, 4, 3, 5, 2)], False),
}


@pytest.mark.parametrize("nome", MEDIDO)
def test_concorda_com_eri_nas_duas_rodadas(nome):
    rodadas, eri = MEDIDO[nome]
    for r in rodadas:
        assert julgar(dict(zip(C, r, strict=True))).aprovado is eri


def test_escolhe_a_versao_que_mais_prende():
    a = julgar(dict(zip(C, (100, 10, 10, 10, 6), strict=True)))
    b = julgar(dict(zip(C, (98, 9, 10, 10, 8), strict=True)))
    ruim = julgar(dict(zip(C, (95, 4, 8, 9, 9), strict=True)))
    assert melhor([a, b, ruim]) is b
    assert melhor([ruim]) is None


def test_o_pedido_nao_conta_que_e_ia_nem_que_e_nosso():
    texto = payload(b"x")["contents"][0]["parts"][1]["text"].lower()
    assert "instagram story" in texto
    for proibido in ("generated", "test", "our ", "synthetic", "seedance"):
        assert proibido not in texto
