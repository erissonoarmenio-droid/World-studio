"""Executores da fila: ligam um trabalho (pedido da lojista) aos nós de geração.

Passo 1.2, parte 4 (trajeto até 25/11). O trabalhador da fila chama o executor pelo tipo
do trabalho; o executor escolhe o nó pelo `dados["item"]`.

Ligados até agora:
- `foto` / `foto_outro_corpo` → nó `foto` (Google, modo lote = metade do preço, ~2 min),
  2 opções por pedido, guardadas no R2 como mídias da loja.

- `video_480` / `video_720` / `video_2_angulos` → nó `video_ugc` (Tein, Seedance 2.5), com o
  1º quadro subido para a Tein, consulta com sinal de vida e o vídeo baixado para o R2 na hora.

Ainda não ligados (o trabalho falha com motivo claro e os créditos voltam sozinhos):
foto de produto, criar influencer, voz, arte. O aviso automático da Tein (webhook) fica para
depois: por enquanto o executor consulta a cada 10 s (funciona, só ocupa o trabalhador).

Regras que valem para todo executor:
- Envio único com aprovação (`nos/envio.py`): o teto de cada envio é o custo estimado do
  pedido (o que a lojista já aprovou ao dizer "pode"), com folga de 30%.
- Pedido barrado por regra do nó (`PedidoBloqueado`) não gasta nada e falha com o motivo.
- Esperas longas mandam "sinal de vida" para a fila não achar que travou.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from app.config import obter_config
from app.geracao.fornecedores.base import Fornecedor, Resposta
from app.geracao.nos.base import No, Pedido
from app.geracao.nos.envio import Aprovacao, RegistroEmMemoria, enviar
from app.geracao.nos.foto import EntradaFoto, Imagem, NoFoto
from app.nucleo import midia
from app.nucleo.db import sessao as abrir_sessao
from app.nucleo.eventos import SISTEMA
from app.nucleo.fila.trabalhador import Resultado, sinal_de_vida
from app.nucleo.modelos import Trabalho

FOLGA_APROVACAO = Decimal("1.3")
ESPERA_ENTRE_CONSULTAS = 10.0  # segundos
ESPERA_MAXIMA = 15 * 60  # foto em lote ~2 min; vídeo 480p ~5–15 min


class NaoLigado(Exception):
    """Item que ainda não tem executor: o pedido falha e os créditos voltam."""


# Fábrica de fornecedores: trocada nos testes por um fornecedor simulado (sem rede).
def _google() -> Fornecedor:
    from app.geracao.fornecedores.google import Google

    chave = obter_config().google_api_key
    if chave is None:
        raise RuntimeError("GOOGLE_API_KEY não configurada no servidor")
    return Google(chave, modo="lote")


def _tein() -> Fornecedor:
    from app.geracao.fornecedores.tein import Tein

    chave = obter_config().tein_api_key
    if chave is None:
        raise RuntimeError("TEIN_API_KEY não configurada no servidor")
    return Tein(chave)


def _baixar(url: str) -> bytes:
    """A Tein apaga os arquivos em 14 dias: o vídeo é baixado e guardado no R2 na hora."""
    import httpx

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


FORNECEDORES: dict[str, Callable[[], Fornecedor]] = {"google": _google, "tein": _tein}
DORMIR: Callable[[float], None] = time.sleep
BAIXAR: Callable[[str], bytes] = _baixar


def _aguardar(
    fornecedor: Fornecedor, resposta: Resposta, trabalho_id: int, maximo: float = ESPERA_MAXIMA
) -> Resposta:
    """Consulta até ficar pronto ou falhar, avisando a fila que está vivo."""
    esperado = 0.0
    while resposta.estado == "na_fila":
        if esperado >= maximo:
            raise TimeoutError(f"o fornecedor passou de {int(maximo // 60)} min sem terminar")
        DORMIR(ESPERA_ENTRE_CONSULTAS)
        esperado += ESPERA_ENTRE_CONSULTAS
        with abrir_sessao() as s:
            sinal_de_vida(s, trabalho_id)
        assert resposta.id is not None
        resposta = fornecedor.consultar(resposta.id)
    if resposta.estado == "falhou":
        raise RuntimeError(f"o fornecedor recusou: {resposta.erro[:200]}")
    return resposta


def _gerar(
    no: No,
    pedido: Pedido,
    trabalho: Trabalho,
    teto: Decimal,
    fornecedor: Fornecedor | None = None,
    maximo: float = ESPERA_MAXIMA,
) -> Resposta:
    fornecedor = fornecedor or FORNECEDORES[pedido.fornecedor]()
    aprovacao = Aprovacao(por=f"loja:{trabalho.loja_id}", custo_max=teto)
    resposta = enviar(no, pedido, aprovacao, fornecedor, RegistroEmMemoria())
    return _aguardar(fornecedor, resposta, trabalho.id, maximo)


def _imagem(loja_id: int, midia_id: int | None) -> Imagem | None:
    if midia_id is None:
        return None
    with abrir_sessao() as s:
        m = midia.obter_midia(s, midia_id, loja_id)
        tipo = m.content_type if m.content_type in ("image/jpeg", "image/png") else "image/jpeg"
        conteudo = midia.ler(s, midia_id, loja_id)
    return Imagem(mime=tipo, dados_b64=base64.b64encode(conteudo).decode())


def _imagens_da_resposta(resposta: Resposta) -> list[tuple[bytes, str]]:
    imagens = []
    for parte in resposta.saidas:
        dados = (parte or {}).get("inlineData") or (parte or {}).get("inline_data")
        if dados and dados.get("data"):
            tipo = dados.get("mimeType") or dados.get("mime_type") or "image/png"
            imagens.append((base64.b64decode(dados["data"]), tipo))
    return imagens


def executar_foto_influencer(trabalho: Trabalho) -> Resultado:
    """dados: {"entrada": campos de EntradaFoto sem imagens,
    "influencer_midia_id", "ancora_midia_id"?, "cenario_midia_id"?, "opcoes": 2}."""
    d: dict[str, Any] = trabalho.dados
    opcoes = int(d.get("opcoes", 2))
    if not 1 <= opcoes <= 4:
        raise ValueError("opcoes fora do limite (1 a 4)")
    entrada = EntradaFoto(
        **d["entrada"],
        influencer=_imagem(trabalho.loja_id, d["influencer_midia_id"]),
        ancora=_imagem(trabalho.loja_id, d.get("ancora_midia_id")),
        cenario_foto=_imagem(trabalho.loja_id, d.get("cenario_midia_id")),
    )
    no = NoFoto()
    pedido, _ = no.preparar(entrada)  # PedidoBloqueado aqui: nada foi gasto
    estimado = trabalho.custo_estimado or pedido.custo_estimado * opcoes
    teto = estimado * FOLGA_APROVACAO / opcoes  # teto por envio

    custo = Decimal("0")
    midias: list[int] = []
    for _ in range(opcoes):
        resposta = _gerar(no, pedido, trabalho, teto)
        custo += (
            Decimal(str(resposta.custo)) if resposta.custo is not None else pedido.custo_estimado
        )
        for conteudo, tipo in _imagens_da_resposta(resposta)[:1]:
            with abrir_sessao() as s:
                m = midia.enviar(
                    s,
                    loja_id=trabalho.loja_id,
                    conteudo=conteudo,
                    tipo="resultado",
                    content_type=tipo,
                    origem="geracao",
                    autor=SISTEMA,
                )
                midias.append(m.id)
    if not midias:
        raise RuntimeError("o fornecedor terminou sem nenhuma imagem")
    return Resultado({"midias": midias, "no": no.nome}, custo)


ESPERA_MAXIMA_VIDEO = 45 * 60  # 720p na fila da Tein: 20–40 min (01/11)


def executar_video(trabalho: Trabalho) -> Resultado:
    """dados: {"entradas": [campos de EntradaUGC sem imagem_url] (1, ou 2 para os 2 ângulos),
    "primeiro_quadro_midia_id": foto aprovada da influencer com a peça}.

    O roteiro (planos e falas) já chega pronto do diretor; aqui só gera, baixa e guarda.
    Reenvio por queda do servidor não cobra 2×: a Tein usa a `idempotency_key` do payload.
    """
    from app.geracao.nos.video_ugc import EntradaUGC, NoVideoUGC

    d: dict[str, Any] = trabalho.dados
    entradas = d.get("entradas") or []
    esperado = 2 if d.get("item") == "video_2_angulos" else 1
    if len(entradas) != esperado:
        raise ValueError(f"o pedido precisa de {esperado} roteiro(s) de vídeo")
    resolucao = "720p" if d.get("item") == "video_720" else "480p"

    fornecedor = FORNECEDORES["tein"]()
    with abrir_sessao() as s:
        m = midia.obter_midia(s, d["primeiro_quadro_midia_id"], trabalho.loja_id)
        tipo_quadro = m.content_type
        quadro = midia.ler(s, m.id, trabalho.loja_id)
    url_quadro = fornecedor.subir_midia(quadro, "quadro1.png", tipo_quadro)  # type: ignore[attr-defined]

    no = NoVideoUGC()
    pedidos_prontos = []
    for campos in entradas:  # confere TODOS antes de gastar qualquer um
        entrada = EntradaUGC(**{**campos, "resolucao": resolucao, "imagem_url": url_quadro})
        pedidos_prontos.append(no.preparar(entrada)[0])
    estimado = trabalho.custo_estimado or sum(p.custo_estimado for p in pedidos_prontos)
    teto = estimado * FOLGA_APROVACAO / len(pedidos_prontos)

    custo = Decimal("0")
    midias: list[int] = []
    for pedido in pedidos_prontos:
        resposta = _gerar(no, pedido, trabalho, teto, fornecedor, ESPERA_MAXIMA_VIDEO)
        custo += (
            Decimal(str(resposta.custo)) if resposta.custo is not None else pedido.custo_estimado
        )
        url = next((x for x in resposta.saidas if isinstance(x, str)), None)
        if url is None:
            raise RuntimeError("a Tein terminou sem o link do vídeo")
        conteudo = BAIXAR(url)
        with abrir_sessao() as s:
            v = midia.enviar(
                s,
                loja_id=trabalho.loja_id,
                conteudo=conteudo,
                tipo="video",
                content_type="video/mp4",
                origem="geracao",
                autor=SISTEMA,
            )
            midias.append(v.id)
    return Resultado({"midias": midias, "no": no.nome, "resolucao": resolucao}, custo)


EXECUTORES_FOTO: dict[str, Callable[[Trabalho], Resultado]] = {
    "foto": executar_foto_influencer,
    "foto_outro_corpo": executar_foto_influencer,
}


def executar_tipo_foto(trabalho: Trabalho) -> Resultado:
    item = trabalho.dados.get("item", "foto")
    executor = EXECUTORES_FOTO.get(item)
    if executor is None:
        raise NaoLigado(f"o item {item!r} ainda não está ligado à geração")
    return executor(trabalho)
