import json
from pathlib import Path

import pytest

from app.geracao.nos.base import checar_regras
from app.geracao.nos.juiz import (
    PROMPT_VIDEO,
    REGRAS,
    ler_json,
    pedido_foto,
    pedido_transcricao,
    pedido_video,
    veredito_foto,
    veredito_video,
)

J = json.loads((Path(__file__).parent / "casos" / "juiz_2910.json").read_text())
FOTO = {r["foto"]: r for r in J["foto"]}
VIDEO = {r["clip"][2:4]: r for r in J["video"]}


@pytest.mark.parametrize("f", ["c1.png", "c2.png", "c3.png", "c4.png", "c5.png"])
def test_fotos_do_google_de_2910_passam(f):
    assert veredito_foto(FOTO[f]).aprovado, veredito_foto(FOTO[f]).motivos


def test_foto_2_da_atlas_com_6_dedos_reprova():
    v = veredito_foto(FOTO["atlas_c2.jpg"])
    assert not v.aprovado
    assert any("6 dedos" in m for m in v.motivos)
    assert any("mesma pessoa" in m for m in v.motivos)


@pytest.mark.parametrize("f", ["atlas_c3.jpg", "atlas_c4.jpg"])
def test_fotos_da_atlas_com_rosto_ou_idade_diferente_reprovam(f):
    assert not veredito_foto(FOTO[f]).aprovado


@pytest.mark.parametrize("c", ["c1", "c3"])
def test_clipes_v1_reprovam_pela_fala(c):
    r = VIDEO[c]
    v = veredito_video(r, J["falas_esperadas_video"][c], r["transcricao"])
    assert not v.aprovado and any("palavras" in m for m in v.motivos)


def test_clipe_sem_transcricao_do_audio_nao_aprova():
    # c2 de 29/10: o juiz de vídeo deu 1,0, mas a transcrição só do áudio mostrou fala trocada
    v = veredito_video(VIDEO["c2"], J["falas_esperadas_video"]["c2"], None)
    assert not v.aprovado and "transcrição só do áudio" in v.motivos[0]


def test_clipe_certo_aprova():
    fala = "As mãos, que a IA sempre errava, cinco dedinhos, ó."
    assert veredito_video(VIDEO["c2"], fala, fala).aprovado


def test_pedidos_do_juiz_passam_nas_regras_e_juiz_de_video_nao_recebe_a_fala():
    ref = ("image/jpeg", "aaaa")
    for p in (
        pedido_foto(ref, ("image/png", "bbbb")),
        pedido_video(ref, "cccc"),
        pedido_transcricao("dddd"),
    ):
        assert not checar_regras("juiz", REGRAS, p).bloqueado
    assert "Fala esperada" not in PROMPT_VIDEO


def test_ler_json_da_resposta():
    assert ler_json([{"text": '{"mesma_pessoa": 7}'}]) == {"mesma_pessoa": 7}
    with pytest.raises(ValueError):
        ler_json([{"inlineData": {}}])
