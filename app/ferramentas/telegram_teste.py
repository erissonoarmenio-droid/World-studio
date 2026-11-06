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
) -> dict[str, Any]:
    from app.nucleo.pessoas import obter_pessoa_por_telegram
    from app.pedidos import criar_pedido

    if not 2 <= len(fotos) <= 6:
        raise SystemExit("mande de 2 a 6 fotos do rosto")
    with sessao() as s:
        pessoa = obter_pessoa_por_telegram(s, telegram_id)
        if pessoa is None:
            raise SystemExit("rode o importar primeiro")
        dados: dict[str, Any] = {
            "modo": "da_pessoa",
            "pessoa_id": pessoa.id,
            "fotos_midia_ids": fotos,
            "genero": "homem",
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
    inf.add_argument("--aparencia", required=True, help="traços do rosto, em inglês")
    inf.add_argument("--corpo-foto", type=int, help="mídia do corpo inteiro (só biótipo)")
    inf.add_argument("--corpo", default="same build and proportions as in the reference photos")
    inf.add_argument("--close", action="store_true", help="1º o close do rosto (E5)")
    sit = sub.add_parser("situacao")
    sit.add_argument("chave")
    dev = sub.add_parser("devolver")
    dev.add_argument("--para", type=int, required=True)
    dev.add_argument("midias", type=int, nargs="+")
    a = p.parse_args(argv)

    if a.cmd == "listar":
        print("\n".join(listar()))
    elif a.cmd == "importar":
        print(json.dumps(importar(a.de), ensure_ascii=False, indent=1))
    elif a.cmd == "influencer":
        fotos = [int(x) for x in a.fotos.split(",") if x.strip()]
        r = pedir_influencer(
            a.de,
            fotos,
            a.idade,
            a.oculos,
            a.roupa,
            aparencia=a.aparencia,
            corpo_midia=a.corpo_foto,
            close=a.close,
            corpo=a.corpo,
        )
        print(json.dumps(r, ensure_ascii=False))
    elif a.cmd == "situacao":
        print(json.dumps(situacao(a.chave), ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "devolver":
        print(f"enviadas: {devolver(a.para, a.midias)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
