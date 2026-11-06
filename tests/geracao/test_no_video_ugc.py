"""Nó vídeo UGC (Método W-orld v3). Caso de ouro: o v3 "corpo vivo" aprovado por Eri em 01/11."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.geracao.nos.base import PedidoBloqueado
from app.geracao.nos.video_ugc import EntradaUGC, NoVideoUGC, Plano

CASOS = Path(__file__).parent / "casos"
IMG = "https://exemplo/q4_1.jpg"
AUD = "https://exemplo/trilha.mp3"


def _v3(original: bool = False, **mudar) -> EntradaUGC:
    dados = dict(
        duracao=16,
        peca_nome="shirt",
        peca="light orange linen shirt (short sleeves, pointed collar, tone-on-tone buttons, "
        "matte linen, no pocket)",
        peca_nunca="colour, collar, buttons or fabric; no pocket appears",
        imagem_url=IMG,
        audio_url=AUD,
        planos=[
            Plano(
                inicio=0,
                fim=5,
                acao="Starts mid-movement: she walks two steps toward the camera from the "
                "clothing rack, holding the shirt on its wooden hanger, already turning to the "
                "lens. She takes a small breath, laughs softly through her nose and says:",
                fala="Gente, olha isso... chegou hoje e eu já separei uma pra mim.",
                depois='Eyebrows lift on "separei"; her free hand points at herself on "pra mim".',
            ),
            Plano(
                inicio=5,
                fim=8.4,
                enquadramento="Slightly closer",
                acao="She turns her body sideways to the camera and holds the shirt up against "
                "her torso, swaying her hips a little as she looks down at it:",
                fala="Ó, isso aqui é linho, tipo..."
                if original
                else "Isso aqui é linho, ó, tipo...",
            ),
            Plano(
                inicio=8.4,
                fim=11.7,
                enquadramento="Slightly wider",
                acao="She steps half a step forward and pushes the shirt toward the lens, "
                "rubbing the fabric between two fingers, then lifts the pointed collar and lets "
                "it fall:",
                fala="...sente a textura. E não esquenta nada, sério.",
                depois='Small shrug with both shoulders on "sério", weight shifting to the '
                "other leg.",
            ),
            Plano(
                inicio=11.7,
                fim=16,
                enquadramento="Chest-up",
                acao="She tosses the hanger over her shoulder, leans slightly toward the lens "
                "with her head tilted and says, relaxed:",
                fala="Quer ver ela vestida? Me chama no direct.",
                depois="A short light chuckle, then she starts to turn away toward the rack "
                "with a lopsided smile and a glance back.",
            ),
        ],
    )
    dados.update(mudar)
    return EntradaUGC(**dados)


def _ids(relatorio) -> set[str]:
    return {f.regra_id for f in relatorio.falhas}


def test_caso_de_ouro_reproduz_o_v3_aprovado():
    no = NoVideoUGC()
    pedido = no.montar_pedido(_v3(original=True))
    esperado = (CASOS / "prompt_v3.txt").read_text(encoding="utf-8").strip()
    assert pedido.prompt == esperado
    # o v3 tinha "Ó, isso aqui..." depois do corte: o "Ó" sumiu (E33) — hoje a regra barra
    assert _ids(no.checar(pedido)) == {"ugc.fala_comeca_forte"}


def test_v3_com_a_fala_corrigida_passa_limpo():
    _, relatorio = NoVideoUGC().preparar(_v3())
    assert relatorio.falhas == []


def test_palavra_curta_depois_do_corte_bloqueia():
    planos = list(_v3().planos)
    planos[2] = planos[2].model_copy(update={"fala": "É leve, fica fresquinho."})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.fala_comeca_forte" in _ids(erro.value.relatorio)


def test_payload_tein_e_custo():
    pedido, _ = NoVideoUGC().preparar(_v3())
    assert pedido.payload["model"] == "seedance-2-5"
    assert pedido.payload["reference_image"] == [IMG]
    assert pedido.payload["reference_audio"] == [AUD]
    assert pedido.custo_estimado == Decimal("0.1279") * 16
    pedido720, _ = NoVideoUGC().preparar(_v3(resolucao="720p"))
    assert pedido720.custo_estimado == Decimal("0.2885") * 16


def test_sem_trilha_nao_cita_audio():
    pedido, relatorio = NoVideoUGC().preparar(_v3(audio_url=None))
    assert "@audio1" not in pedido.prompt
    assert "exactly as written" in pedido.prompt
    assert "ugc.voz_ref_coerente" not in _ids(relatorio)


def test_plano_sem_acao_de_corpo_bloqueia():
    planos = list(_v3().planos)
    planos[1] = planos[1].model_copy(update={"acao": "She smiles and looks at the fabric:"})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.corpo_vivo" in _ids(erro.value.relatorio)


def test_trava_de_corpo_do_v2_bloqueia():
    planos = list(_v3().planos)
    planos[0] = planos[0].model_copy(
        update={"depois": "Gestures are compact, no constant hand movement."}
    )
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.sem_trava_de_corpo" in _ids(erro.value.relatorio)


def test_buraco_no_tempo_bloqueia():
    planos = list(_v3().planos)
    planos[2] = planos[2].model_copy(update={"inicio": 9.0})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.tempos_contiguos" in _ids(erro.value.relatorio)


def test_propaganda_bloqueia():
    planos = list(_v3().planos)
    planos[3] = planos[3].model_copy(update={"fala": "Gente, é imperdível, corre que acaba."})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.sem_propaganda" in _ids(erro.value.relatorio)


def test_close_extremo_bloqueia():
    planos = list(_v3().planos)
    planos[3] = planos[3].model_copy(update={"enquadramento": "Extreme close-up"})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.sem_close_extremo" in _ids(erro.value.relatorio)


def test_sem_primeiro_quadro_bloqueia():
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(imagem_url=None))
    assert "ugc.primeiro_quadro" in _ids(erro.value.relatorio)


def test_fala_longa_demais_so_avisa():
    planos = list(_v3().planos)
    longa = "Gente olha " + " ".join(["palavra"] * 40)
    planos[0] = planos[0].model_copy(update={"fala": longa, "depois": ""})
    _, relatorio = NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.palavras_cabem" in _ids(relatorio)
    assert not relatorio.bloqueado


def test_dois_planos_bloqueia_cortes():
    planos = [
        _v3().planos[0],
        _v3().planos[3].model_copy(update={"inicio": 5.0}),
    ]
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.cortes" in _ids(erro.value.relatorio)


def test_fala_com_aspas_recusada():
    with pytest.raises(ValueError):
        Plano(inicio=0, fim=4, acao="She walks to the rack and says:", fala='ela disse "oi"')


def test_homem_troca_pronomes_e_mantem_falas():
    import re

    mulher = NoVideoUGC().preparar(_v3())[0].prompt
    pedido, relatorio = NoVideoUGC().preparar(_v3(genero="homem"))
    assert relatorio.falhas == []
    assert not re.search(r"\b(she|her|herself|woman|women)\b", pedido.prompt, re.I)
    assert "THE MAN AND THE" in pedido.prompt
    falas_m = [p.fala for p in _v3().planos]
    assert all(f in pedido.prompt for f in falas_m if f)  # português intacto
    assert mulher != pedido.prompt
