"""Nó juiz: confere foto, voz e vídeo depois de gerar (Gemini), com os limites da spec.

O pedido ao Gemini usa os prompts dos juízes de 29/10 (juiz_foto.py, juiz_video.py,
transcrever.py). O veredito é calculado por código a partir da resposta JSON — o modelo dá
as notas, quem aprova é a regra. Regra 7: juiz tem variação; decisão de método pede ≥ 2
repetições.

Limites:
- foto: mesma pessoa ≥ 6, idade ±3, mãos ok, sem texto/logo, espelho coerente;
- vídeo: palavras ≥ 90% pela transcrição SÓ do áudio (o juiz de vídeo "ouve" a fala
  esperada e erra — c2 de 29/10), peça igual, mãos ok, sem música, sem texto, sem celular.
- voz: ver voz.conferir_voz.
"""

from __future__ import annotations

import difflib
import json
from decimal import Decimal
from typing import Any

from app.geracao.nos.base import Pedido, Regra, Veredito
from app.geracao.nos.regras import registrar
from app.geracao.nos.voz import LIMITE_PALAVRAS, palavras_de

MODELO = "gemini-3.8-flash"
CUSTO = Decimal("0.003")  # estimado por conferência (foto ou clipe curto)

PROMPT_FOTO = (
    "Imagem 1 = referência da pessoa. Imagem 2 = foto gerada para um vídeo UGC de loja. "
    'Seja rigoroso e não suponha nada. Responda SÓ JSON: {"mesma_pessoa": 0-10, '
    '"idade_ref": n, "idade_foto": n, "maos_ok": true/false, "dedos_contados": "...", '
    '"espelho_reflexo_ok": true/false/null, "texto_ou_logo": true/false, '
    '"parece_foto_real": 0-10, "defeitos": ["..."]}'
)
PROMPT_VIDEO = (
    "Imagem 1 = referência da pessoa. O vídeo é um clipe UGC de loja gerado por IA. Assista "
    'com atenção, quadro a quadro, e seja rigoroso. Responda SÓ JSON: {"sincronia_boca": '
    '0-10, "mesma_pessoa_do_inicio_ao_fim": 0-10, "parecida_com_referencia": 0-10, '
    '"idade_aparente": n, "maos_ok": true/false, "camisa_igual_o_tempo_todo": '
    'true/false, "espelho_ok": true/false/null, "texto_ou_logo": true/false, '
    '"celular_visivel_indevido": true/false, "musica": true/false, '
    '"parece_video_real": 0-10, "defeitos": ["segundo X: ..."]}'
)
# A fala esperada NÃO vai para o juiz de vídeo: com ela, ele "ouviu" a fala certa no c2.
PROMPT_TRANSCRICAO = (
    "Transcreva EXATAMENTE o que é falado, palavra por palavra, sem corrigir. Só a transcrição."
)

REGRAS = registrar(
    "juiz",
    [
        Regra(
            id="juiz.sem_fala_esperada_no_video",
            nivel="bloqueia",
            faca="NÃO mandar a fala esperada para o juiz de vídeo; as palavras saem da "
            "transcrição só do áudio.",
            origem="29/10 (c2: juiz com a fala esperada deu 1,0; só o áudio mostrou fala trocada)",
            checar=lambda p: p.no != "juiz.video" or "Fala esperada" not in p.prompt,
        ),
        Regra(
            id="juiz.resposta_em_json",
            nivel="bloqueia",
            faca="Pedir resposta em JSON (responseMimeType) para o veredito sair por código.",
            origem="juízes de 29/10",
            checar=lambda p: (
                p.no == "juiz.transcricao"
                or p.payload.get("generationConfig", {}).get("responseMimeType")
                == "application/json"
            ),
        ),
    ],
)


def _parte(mime: str, dados_b64: str) -> dict:
    return {"inlineData": {"mimeType": mime, "data": dados_b64}}


def _pedido(no: str, prompt: str, midias: list[dict], json_: bool = True) -> Pedido:
    payload: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}, *midias]}]}
    if json_:
        payload["generationConfig"] = {"responseMimeType": "application/json"}
    return Pedido(
        no=no,
        fornecedor="google",
        modelo=MODELO,
        entrada=None,
        prompt=prompt,
        payload=payload,
        custo_estimado=CUSTO,
    )


def pedido_foto(ref: tuple[str, str], foto: tuple[str, str]) -> Pedido:
    """ref/foto = (mime, base64)."""
    return _pedido("juiz.foto", PROMPT_FOTO, [_parte(*ref), _parte(*foto)])


def pedido_video(ref: tuple[str, str], clipe_b64: str) -> Pedido:
    return _pedido("juiz.video", PROMPT_VIDEO, [_parte(*ref), _parte("video/mp4", clipe_b64)])


def pedido_transcricao(audio_b64: str, mime: str = "audio/wav") -> Pedido:
    return _pedido("juiz.transcricao", PROMPT_TRANSCRICAO, [_parte(mime, audio_b64)], False)


def ler_json(saidas: list[Any]) -> dict:
    """Pega o JSON da primeira parte de texto da resposta do Gemini."""
    for parte in saidas:
        if isinstance(parte, dict) and "text" in parte:
            return json.loads(parte["text"])
    raise ValueError("resposta do juiz sem texto")


def veredito_foto(r: dict) -> Veredito:
    motivos = []
    if (r.get("mesma_pessoa") or 0) < 6:
        motivos.append(f"mesma pessoa {r.get('mesma_pessoa')} < 6")
    if r.get("idade_foto") is None or r.get("idade_ref") is None:
        motivos.append("juiz não estimou a idade")
    elif abs(r["idade_foto"] - r["idade_ref"]) > 3:
        motivos.append(f"idade {r['idade_foto']} × referência {r['idade_ref']} (> ±3)")
    if r.get("maos_ok") is not True:
        motivos.append(f"mãos: {r.get('dedos_contados', 'não ok')}")
    if r.get("texto_ou_logo") is not False:
        motivos.append("texto ou logo na foto")
    if r.get("espelho_reflexo_ok") is False:
        motivos.append("reflexo do espelho incoerente")
    return Veredito(
        not motivos,
        tuple(motivos),
        {"real": r.get("parece_foto_real"), "defeitos": r.get("defeitos", [])},
    )


def veredito_video(r: dict, fala: str, transcricao_audio: str | None) -> Veredito:
    motivos = []
    if transcricao_audio is None:
        motivos.append("falta a transcrição só do áudio (não confiar no juiz de vídeo)")
        palavras = None
    else:
        palavras = difflib.SequenceMatcher(
            None, palavras_de(fala), palavras_de(transcricao_audio)
        ).ratio()
        if palavras < LIMITE_PALAVRAS:
            motivos.append(f"palavras {palavras:.0%} < 90% (fala trocada)")
    if r.get("camisa_igual_o_tempo_todo") is not True:
        motivos.append("peça mudou durante o clipe")
    if r.get("maos_ok") is not True:
        motivos.append("mãos com defeito")
    if r.get("musica") is not False:
        motivos.append("tem música")
    if r.get("texto_ou_logo") is not False:
        motivos.append("texto ou logo no vídeo")
    if r.get("celular_visivel_indevido") is True:
        motivos.append("celular aparecendo")
    if r.get("espelho_ok") is False:
        motivos.append("espelho incoerente")
    notas = {
        "palavras": None if palavras is None else round(palavras, 2),
        "boca": r.get("sincronia_boca"),
        "real": r.get("parece_video_real"),
        "defeitos": r.get("defeitos", []),
    }
    return Veredito(not motivos, tuple(motivos), notas)
