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
                fala="Gente, olha isso... chegou hoje e eu já separei uma pra mim."
                if original
                else "Gente, olha isso, chegou hoje e eu já separei uma pra mim.",
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
                else "Isso aqui é linho, ó, bem leve,",
            ),
            Plano(
                inicio=8.4,
                fim=11.7,
                enquadramento="Slightly wider",
                acao="She steps half a step forward and pushes the shirt toward the lens, "
                "rubbing the fabric between two fingers, then lifts the pointed collar and lets "
                "it fall:"
                if original
                else "She steps half a step forward and holds the shirt toward the lens, then "
                "lifts the pointed collar with two fingers and lets it fall:",
                fala="...sente a textura. E não esquenta nada, sério."
                if original
                else "sente a textura, e não esquenta nada, sério.",
                depois='Small shrug with both shoulders on "sério", weight shifting to the '
                "other leg.",
            ),
            Plano(
                inicio=11.7,
                fim=16,
                enquadramento="Chest-up",
                acao="She tosses the hanger over her shoulder, leans slightly toward the lens "
                "with her head tilted and says, relaxed:",
                fala="Quer ver ela vestida? Me chama no direct."
                if original
                else "Quer ver ela vestida? Me chama no privado.",
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
    # e, desde 13/11, "direct" (E44), esfregar o tecido falando (E56) e reticências (E3)
    assert _ids(no.checar(pedido)) == {
        "ugc.fala_comeca_forte",
        "ugc.sem_palavra_estrangeira",
        "ugc.acao_barulhenta_fora_da_fala",
        "ugc.sem_reticencias",
    }


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


def _homem(**mudar):
    """O v3 com as ações de homem (sem balançar o quadril nem inclinar a cabeça)."""
    e = _v3(genero="homem", **mudar)
    planos = list(e.planos)
    planos[0] = planos[0].model_copy(
        update={"fala": "Chegou essa aqui, cara. Veste bem no ombro.", "depois": ""}
    )
    planos[1] = planos[1].model_copy(
        update={
            "acao": "He turns his body sideways to the camera and holds the shirt up "
            "against his torso, shifting his weight as he looks down at it:"
        }
    )
    planos[3] = planos[3].model_copy(
        update={
            "acao": "He tosses the hanger over his shoulder, leans slightly toward the "
            "lens and says, relaxed:",
            "depois": "A short laugh through the nose, then he turns away toward the rack.",
        }
    )
    return e.model_copy(update={"planos": planos})


def test_homem_com_fala_feminina_e_barrado():
    e = _homem()
    planos = list(e.planos)
    planos[0] = planos[0].model_copy(update={"fala": "Já separei uma pra mim, amei."})
    pedido = NoVideoUGC().montar_pedido(e.model_copy(update={"planos": planos}))
    assert "ugc.perfil_do_genero" in _ids(NoVideoUGC().checar(pedido))


def test_homem_com_gestos_femininos_e_barrado():
    pedido = NoVideoUGC().montar_pedido(_v3(genero="homem"))
    assert "ugc.perfil_do_genero" in _ids(NoVideoUGC().checar(pedido))


def test_homem_tem_perfil_de_atuacao_e_voz_masculinos():
    pedido, relatorio = NoVideoUGC().preparar(_homem())
    assert relatorio.falhas == []
    assert "VOICE — a Brazilian man" in pedido.prompt
    assert "like showing something to a buddy" in pedido.prompt
    assert "tucks hair" not in pedido.prompt and "lightly amused" not in pedido.prompt
    mulher = NoVideoUGC().preparar(_v3())[0].prompt
    assert "VOICE — a Brazilian man" not in mulher and "tucks hair" in mulher


def test_homem_troca_pronomes_e_mantem_falas():
    import re

    mulher = NoVideoUGC().preparar(_v3())[0].prompt
    pedido, relatorio = NoVideoUGC().preparar(_homem())
    assert relatorio.falhas == []
    assert not re.search(r"\b(she|her|herself|woman|women)\b", pedido.prompt, re.I)
    assert "THE MAN AND THE" in pedido.prompt
    falas_m = [p.fala for p in _homem().planos]
    assert all(f in pedido.prompt for f in falas_m if f)  # português intacto
    assert mulher != pedido.prompt


def test_som_voz_por_cima_e_acao_barulhenta_fora_da_fala():
    """E56 (13/11): o prompt manda a voz por cima; barulho em cima da fala vira aviso."""
    pedido, relatorio = NoVideoUGC().preparar(_v3())
    assert "SOUND MIX" in pedido.prompt and "never louder than her voice" in pedido.prompt
    assert "SFX —" not in pedido.prompt and relatorio.falhas == []
    planos = list(_v3().planos)
    planos[1] = planos[1].model_copy(
        update={"acao": "She sits down on the armchair, rubbing the fabric, and says:"}
    )
    _, relatorio = NoVideoUGC().preparar(_v3(planos=planos))
    assert _ids(relatorio) == {"ugc.acao_barulhenta_fora_da_fala"}


def test_direct_bloqueia_e_reticencias_avisam():
    planos = list(_v3().planos)
    planos[3] = planos[3].model_copy(update={"fala": "Quer ver? Me chama no direct."})
    with pytest.raises(PedidoBloqueado) as erro:
        NoVideoUGC().preparar(_v3(planos=planos))
    assert "ugc.sem_palavra_estrangeira" in _ids(erro.value.relatorio)
    planos[3] = planos[3].model_copy(update={"fala": "Quer ver... me chama no privado."})
    _, relatorio = NoVideoUGC().preparar(_v3(planos=planos))
    assert _ids(relatorio) == {"ugc.sem_reticencias"}


def test_outra_peca_nao_vira_camisa_no_prompt():
    """Vestido ou calça: os blocos fixos não podem falar de 'the shirt'."""
    planos = [p.model_copy(update={"acao": p.acao.replace("shirt", "dress")}) for p in _v3().planos]
    pedido, relatorio = NoVideoUGC().preparar(
        _v3(
            planos=planos,
            peca_nome="dress",
            peca="black midi dress (thin straps, square neckline, matte crepe, side slit)",
            peca_nunca="colour, straps, neckline or length",
            contexto="a young woman shows a dress that just arrived to a friend filming her. "
            "It must feel like a real, slightly messy story, not a fashion commercial.",
        )
    )
    assert "shirt" not in pedido.prompt and "between the dress, the lens" in pedido.prompt
    assert relatorio.falhas == []
