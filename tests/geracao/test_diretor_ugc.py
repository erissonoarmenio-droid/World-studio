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
             "sideways and holds the shirt against her torso:", "fala": "Ó, linho, tipo."},
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
