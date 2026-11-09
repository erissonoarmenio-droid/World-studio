"""Loja de teste do Eri pelo @DesfilaBot (06/11), enquanto o bot de verdade não está no ar.

Rodar no Shell do Render (a chave do bot vem do ambiente; nada é impresso):

    python -m app.ferramentas.telegram_teste listar
    python -m app.ferramentas.telegram_teste importar --de <telegram_id>
    python -m app.ferramentas.telegram_teste influencer --idade 27 --fotos 1,2,3 [--oculos "..."]
    python -m app.ferramentas.telegram_teste situacao <chave_unica>
    python -m app.ferramentas.telegram_teste devolver --para <telegram_id> <midia_id> ...

- `listar` só lê: mostra o que está esperando no bot (quem mandou, tipo), sem baixar nada.
- `importar` aceita só mensagens de quem foi passado em --de; cria (uma vez) a loja "Teste Eri"
  com o Eri como dona, os aceites de termos e de clone (rosto e voz dele, autorizados no chat de
  05/11) e o plano estúdio liberado na mão; guarda fotos e áudios no R2 e marca as mensagens como
  lidas no Telegram.
- `influencer` cria o pedido (reserva créditos e entra na fila). É o passo que GASTA: o
  trabalhador do servidor pega e gera.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from app.nucleo.db import sessao
from app.nucleo.eventos import ERI, Autor

NOME_LOJA = "Teste Eri"
VERSAO_ACEITE = "teste-0611"
REFERENCIA_PLANO = "manual-teste-eri-0611-loja-{}"
TIPOS_IMAGEM = ("image/jpeg", "image/png", "image/webp")

Chamar = Callable[[str, dict[str, Any] | None], Any]
Baixar = Callable[[str], bytes]


def _token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN não está no ambiente")
    return token


def chamar_api(metodo: str, params: dict[str, Any] | None = None) -> Any:
    corpo = json.dumps(params or {}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{_token()}/{metodo}",
        data=corpo,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (sempre https da API)
        dados = json.loads(r.read())
    if not dados.get("ok"):
        raise RuntimeError(f"Telegram recusou {metodo}: {dados.get('description')}")
    return dados["result"]


def baixar_arquivo(caminho: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{_token()}/{caminho}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def arquivo_da_mensagem(msg: dict[str, Any]) -> tuple[str, str, str] | None:
    """(file_id, content_type, tipo de mídia) ou None se não for foto/áudio aceito."""
    if msg.get("photo"):
        return msg["photo"][-1]["file_id"], "image/jpeg", "influencer"
    doc = msg.get("document")
    if doc and doc.get("mime_type") in TIPOS_IMAGEM:
        return doc["file_id"], doc["mime_type"], "influencer"
    if msg.get("voice"):
        return msg["voice"]["file_id"], "audio/ogg", "voz"
    audio = msg.get("audio") or (
        doc if doc and str(doc.get("mime_type", "")).startswith("audio/") else None
    )
    if audio:
        mime = audio.get("mime_type", "audio/mpeg")
        if mime in ("audio/x-m4a", "audio/m4a"):
            mime = "audio/mp4"
        return audio["file_id"], mime, "voz"
    return None


def _mensagens(chamar: Chamar) -> list[dict[str, Any]]:
    return chamar("getUpdates", {"timeout": 0, "allowed_updates": ["message"]})


def listar(chamar: Chamar = chamar_api) -> list[str]:
    linhas = []
    for u in _mensagens(chamar):
        msg = u.get("message") or {}
        de = msg.get("from") or {}
        arq = arquivo_da_mensagem(msg)
        tipo = arq[1] if arq else ("texto" if msg.get("text") else "outro")
        linhas.append(f"update {u['update_id']}: de {de.get('id')} ({de.get('first_name')}) {tipo}")
    return linhas or ["nada esperando no bot"]


def garantir_loja(s: Any, telegram_id: int, nome: str = "Eri") -> tuple[int, int, bool]:
    """(loja_id, pessoa_id, criou_agora). Idempotente."""
    from app.creditos import servico as creditos
    from app.nucleo.consentimentos import registrar_aceite
    from app.nucleo.lojas import criar_loja_com_dona
    from app.nucleo.pessoas import obter_pessoa_por_telegram

    pessoa = obter_pessoa_por_telegram(s, telegram_id)
    criou = pessoa is None
    if pessoa is None:
        _, pessoa = criar_loja_com_dona(
            s,
            {"nome": NOME_LOJA, "segmento": "teste"},
            {"nome": nome, "telegram_id": telegram_id},
            ERI,
        )
    eu = Autor("pessoa", pessoa.id)
    registrar_aceite(s, pessoa.id, "termos_privacidade", VERSAO_ACEITE, eu)
    registrar_aceite(
        s,
        pessoa.id,
        "clone",
        VERSAO_ACEITE,
        eu,
        {"rosto": True, "voz": True, "origem": "Eri autorizou no chat em 05/11/2026"},
    )
    if creditos.obter_assinatura(s, pessoa.loja_id) is None:
        creditos.ativar_plano(
            s, pessoa.loja_id, "estudio", REFERENCIA_PLANO.format(pessoa.loja_id), autor=ERI
        )
    return pessoa.loja_id, pessoa.id, criou


def importar(
    de: int, chamar: Chamar = chamar_api, baixar: Baixar = baixar_arquivo
) -> dict[str, Any]:
    from app.nucleo import midia

    updates = _mensagens(chamar)
    guardadas: list[tuple[int, str, str]] = []
    ignoradas = 0
    with sessao() as s:
        loja_id, pessoa_id, criou = garantir_loja(s, de)
        autor = Autor("pessoa", pessoa_id)
        for u in updates:
            msg = u.get("message") or {}
            arq = arquivo_da_mensagem(msg) if (msg.get("from") or {}).get("id") == de else None
            if arq is None:
                ignoradas += 1
                continue
            file_id, content_type, tipo = arq
            caminho = chamar("getFile", {"file_id": file_id})["file_path"]
            m = midia.enviar(
                s,
                loja_id=loja_id,
                conteudo=baixar(caminho),
                tipo=tipo,
                content_type=content_type,
                origem="telegram",
                autor=autor,
            )
            guardadas.append((m.id, tipo, msg.get("caption") or ""))
    if updates:  # só depois de tudo gravado: marca como lido
        chamar("getUpdates", {"offset": updates[-1]["update_id"] + 1, "timeout": 0})
    return {
        "loja_id": loja_id,
        "pessoa_id": pessoa_id,
        "loja_criada_agora": criou,
        "midias": guardadas,
        "ignoradas": ignoradas,
    }


def pedir_influencer(
    telegram_id: int,
    fotos: list[int],
    idade: int,
    oculos: str | None,
    roupa: str,
    chave: str | None = None,
    aparencia: str = "",
    corpo_midia: int | None = None,
    close: bool = False,
    corpo: str = "same build and proportions as in the reference photos",
    pessoa_id: int | None = None,
    genero: str = "homem",
) -> dict[str, Any]:
    from app.pedidos import criar_pedido

    if not 2 <= len(fotos) <= 6:
        raise SystemExit("mande de 2 a 6 fotos do rosto")
    with sessao() as s:
        pessoa = _dona_do_rosto(s, telegram_id, pessoa_id)
        dados: dict[str, Any] = {
            "modo": "da_pessoa",
            "pessoa_id": pessoa.id,
            "fotos_midia_ids": fotos,
            "genero": genero,
            "idade": idade,
            "corpo": corpo,
            "roupa": roupa,
            "aparencia": aparencia,
            "enquadramento": "close" if close else "corpo",
        }
        if corpo_midia:
            dados["corpo_midia_id"] = corpo_midia
        if oculos:
            dados["oculos"] = oculos
        situacao, criado = criar_pedido(
            s,
            loja_id=pessoa.loja_id,
            item="influencer_principal",
            dados=dados,
            chave_unica=chave or f"teste-eri-influencer-{uuid.uuid4().hex[:8]}",
            autor=Autor("pessoa", pessoa.id),
        )
        return {"chave": situacao.chave_unica, "criado_agora": criado, "estado": situacao.estado}


def pedir_foto(
    telegram_id: int,
    influencer_midia: int,
    peca_midias: list[int],
    entrada: dict[str, Any],
    opcoes: int = 2,
    chave: str | None = None,
    rostos: list[int] | None = None,
    oculos: str = "",
    pessoa_id: int | None = None,
) -> dict[str, Any]:
    """Foto da influencer vestindo a peça (item "foto", 2 opções). É o passo que GASTA.
    Com `rostos` (fotos reais), cada opção passa pela trava do rosto (nó rosto_fixo)."""
    from app.pedidos import criar_pedido

    with sessao() as s:
        pessoa = _dona_do_rosto(s, telegram_id, pessoa_id)
        situacao, criado = criar_pedido(
            s,
            loja_id=pessoa.loja_id,
            item="foto",
            dados={
                "entrada": entrada,
                "influencer_midia_id": influencer_midia,
                "peca_midia_ids": peca_midias,
                "opcoes": opcoes,
                "rostos_reais_midia_ids": rostos or [],
                "pessoa_id": pessoa.id,
                "oculos": oculos,
            },
            chave_unica=chave or f"teste-eri-foto-{uuid.uuid4().hex[:8]}",
            autor=Autor("pessoa", pessoa.id),
        )
        return {"chave": situacao.chave_unica, "criado_agora": criado, "estado": situacao.estado}


def provador(
    telegram_id: int,
    foto_real: int,
    peca_midias: list[int],
    peca: str,
    cenario: str,
    reais: list[int],
    opcoes: int = 2,
    pessoa_id: int | None = None,
    genero: str = "homem",
) -> dict[str, Any]:
    """Veste a peça na FOTO REAL (nó provador, E43) e mede o rosto. GASTA (US$ 0,04/opção)."""
    from app.pedidos import criar_pedido

    with sessao() as s:
        pessoa = _dona_do_rosto(s, telegram_id, pessoa_id)
        situacao, criado = criar_pedido(
            s,
            loja_id=pessoa.loja_id,
            item="foto",
            dados={
                "modo": "provador",
                "foto_real_midia_id": foto_real,
                "peca_midia_ids": peca_midias,
                "peca": peca,
                "cenario": cenario,
                "genero": genero,
                "opcoes": opcoes,
                "rostos_reais_midia_ids": reais,
                "pessoa_id": pessoa.id,
            },
            chave_unica=f"teste-eri-provador-{uuid.uuid4().hex[:8]}",
            autor=Autor("pessoa", pessoa.id),
        )
        return {"chave": situacao.chave_unica, "criado_agora": criado, "estado": situacao.estado}


def dirigir(
    de: int,
    quadro: int,
    pedido: str,
    peca: str,
    genero: str = "homem",
    cerebro: Any = None,
) -> dict[str, Any]:
    """Diretor UGC: escreve os 2 roteiros (ângulos) olhando o 1º quadro. Custa centavos de
    Claude; NÃO gera vídeo. Devolve as falas (para aprovar) e as entradas prontas do nó."""
    from app.config import obter_config
    from app.geracao.diretor_ugc import DiretorUGC
    from app.geracao.fornecedores.claude import ClienteClaude

    if cerebro is None:
        chave = obter_config().anthropic_api_key
        if chave is None:
            raise SystemExit("ANTHROPIC_API_KEY não configurada no servidor")
        cerebro = ClienteClaude(chave)
    ((_, foto),) = _ler_midias(de, [quadro])
    tipo = "image/png" if foto[:4] == b"\x89PNG" else "image/jpeg"
    direcao = DiretorUGC(cerebro).dirigir(
        pedido,
        peca,
        imagem_url=f"https://midia.interna/{quadro}",  # o executor troca pelo link da Tein
        foto_local=(foto, tipo),
        genero=genero,
    )
    videos = []
    for v in direcao.videos:
        e = v.pedido.entrada
        videos.append(
            {
                "angulo": v.angulo,
                "falas": [
                    {"de": p.inicio, "ate": p.fim, "fala": p.fala, "acao": p.acao} for p in e.planos
                ],
                "entrada": e.model_dump(mode="json", exclude={"imagem_url", "resolucao"}),
            }
        )
    return {
        "mensagem": direcao.mensagem_para_lojista,
        "tentativas": direcao.tentativas,
        "videos": videos,
    }


def gerar_video(
    de: int, quadro: int, entrada: dict[str, Any], pessoa_id: int | None = None
) -> dict[str, Any]:
    """Vídeo 480p (item video_480) com o roteiro já aprovado. GASTA (≈ US$ 2,15 na Tein)."""
    from app.pedidos import criar_pedido

    with sessao() as s:
        pessoa = _dona_do_rosto(s, de, pessoa_id)
        situacao, criado = criar_pedido(
            s,
            loja_id=pessoa.loja_id,
            item="video_480",
            dados={
                "entradas": [entrada],
                "primeiro_quadro_midia_id": quadro,
                "pessoa_id": pessoa.id,
            },
            chave_unica=f"teste-eri-video-{uuid.uuid4().hex[:8]}",
            autor=Autor("pessoa", pessoa.id),
        )
        return {"chave": situacao.chave_unica, "criado_agora": criado, "estado": situacao.estado}


def travar_rosto(
    telegram_id: int,
    base: int,
    rostos: list[int],
    tracos: str,
    oculos: str = "",
    pessoa_id: int | None = None,
    genero: str = "mulher",
) -> dict[str, Any]:
    """Trava o rosto de uma foto já gerada (item ajuste_rosto, modo rosto_fixo). GASTA."""
    from app.pedidos import criar_pedido

    with sessao() as s:
        pessoa = _dona_do_rosto(s, telegram_id, pessoa_id)
        situacao, criado = criar_pedido(
            s,
            loja_id=pessoa.loja_id,
            item="ajuste_rosto",
            dados={
                "modo": "rosto_fixo",
                "base_midia_id": base,
                "rostos_reais_midia_ids": rostos,
                "tracos": tracos,
                "oculos": oculos,
                "pessoa_id": pessoa.id,
                "genero": genero,
            },
            chave_unica=f"teste-eri-rosto-{uuid.uuid4().hex[:8]}",
            autor=Autor("pessoa", pessoa.id),
        )
        return {"chave": situacao.chave_unica, "criado_agora": criado, "estado": situacao.estado}


def nova_pessoa(telegram_id: int, nome: str, origem: str) -> dict[str, Any]:
    """Outra pessoa real na loja de teste (07/11: a mulher do teste), com os aceites de clone
    (rosto e voz) registrados em nome dela, com a origem da autorização."""
    from app.nucleo.consentimentos import registrar_aceite
    from app.nucleo.pessoas import adicionar_pessoa, obter_pessoa_por_telegram

    with sessao() as s:
        eri = obter_pessoa_por_telegram(s, telegram_id)
        if eri is None:
            raise SystemExit("rode o importar primeiro")
        p = adicionar_pessoa(s, eri.loja_id, {"nome": nome, "papel": "socia"}, ERI)
        ela = Autor("pessoa", p.id)
        registrar_aceite(
            s, p.id, "clone", VERSAO_ACEITE, ela, {"rosto": True, "voz": True, "origem": origem}
        )
        return {"pessoa_id": p.id, "loja_id": eri.loja_id}


def _dona_do_rosto(s: Any, telegram_id: int, pessoa_id: int | None) -> Any:
    from app.nucleo.pessoas import obter_pessoa, obter_pessoa_por_telegram

    eri = obter_pessoa_por_telegram(s, telegram_id)
    if eri is None:
        raise SystemExit("rode o importar primeiro")
    if pessoa_id is None:
        return eri
    p = obter_pessoa(s, pessoa_id)
    if p.loja_id != eri.loja_id:
        raise SystemExit("essa pessoa não é da loja de teste")
    return p


def situacao(chave: str) -> dict[str, Any]:
    from sqlalchemy import select

    from app.nucleo.modelos.fila import Trabalho

    with sessao() as s:
        t = s.scalar(select(Trabalho).where(Trabalho.chave_unica == chave))
        if t is None:
            return {"erro": "pedido não encontrado"}
        return {
            "estado": t.estado,
            "tentativas": t.tentativas,
            "custo_estimado": str(t.custo_estimado),
            "custo_real": str(t.custo_real),
            "resultado": t.resultado,
            "erro": (t.erro or "")[:500],
        }


def _multipart(campos: dict[str, str], nome: str, conteudo: bytes, tipo: str) -> tuple[bytes, str]:
    fronteira = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(
            f'--{fronteira}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    partes.append(
        f'--{fronteira}\r\nContent-Disposition: form-data; name="document"; filename="{nome}"\r\n'
        f"Content-Type: {tipo}\r\n\r\n".encode()
        + conteudo
        + b"\r\n"
    )
    partes.append(f"--{fronteira}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def devolver(para: int, midia_ids: list[int]) -> int:
    """Manda as mídias como arquivo (qualidade cheia) para o chat do Eri."""
    from app.nucleo import midia
    from app.nucleo.pessoas import obter_pessoa_por_telegram

    enviadas = 0
    with sessao() as s:
        pessoa = obter_pessoa_por_telegram(s, para)
        if pessoa is None:
            raise SystemExit("essa pessoa não está cadastrada")
        for mid in midia_ids:
            m = midia.obter_midia(s, mid, pessoa.loja_id)  # só mídia da loja dele
            conteudo = midia.ler(s, m.id, pessoa.loja_id)
            ext = m.chave.rsplit(".", 1)[-1]
            corpo, ctype = _multipart(
                {"chat_id": str(para), "caption": f"mídia {m.id}"},
                f"midia_{m.id}.{ext}",
                conteudo,
                m.content_type,
            )
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{_token()}/sendDocument",
                data=corpo,
                headers={"Content-Type": ctype},
            )
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
                if json.loads(r.read()).get("ok"):
                    enviadas += 1
    return enviadas


def _ler_midias(de: int, ids: list[int]) -> list[tuple[int, bytes]]:
    from app.nucleo import midia
    from app.nucleo.pessoas import obter_pessoa_por_telegram

    with sessao() as s:
        pessoa = obter_pessoa_por_telegram(s, de)
        if pessoa is None:
            raise SystemExit("essa pessoa não está cadastrada")
        return [(i, midia.ler(s, i, pessoa.loja_id)) for i in ids]


def medir_rostos(de: int, reais: list[int], midias: list[int]) -> list[dict[str, Any]]:
    """Nota do medidor de rosto (0–100) de cada mídia contra as fotos reais. Grátis."""
    from app.geracao.medidor_rosto import medir

    fotos_reais = [b for _, b in _ler_midias(de, reais)]
    saida = []
    for mid, conteudo in _ler_midias(de, midias):
        m = medir(fotos_reais, conteudo)
        saida.append(
            {
                "midia": mid,
                "nota": m.nota,
                "cosseno": m.cosseno,
                "proporcao": m.proporcao,
                "aprovado": m.aprovado,
                "rosto_px": m.rosto_px,
                "diferencas": m.diferencas,
            }
        )
    return saida


def folha(de: int, midias: list[int], altura: int = 420, pedaco: int = 6000) -> list[str]:
    """Folha lado a lado (JPEG pequeno) em pedaços de base64, para o Claude olhar pelo Shell."""
    import base64

    import cv2
    import numpy as np

    quadros = []
    for mid, conteudo in _ler_midias(de, midias):
        img = cv2.imdecode(np.frombuffer(conteudo, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        img = cv2.resize(img, (int(w * altura / h), altura), interpolation=cv2.INTER_AREA)
        cv2.putText(img, str(mid), (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        quadros.append(img)
    ok, jpg = cv2.imencode(".jpg", np.hstack(quadros), [cv2.IMWRITE_JPEG_QUALITY, 80])
    b64 = base64.b64encode(jpg.tobytes()).decode()
    partes = [b64[i : i + pedaco] for i in range(0, len(b64), pedaco)]
    return [f"P{i + 1}/{len(partes)}#{p}#FIM" for i, p in enumerate(partes)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="telegram_teste")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    imp = sub.add_parser("importar")
    imp.add_argument("--de", type=int, required=True)
    inf = sub.add_parser("influencer")
    inf.add_argument("--de", type=int, required=True)
    inf.add_argument("--fotos", required=True, help="ids separados por vírgula")
    inf.add_argument("--idade", type=int, required=True)
    inf.add_argument("--oculos")
    inf.add_argument("--roupa", default="plain white crew-neck t-shirt and dark jeans")
    inf.add_argument("--aparencia", default="", help="traços do rosto, em inglês")
    inf.add_argument("--corpo-foto", type=int, help="mídia do corpo inteiro (só biótipo)")
    inf.add_argument("--corpo", default="same build and proportions as in the reference photos")
    inf.add_argument("--close", action="store_true", help="1º o close do rosto (E5)")
    fo = sub.add_parser("foto")
    fo.add_argument("--de", type=int, required=True)
    fo.add_argument("--influencer", type=int, required=True, help="mídia do rosto aprovado")
    fo.add_argument("--peca-fotos", required=True, help="mídias da peça, por vírgula")
    fo.add_argument("--entrada", required=True, help="arquivo JSON com os campos da foto")
    fo.add_argument("--opcoes", type=int, default=2)
    fo.add_argument("--rostos", default="", help="fotos REAIS do rosto (trava), por vírgula")
    fo.add_argument("--oculos", default="")
    ro = sub.add_parser("rosto")
    ro.add_argument("--de", type=int, required=True)
    ro.add_argument("--base", type=int, required=True, help="foto gerada a corrigir")
    ro.add_argument("--rostos", required=True, help="fotos REAIS do rosto, por vírgula")
    ro.add_argument("--tracos-arquivo", required=True)
    ro.add_argument("--oculos", default="")
    ro.add_argument("--genero", default="homem", choices=["homem", "mulher"])
    pe = sub.add_parser("pessoa")
    pe.add_argument("--de", type=int, required=True)
    pe.add_argument("--nome", required=True)
    pe.add_argument("--origem", required=True, help="como veio a autorização")
    for sp in (inf, fo, ro):
        sp.add_argument("--pessoa", type=int, help="dona do rosto (padrão: o Eri)")
    inf.add_argument("--genero", default="homem", choices=["homem", "mulher"])
    inf.add_argument("--tracos-arquivo", help="ler os traços de um arquivo")
    sit = sub.add_parser("situacao")
    sit.add_argument("chave")
    dev = sub.add_parser("devolver")
    dev.add_argument("--para", type=int, required=True)
    dev.add_argument("midias", type=int, nargs="+")
    pv = sub.add_parser("provador")
    pv.add_argument("--de", type=int, required=True)
    pv.add_argument("--foto-real", type=int, required=True, help="foto REAL de frente")
    pv.add_argument("--peca-fotos", required=True, help="mídias da peça, por vírgula")
    pv.add_argument("--entrada", required=True, help='JSON com "peca" e "cenario"')
    pv.add_argument("--reais", required=True, help="fotos reais para o medidor, por vírgula")
    pv.add_argument("--opcoes", type=int, default=2)
    pv.add_argument("--pessoa", type=int)
    pv.add_argument("--genero", default="homem", choices=["homem", "mulher"])
    di = sub.add_parser("dirigir")
    di.add_argument("--de", type=int, required=True)
    di.add_argument("--quadro", type=int, required=True, help="foto aprovada (1º quadro)")
    di.add_argument("--pedido", required=True, help="o que o lojista quer, em português")
    di.add_argument("--peca", required=True, help="descrição da peça")
    di.add_argument("--genero", default="homem", choices=["homem", "mulher"])
    di.add_argument("--saida", required=True)
    vi = sub.add_parser("video")
    vi.add_argument("--de", type=int, required=True)
    vi.add_argument("--quadro", type=int, required=True)
    vi.add_argument("--direcao", required=True)
    vi.add_argument("--angulo", required=True, choices=["problema_solucao", "prova_pessoal"])
    vi.add_argument("--pessoa", type=int)
    me = sub.add_parser("medir")
    me.add_argument("--de", type=int, required=True)
    me.add_argument("--reais", required=True, help="fotos REAIS de frente, por vírgula")
    me.add_argument("midias", type=int, nargs="+")
    fl = sub.add_parser("folha")
    fl.add_argument("--de", type=int, required=True)
    fl.add_argument("--altura", type=int, default=420)
    fl.add_argument("midias", type=int, nargs="+")
    a = p.parse_args(argv)

    if a.cmd == "listar":
        print("\n".join(listar()))
    elif a.cmd == "importar":
        print(json.dumps(importar(a.de), ensure_ascii=False, indent=1))
    elif a.cmd == "influencer":
        fotos = [int(x) for x in a.fotos.split(",") if x.strip()]
        aparencia = a.aparencia
        if a.tracos_arquivo:
            with open(a.tracos_arquivo, encoding="utf-8") as f:
                aparencia = f.read().strip()
        r = pedir_influencer(
            a.de,
            fotos,
            a.idade,
            a.oculos,
            a.roupa,
            aparencia=aparencia,
            corpo_midia=a.corpo_foto,
            close=a.close,
            corpo=a.corpo,
            pessoa_id=a.pessoa,
            genero=a.genero,
        )
        print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == "foto":
        with open(a.entrada, encoding="utf-8") as f:
            entrada = json.load(f)
        pecas = [int(x) for x in a.peca_fotos.split(",") if x.strip()]
        rostos = [int(x) for x in a.rostos.split(",") if x.strip()]
        r = pedir_foto(
            a.de,
            a.influencer,
            pecas,
            entrada,
            a.opcoes,
            rostos=rostos,
            oculos=a.oculos,
            pessoa_id=a.pessoa,
        )
        print(json.dumps(r))
    elif a.cmd == "rosto":
        with open(a.tracos_arquivo, encoding="utf-8") as f:
            tracos = f.read().strip()
        rostos = [int(x) for x in a.rostos.split(",") if x.strip()]
        print(json.dumps(travar_rosto(a.de, a.base, rostos, tracos, a.oculos, a.pessoa, a.genero)))
    elif a.cmd == "pessoa":
        print(json.dumps(nova_pessoa(a.de, a.nome, a.origem)))
    elif a.cmd == "situacao":
        print(json.dumps(situacao(a.chave), ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "devolver":
        print(f"enviadas: {devolver(a.para, a.midias)}")
    elif a.cmd == "provador":
        with open(a.entrada, encoding="utf-8") as arq:
            ent = json.load(arq)
        ids = lambda txt: [int(x) for x in txt.split(",") if x]  # noqa: E731
        r = provador(
            a.de,
            a.foto_real,
            ids(a.peca_fotos),
            ent["peca"],
            ent["cenario"],
            ids(a.reais),
            a.opcoes,
            a.pessoa,
            a.genero,
        )
        print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == "dirigir":
        r = dirigir(a.de, a.quadro, a.pedido, a.peca, a.genero)
        with open(a.saida, "w", encoding="utf-8") as arq:
            json.dump(r, arq, ensure_ascii=False)
        print("MENSAGEM:", r["mensagem"])
        for v in r["videos"]:
            print(f"== {v['angulo']} ({v['entrada']['duracao']} s)")
            for f in v["falas"]:
                print(f"  {f['de']:>4}-{f['ate']:<4} {f['fala'] or '(sem fala)'}")
    elif a.cmd == "video":
        with open(a.direcao, encoding="utf-8") as arq:
            r = json.load(arq)
        entrada = next(v["entrada"] for v in r["videos"] if v["angulo"] == a.angulo)
        print(json.dumps(gerar_video(a.de, a.quadro, entrada, a.pessoa), ensure_ascii=False))
    elif a.cmd == "medir":
        reais = [int(x) for x in a.reais.split(",") if x]
        for linha in medir_rostos(a.de, reais, a.midias):
            print(json.dumps(linha, ensure_ascii=False))
    elif a.cmd == "folha":
        print("\n".join(folha(a.de, a.midias, a.altura)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
