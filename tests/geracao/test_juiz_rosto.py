"""Juiz de rosto (07/11): pega rosto afinando (E39) e cabeça inflando (E40)."""

from app.geracao.nos.juiz_rosto import pedido_rosto, veredito_rosto

BOM = {
    "reconheceria": 9,
    "largura_rosto": "igual",
    "comprimento_rosto": "igual",
    "cabeca_vs_corpo": "igual",
    "tom_pele": "igual",
    "olhos": "igual",
    "nariz": "igual",
    "boca": "igual",
    "cabelo": "igual",
    "idade_ref": 26,
    "idade_foto": 27,
    "diferencas": [],
}


def test_rosto_igual_passa():
    v = veredito_rosto(BOM)
    assert v.aprovado and v.notas["reconheceria"] == 9


def test_rosto_fino_e_cabeca_grande_reprovam():
    v = veredito_rosto({**BOM, "largura_rosto": "mais_fino", "cabeca_vs_corpo": "maior"})
    assert not v.aprovado
    assert "rosto: mais fino" in v.motivos and "cabeça: maior" in v.motivos


def test_nota_baixa_pele_e_idade_reprovam():
    v = veredito_rosto({**BOM, "reconheceria": 6, "tom_pele": "mais_oliva", "idade_foto": 34})
    assert not v.aprovado and len(v.motivos) == 3


def test_pedido_direto_rapido_com_as_reais_antes():
    p = pedido_rosto(
        [("image/jpeg", "cmVhbDE="), ("image/jpeg", "cmVhbDI=")], ("image/png", "Zm90bw==")
    )
    partes = p.payload["contents"][0]["parts"]
    assert "Images 1 to 2 are real photos" in partes[0]["text"]
    assert partes[-1]["inlineData"]["data"] == "Zm90bw=="
    assert p.payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
