"""Executores da fila: ligam um trabalho (pedido da lojista) aos nós de geração.

Passo 1.2, parte 4 (trajeto até 25/11). O trabalhador da fila chama o executor pelo tipo
do trabalho; o executor escolhe o nó pelo `dados["item"]`.

Ligados até agora:
- `foto` / `foto_outro_corpo` → nó `foto` (Google, modo lote = metade do preço, ~2 min),
  2 opções por pedido, guardadas no R2 como mídias da loja.

- `video_480` / `video_720` / `video_2_angulos` → nó `video_ugc` (Tein, Seedance 2.5), com o
  1º quadro subido para a Tein, consulta com sinal de vida e o vídeo baixado para o R2 na hora.

- `foto_produto` → nó `foto_produto` (extrai a peça 1× por peça e reaproveita; depois a cena).

- `influencer_principal` / `influencer_extra` / `ajuste_rosto` → nó `influencer` (criar nova,
  da própria pessoa com consentimento "clone", ajustar, ou gerar as vistas close + costas).

Ainda não ligados (o trabalho falha com motivo claro e os créditos voltam sozinhos): voz, arte.
O aviso automático da Tein (webhook) fica para
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
from app.geracao.nos.envio import Aprovacao, Envio, enviar
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


class RegistroDoTrabalho:
    """Registro de envios guardado no próprio trabalho (`dados["envios"]`), no banco (E36, 06/11).

    Se a tentativa cai (tempo esgotado, servidor reiniciado) depois de o fornecedor aceitar o
    pedido, a próxima tentativa acha o id e só CONSULTA o mesmo lote — não paga duas vezes.
    `vez` separa envios iguais de propósito (as 2 opções de uma foto são o mesmo pedido).
    """

    def __init__(self, trabalho_id: int, vez: int) -> None:
        self.trabalho_id = trabalho_id
        self.vez = vez

    def _ler(self) -> dict[str, Any]:
        with abrir_sessao() as s:
            t = s.get(Trabalho, self.trabalho_id)
            return dict((t.dados or {}).get("envios") or {}) if t else {}

    def _gravar(self, envios: dict[str, Any]) -> None:
        with abrir_sessao() as s:
            t = s.get(Trabalho, self.trabalho_id, with_for_update=True)
            if t is not None:
                t.dados = {**(t.dados or {}), "envios": envios}

    def _k(self, chave: str) -> str:
        return f"{self.vez}:{chave[:32]}"

    def obter(self, chave: str) -> Envio | None:
        e = self._ler().get(self._k(chave))
        return Envio(e["estado"], e.get("id")) if e else None

    def guardar(self, chave: str, envio: Envio) -> None:
        envios = self._ler()
        envios[self._k(chave)] = {"estado": envio.estado, "id": envio.id_fornecedor}
        self._gravar(envios)

    def apagar(self, chave: str) -> None:
        envios = self._ler()
        envios.pop(self._k(chave), None)
        self._gravar(envios)


def _gerar(
    no: No,
    pedido: Pedido,
    trabalho: Trabalho,
    teto: Decimal,
    fornecedor: Fornecedor | None = None,
    maximo: float = ESPERA_MAXIMA,
    vez: int = 0,
) -> Resposta:
    fornecedor = fornecedor or FORNECEDORES[pedido.fornecedor]()
    aprovacao = Aprovacao(por=f"loja:{trabalho.loja_id}", custo_max=teto)
    registro = RegistroDoTrabalho(trabalho.id, vez)
    resposta = enviar(no, pedido, aprovacao, fornecedor, registro)
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
    for vez in range(opcoes):
        resposta = _gerar(no, pedido, trabalho, teto, vez=vez)
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
    for vez, pedido in enumerate(pedidos_prontos):
        resposta = _gerar(no, pedido, trabalho, teto, fornecedor, ESPERA_MAXIMA_VIDEO, vez)
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


def _guardar_imagem(loja_id: int, conteudo: bytes, tipo_conteudo: str, tipo: str) -> int:
    with abrir_sessao() as s:
        m = midia.enviar(
            s,
            loja_id=loja_id,
            conteudo=conteudo,
            tipo=tipo,
            content_type=tipo_conteudo,
            origem="geracao",
            autor=SISTEMA,
        )
        return m.id


def executar_foto_produto(trabalho: Trabalho) -> Resultado:
    """dados: {"peca_midia_id" (foto do lojista), "peca_nome", "detalhes", "cena",
    "cena_livre"?, "proporcao"?, "extraida_midia_id"?, "opcoes": 2}.

    1) Extrai a peça da foto do lojista (1× por peça: se já existe `extraida_midia_id` no
       catálogo, reaproveita e não gasta de novo). 2) Põe a peça na cena, N opções.
    O resultado devolve `extraida_midia_id` para o bot guardar no catálogo da peça."""
    from app.geracao.nos.foto_produto import EntradaProduto, NoFotoProduto

    d: dict[str, Any] = trabalho.dados
    opcoes = int(d.get("opcoes", 2))
    if not 1 <= opcoes <= 4:
        raise ValueError("opcoes fora do limite (1 a 4)")
    comum = {
        "peca_nome": d["peca_nome"],
        "detalhes": d["detalhes"],
        "proporcao": d.get("proporcao", "4:5"),
    }
    no = NoFotoProduto()
    # Confere a cena ANTES de gastar com a extração (cena livre sem descrição, por exemplo).
    cena_campos = {"cena": d.get("cena", "cama"), "cena_livre": d.get("cena_livre", "")}
    EntradaProduto(
        etapa="cena", foto=_imagem(trabalho.loja_id, d["peca_midia_id"]), **comum, **cena_campos
    )

    teto = (trabalho.custo_estimado or Decimal("0.08")) * FOLGA_APROVACAO
    custo = Decimal("0")
    extraida_id = d.get("extraida_midia_id")
    if extraida_id is None:
        entrada = EntradaProduto(
            etapa="extrair", foto=_imagem(trabalho.loja_id, d["peca_midia_id"]), **comum
        )
        pedido, _ = no.preparar(entrada)
        resposta = _gerar(no, pedido, trabalho, teto)
        custo += _custo(resposta, pedido)
        imagens = _imagens_da_resposta(resposta)
        if not imagens:
            raise RuntimeError("a extração da peça terminou sem imagem")
        conteudo, tipo = imagens[0]
        extraida_id = _guardar_imagem(trabalho.loja_id, conteudo, tipo, "peca")

    entrada = EntradaProduto(
        etapa="cena", foto=_imagem(trabalho.loja_id, extraida_id), **comum, **cena_campos
    )
    pedido, _ = no.preparar(entrada)
    midias: list[int] = []
    for vez in range(opcoes):
        resposta = _gerar(no, pedido, trabalho, teto, vez=vez)
        custo += _custo(resposta, pedido)
        for conteudo, tipo in _imagens_da_resposta(resposta)[:1]:
            midias.append(_guardar_imagem(trabalho.loja_id, conteudo, tipo, "resultado"))
    if not midias:
        raise RuntimeError("o fornecedor terminou sem nenhuma imagem")
    return Resultado({"midias": midias, "no": no.nome, "extraida_midia_id": extraida_id}, custo)


def _custo(resposta: Resposta, pedido: Pedido) -> Decimal:
    return Decimal(str(resposta.custo)) if resposta.custo is not None else pedido.custo_estimado


def executar_influencer(trabalho: Trabalho) -> Resultado:
    """Criar a influencer (principal), ajustar o rosto ou gerar as vistas (close + costas).

    dados: {"modo": "nova" | "da_pessoa" | "ajuste" | "vistas", "genero", "idade", "corpo",
    "roupa", "aparencia"?, "oculos"?, "fotos_midia_ids"? (da_pessoa, até 6),
    "pessoa_id"? (da_pessoa: dona do rosto), "anterior_midia_id"? (ajuste/vistas), "mudanca"?}.
    Cobrança (decidida pelo bot ao criar o pedido): 1ª influencer, 3 primeiros ajustes e vistas
    no item `influencer_principal` (0 cr); 2ª/3ª em `influencer_extra` (5 cr); do 4º ajuste em
    diante `ajuste_rosto` (2 cr).
    """
    from app.geracao.nos.influencer import EntradaInfluencer, NoInfluencer
    from app.nucleo.consentimentos import consentimento_ativo

    d: dict[str, Any] = dict(trabalho.dados)
    modo = d.pop("modo")
    comum = {
        k: d[k]
        for k in ("genero", "idade", "corpo", "roupa", "aparencia", "oculos", "mudanca")
        if k in d
    }
    loja = trabalho.loja_id
    entradas: list[EntradaInfluencer] = []
    if modo == "da_pessoa":
        pessoa_id = d.get("pessoa_id")
        with abrir_sessao() as s:
            if pessoa_id is None or consentimento_ativo(s, pessoa_id, "clone") is None:
                raise PermissionError(
                    "rosto de pessoa real só com o consentimento 'clone' dela registrado"
                )
        ids = list(d.get("fotos_midia_ids") or [])[:6]
        fotos = [_imagem(loja, i) for i in ids]
        entradas.append(
            EntradaInfluencer(
                modo="da_pessoa",
                fotos=fotos,
                foto_corpo=_imagem(loja, d.get("corpo_midia_id")),
                enquadramento=d.get("enquadramento", "corpo"),
                **comum,
            )
        )
    elif modo == "vistas":
        anterior = _imagem(loja, d.get("anterior_midia_id"))
        for vista in ("close", "costas"):
            entradas.append(
                EntradaInfluencer(modo="vista", vista=vista, anterior=anterior, **comum)
            )
    elif modo in ("nova", "ajuste"):
        anterior = _imagem(loja, d.get("anterior_midia_id")) if modo == "ajuste" else None
        entradas.append(EntradaInfluencer(modo=modo, anterior=anterior, **comum))
    else:
        raise ValueError(f"modo desconhecido: {modo!r}")

    no = NoInfluencer()
    pedidos_prontos = [no.preparar(e)[0] for e in entradas]  # confere tudo antes de gastar
    teto = max(trabalho.custo_estimado or Decimal("0"), Decimal("0.40")) * FOLGA_APROVACAO
    custo = Decimal("0")
    midias: list[int] = []
    for vez, pedido in enumerate(pedidos_prontos):
        resposta = _gerar(no, pedido, trabalho, teto, vez=vez)
        custo += _custo(resposta, pedido)
        for conteudo, tipo in _imagens_da_resposta(resposta)[:1]:
            midias.append(_guardar_imagem(loja, conteudo, tipo, "influencer"))
    if not midias:
        raise RuntimeError("o fornecedor terminou sem nenhuma imagem")
    return Resultado({"midias": midias, "no": no.nome, "modo": modo}, custo)


EXECUTORES_FOTO: dict[str, Callable[[Trabalho], Resultado]] = {
    "influencer_principal": executar_influencer,
    "influencer_extra": executar_influencer,
    "ajuste_rosto": executar_influencer,
    "foto": executar_foto_influencer,
    "foto_outro_corpo": executar_foto_influencer,
    "foto_produto": executar_foto_produto,
}


def executar_tipo_foto(trabalho: Trabalho) -> Resultado:
    item = trabalho.dados.get("item", "foto")
    executor = EXECUTORES_FOTO.get(item)
    if executor is None:
        raise NaoLigado(f"o item {item!r} ainda não está ligado à geração")
    return executor(trabalho)
