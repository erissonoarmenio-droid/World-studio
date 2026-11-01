"""Diretor UGC: transforma o pedido do lojista (conversa + foto do local) em 2 vídeos.

Pedido em linguagem natural → Claude escreve 2 ângulos de venda (problema-solução e prova
pessoal) no formato de planos do nó `video_ugc` → cada ângulo passa pelas regras do nó.
Se alguma regra que bloqueia falhar, o diretor devolve as falhas ao Claude UMA vez para
corrigir; se falhar de novo, para e relata (nada é enviado ao gerador aqui).

Não engessa a conversa (Eri, 01/11): o lugar, a peça, as ações, as falas, a luz, os cortes
e a duração vêm do pedido. Fixo é só o que faz parecer real (Método W-orld v3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from app.geracao.nos.base import Pedido, PedidoBloqueado, Relatorio
from app.geracao.nos.video_ugc import EntradaUGC, NoVideoUGC

ANGULOS = ("problema_solucao", "prova_pessoal")

SISTEMA = """Você é o diretor de vídeos UGC de uma influencer de IA que trabalha para lojas de
roupa no Brasil. Você recebe o pedido do lojista (texto livre), a descrição da peça e, às
vezes, a foto do local. Você devolve SÓ um JSON com 2 vídeos curtos de story de Instagram,
um para cada ângulo de venda:
- "problema_solucao": a peça resolve algo concreto (calor, amassar, combinar, caimento).
- "prova_pessoal": a influencer conta a experiência dela com a peça ("eu já separei uma pra
  mim"). NUNCA invente depoimento de cliente, número de vendas, preço ou dado que o lojista
  não deu.

Siga o pedido do lojista (lugar, ação, clima). Se ele não disse o que quer, escolha você algo
que combine com a peça e com o local, e diga isso na "mensagem_para_lojista".

REGRAS (o sistema bloqueia se quebrar):
1. Corpo vivo: em CADA plano ela faz uma ação de corpo inteiro (andar, dar um passo, virar,
   balançar, inclinar, segurar/levantar/empurrar a peça na frente do corpo, sentar, pendurar,
   ir até a arara). Use verbos em inglês (walks, steps, turns, sways, leans, holds, lifts,
   pushes, sits, hangs, reaches). O 1º plano começa no meio de um movimento ("Starts
   mid-movement: she walks...").
2. 3 a 5 planos (2 a 4 jump cuts). Tempos em segundos: o 1º começa em 0, cada um começa onde
   o anterior termina, o último termina na duração. Duração 12 a 16 s.
3. Enquadramento dos planos 2+ em inglês e curto: "Slightly closer", "Slightly wider",
   "Chest-up", "Waist-up". NUNCA "extreme close-up". O 1º plano sem enquadramento.
4. "acao" em inglês, terminando no gancho da fala (ex.: "... and says:" ou "... at it:").
   "fala" em português do Brasil falado, SEM aspas: frases curtas e quebradas, pelo menos
   uma muleta (gente, olha, ó, tipo, né, sério), nada de propaganda (proibido: imperdível,
   corre que acaba, você precisa, obcecada, game changer, melhor do mundo).
   "depois" (opcional) em inglês: reação depois da fala; pode citar entre aspas UMA palavra
   que está na fala (ex.: Small shrug on "sério").
5. Total de palavras faladas até (duração − 2) × 2,5. Deixe respiros.
6. Quem filma é uma AMIGA com o celular na mão (a câmera é fixa no sistema): no "contexto"
   NUNCA diga que ela segura o celular ou filma a si mesma.
7. Use os móveis que existem no local (se a foto mostra poltrona, é "armchair", não "sofa").
8. Descreva a peça em inglês com cor, tecido e detalhes que não podem mudar (gola, botões,
   bolsos, mangas). "peca_nunca" lista o que nunca muda (ex.: "colour, collar, buttons or
   fabric; no pocket appears").

FORMATO DE SAÍDA (só o JSON, nada mais):
{
  "mensagem_para_lojista": "frase natural da influencer, em português, dizendo o que vai fazer
     (e sugerindo, se o lojista não especificou). Sem lista, sem menu.",
  "peca_nome": "shirt",
  "peca": "terracotta long-sleeve shirt (...)",
  "peca_nunca": "colour, ...",
  "videos": [
    {"angulo": "problema_solucao", "duracao": 15,
     "contexto": "1–2 frases em inglês: quem é ela, o que mostra, para quem filma; termina com
        'It must feel like a real, slightly messy story, not a fashion commercial.'",
     "cenario": "frase em inglês sobre o lugar, ex.: The store room stays as in @image1.",
     "luz": "luz real do lugar em inglês, ex.: Soft daylight from a window on the left",
     "som_peca": "sons do produto em inglês, ex.: soft fabric rustle, wooden hanger click",
     "planos": [{"inicio": 0, "fim": 5, "enquadramento": "", "acao": "...", "fala": "...",
                 "depois": ""}]},
    {"angulo": "prova_pessoal", ...}
  ]
}

EXEMPLO de planos aprovados pelo dono (vídeo real que ficou ótimo):
[{"inicio":0,"fim":5,"enquadramento":"","acao":"Starts mid-movement: she walks two steps
toward the camera from the clothing rack, holding the shirt on its wooden hanger, already
turning to the lens. She takes a small breath, laughs softly through her nose and says:",
"fala":"Gente, olha isso... chegou hoje e eu já separei uma pra mim.","depois":"Eyebrows
lift on \\"separei\\"; her free hand points at herself on \\"pra mim\\"."},
{"inicio":5,"fim":8.4,"enquadramento":"Slightly closer","acao":"She turns her body sideways
to the camera and holds the shirt up against her torso, swaying her hips a little as she
looks down at it:","fala":"Ó, isso aqui é linho, tipo...","depois":""},
{"inicio":8.4,"fim":11.7,"enquadramento":"Slightly wider","acao":"She steps half a step
forward and pushes the shirt toward the lens, rubbing the fabric between two fingers, then
lifts the pointed collar and lets it fall:","fala":"...sente a textura. E não esquenta nada,
sério.","depois":"Small shrug with both shoulders on \\"sério\\", weight shifting to the
other leg."},
{"inicio":11.7,"fim":16,"enquadramento":"Chest-up","acao":"She tosses the hanger over her
shoulder, leans slightly toward the lens with her head tilted and says, relaxed:","fala":"Quer
ver ela vestida? Me chama no direct.","depois":"A short light chuckle, then she starts to
turn away toward the rack with a lopsided smile and a glance back."}]
"""


class CerebroJSON(Protocol):
    def json(
        self, sistema: str, texto: str, imagens: list[tuple[bytes, str]] | None = None
    ) -> dict[str, Any]: ...


@dataclass
class VideoDirigido:
    angulo: str
    pedido: Pedido
    relatorio: Relatorio


@dataclass
class Direcao:
    mensagem_para_lojista: str
    videos: list[VideoDirigido] = field(default_factory=list)
    tentativas: int = 1


class DirecaoFalhou(Exception):
    """O roteiro não passou nas regras nem depois da correção. Nada foi enviado."""


def _entradas(dados: dict[str, Any], imagem_url: str | None) -> list[tuple[str, EntradaUGC]]:
    saida = []
    for v in dados["videos"]:
        saida.append(
            (
                v["angulo"],
                EntradaUGC(
                    planos=v["planos"],
                    duracao=v["duracao"],
                    peca_nome=dados["peca_nome"],
                    peca=dados["peca"],
                    peca_nunca=dados["peca_nunca"],
                    contexto=v["contexto"],
                    cenario=v.get("cenario") or "The store room stays as in @image1.",
                    luz=v["luz"],
                    som_peca=v["som_peca"],
                    imagem_url=imagem_url,
                ),
            )
        )
    return saida


def _avaliar(dados: dict[str, Any], imagem_url: str | None) -> tuple[list[VideoDirigido], str]:
    """Monta e checa os 2 vídeos. Devolve (vídeos ok, texto das falhas para corrigir)."""
    no = NoVideoUGC()
    falhas: list[str] = []
    videos: list[VideoDirigido] = []
    try:
        angulos = [v.get("angulo") for v in dados.get("videos", [])]
        if sorted(angulos) != sorted(ANGULOS):
            falhas.append(f"os 2 vídeos precisam ser os ângulos {ANGULOS}; veio {angulos}")
        else:
            for angulo, entrada in _entradas(dados, imagem_url):
                try:
                    pedido, relatorio = no.preparar(entrada)
                    videos.append(VideoDirigido(angulo, pedido, relatorio))
                except PedidoBloqueado as erro:
                    falhas.append(f"[{angulo}] {erro.relatorio.resumo()}")
    except (KeyError, TypeError, AttributeError, ValidationError) as erro:
        falhas.append(f"JSON fora do formato: {erro}")
    return videos, "\n".join(falhas)


class DiretorUGC:
    def __init__(self, cerebro: CerebroJSON) -> None:
        self.cerebro = cerebro

    def dirigir(
        self,
        pedido_lojista: str,
        peca: str,
        imagem_url: str | None = None,
        foto_local: tuple[bytes, str] | None = None,
        local: str = "",
    ) -> Direcao:
        texto = (
            f"PEDIDO DO LOJISTA: {pedido_lojista or '(não disse o que quer — sugira)'}\n"
            f"PEÇA: {peca}\n"
            f"LOCAL: {local or ('ver a foto' if foto_local else 'a loja do 1º quadro')}"
        )
        imagens = [foto_local] if foto_local else None
        dados = self.cerebro.json(SISTEMA, texto, imagens)
        videos, falhas = _avaliar(dados, imagem_url)
        if not falhas:
            return Direcao(dados.get("mensagem_para_lojista", ""), videos, 1)
        correcao = (
            texto
            + "\n\nSUA RESPOSTA ANTERIOR:\n"
            + json.dumps(dados, ensure_ascii=False)
            + "\n\nO SISTEMA BLOQUEOU POR ESTES MOTIVOS. Corrija só isso e devolva o JSON "
            "completo:\n" + falhas
        )
        dados = self.cerebro.json(SISTEMA, correcao, imagens)
        videos, falhas = _avaliar(dados, imagem_url)
        if falhas:
            raise DirecaoFalhou(falhas)
        return Direcao(dados.get("mensagem_para_lojista", ""), videos, 2)
