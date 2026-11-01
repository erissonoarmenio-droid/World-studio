"""Casos reais de 31/10–01/11: o "Ó" depois do corte sumiu nos 3 vídeos (E33)."""

from app.geracao.conferencia import conferir_palavras


def test_sofa_problema_solucao():
    roteiro = [
        "Gente, senta aqui comigo. Sabe aquela camisa que gruda no calor?",
        "Essa aqui não. O tecido é fosco, com textura, né.",
        "Ó, é leve, fica fresquinho.",
        "Vem sentir, sério.",
    ]
    ouvido = (
        "Gente, senta aqui comigo. Sabe aquela camisa que gruda no calor? Essa aqui não. "
        "O tecido é fosco com textura, né? É leve, fica fresquinho. Vem sentir, sério."
    )
    c = conferir_palavras(roteiro, ouvido)
    assert c.faltando == ("o",)
    assert c.aprovado


def test_sofa_prova_pessoal_perde_o_comeco_do_plano():
    roteiro = [
        "Gente, olha... eu já separei uma pra mim.",
        "Ó, é esse tecido, tipo... fosco, com textura.",
        "E os bolsinhos, né? Eu amei o detalhe.",
        "Quer ver vestida? Me chama no direct.",
    ]
    ouvido = (
        "Gente, olha, eu já separei uma pra mim. Esse tecido tipo fosco com textura e os "
        "bolsinhos, né? Eu amei o detalhe. Quer ver vestida? Me chama no Direct."
    )
    c = conferir_palavras(roteiro, ouvido)
    assert c.faltando == ("o", "e")
    assert 0.9 < c.acerto < 1


def test_fala_trocada_reprova():
    c = conferir_palavras(["Essa camisa é de linho e não amassa"], "Essa calça é de seda")
    assert not c.aprovado
