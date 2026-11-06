"""Diretor UGC: pedido livre → 2 ângulos que passam no nó, com 1 correção no máximo."""

from __future__ import annotations

import copy
import json

import pytest

from app.geracao.diretor_ugc import DirecaoFalhou, DiretorUGC


def _video(angulo: str) -> dict:
    return {
        "angulo": angulo,
        "duracao": 16,
        "contexto": "a young woman shows a shirt. It must feel like a real, slightly messy "
        "story, not a fashion commercial.",
        "cenario": "The store room stays as in @image1.",
        "luz": "Soft daylight from a window on the left",
        "som_peca": "soft fabric rustle, wooden hanger click",
        "planos": [
            {"inicio": 0, "fim": 5, "acao": "Starts mid-movement: she walks two steps toward "
             "the camera holding the shirt and says:", "fala": "Gente, olha isso, chegou hoje."},
            {"inicio": 5, "fim": 10, "enquadramento": "Slightly closer", "acao": "She turns "
             "sideways and holds the shirt against her torso:", "fala": "Linho, ó, tipo."},
            {"inicio": 10, "fim": 16, "enquadramento": "Chest-up", "acao": "She leans toward "
             "the lens and says:", "fala": "Me chama no direct, tá?"},
        ],
    }  # fmt: skip


BOM = {
    "mensagem_para_lojista": "Vou pegar a camisa da arara e contar que chegou, beleza?",
    "peca_nome": "shirt",
    "peca": "terracotta long-sleeve shirt (two flap pockets with buttons, pointed collar)",
    "peca_nunca": "colour, collar, pockets, buttons or fabric",
    "videos": [_video("problema_solucao"), _video("prova_pessoal")],
}


class Falso:
    def __init__(self, *respostas: dict) -> None:
        self.respostas = list(respostas)
        self.textos: list[str] = []

    def json(self, sistema, texto, imagens=None):
        self.textos.append(texto)
        return self.respostas.pop(0)


def test_roteiro_bom_passa_de_primeira():
    cerebro = Falso(BOM)
    d = DiretorUGC(cerebro).dirigir("ela pegando da arara", "camisa terracota", "https://x/q.jpg")
    assert d.tentativas == 1
    assert [v.angulo for v in d.videos] == ["problema_solucao", "prova_pessoal"]
    assert all(v.pedido.payload["model"] == "seedance-2-5" for v in d.videos)
    assert "arara" in d.mensagem_para_lojista


def test_roteiro_parado_e_corrigido_uma_vez():
    ruim = copy.deepcopy(BOM)
    ruim["videos"][0]["planos"][1]["acao"] = "She smiles at the fabric:"
    cerebro = Falso(ruim, BOM)
    d = DiretorUGC(cerebro).dirigir("", "camisa", "https://x/q.jpg")
    assert d.tentativas == 2
    assert "ugc.corpo_vivo" in cerebro.textos[1]
    assert "(não disse o que quer — sugira)" in cerebro.textos[0]


def test_falha_duas_vezes_para_e_relata():
    ruim = copy.deepcopy(BOM)
    ruim["videos"][1]["planos"][2]["fala"] = "Gente, é imperdível!"
    with pytest.raises(DirecaoFalhou) as erro:
        DiretorUGC(Falso(ruim, ruim)).dirigir("x", "camisa", "https://x/q.jpg")
    assert "ugc.sem_propaganda" in str(erro.value)


def test_angulo_faltando_pede_correcao():
    so_um = copy.deepcopy(BOM)
    so_um["videos"] = [so_um["videos"][0]]
    cerebro = Falso(so_um, BOM)
    d = DiretorUGC(cerebro).dirigir("x", "camisa", "https://x/q.jpg")
    assert d.tentativas == 2
    assert "ângulos" in cerebro.textos[1]


def test_json_quebrado_pede_correcao():
    cerebro = Falso({"videos": "nada"}, BOM)
    d = DiretorUGC(cerebro).dirigir("x", "camisa", "https://x/q.jpg")
    assert d.tentativas == 2
    assert json.loads(json.dumps(d.mensagem_para_lojista))


def test_encaixar_tempos_pela_fala_medida():
    """Caso real do sofá (01/11): falas de 4,68 / 3,79 / 2,19 / 1,57 s em planos de 15 s."""
    from app.geracao.diretor_ugc import encaixar_tempos

    planos = [
        {"inicio": 0, "fim": 4.5}, {"inicio": 4.5, "fim": 8.5},
        {"inicio": 8.5, "fim": 12}, {"inicio": 12, "fim": 15},
    ]  # fmt: skip
    novos, duracao = encaixar_tempos(planos, [4.68, 3.79, 2.19, 1.57])
    assert duracao == 16
    assert novos[0]["inicio"] == 0 and novos[-1]["fim"] == 16
    for p, d in zip(novos, [4.68, 3.79, 2.19, 1.57], strict=True):
        assert p["fim"] - p["inicio"] >= 0.3 + d + 0.6 - 0.05
    assert all(a["fim"] == b["inicio"] for a, b in zip(novos, novos[1:], strict=False))


def test_fala_que_nao_cabe_em_16s_avisa():
    from app.geracao.diretor_ugc import FalaNaoCabe, encaixar_tempos

    planos = [{"inicio": 0, "fim": 5}, {"inicio": 5, "fim": 10}, {"inicio": 10, "fim": 15}]
    with pytest.raises(FalaNaoCabe):
        encaixar_tempos(planos, [6.0, 6.0, 5.0])


def test_homem_avisa_o_cerebro_e_vai_para_as_entradas():
    cerebro = Falso(BOM)
    d = DiretorUGC(cerebro).dirigir("x", "camisa", "https://x/q.jpg", genero="homem")
    assert "HOMEM" in cerebro.textos[0]
    assert all("THE MAN AND THE" in v.pedido.prompt for v in d.videos)
