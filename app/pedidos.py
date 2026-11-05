"""Pedidos: a porta única de tudo o que gasta (passo 1.2 do trajeto).

Um pedido = reservar créditos + pôr o trabalho na fila, na MESMA transação. A mesma
`chave_unica` serve para os dois, então pedir de novo devolve o mesmo pedido sem cobrar.

Quando a fila termina:
- concluído → `creditos.confirmar` (desconta de vez e guarda o custo real);
- falhou de vez (3 tentativas) → `creditos.estornar` (devolve os créditos).
O trabalhador chama `ao_concluir` / `ao_falhar_de_vez` (ver `nucleo/fila/trabalhador.py`).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.creditos import servico as creditos
from app.nucleo.consentimentos import exigir_termos_aceitos
from app.nucleo.erros import DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import SISTEMA, Autor
from app.nucleo.fila import enfileirar
from app.nucleo.modelos import Reserva, Trabalho

# Item vendido (tabela de créditos) → tipo de trabalho da fila. O executor de cada tipo
# lê `dados["item"]` para escolher o nó certo (foto, foto de produto, criar influencer...).
TIPO_DO_ITEM: dict[str, str] = {
    "foto": "foto",
    "foto_outro_corpo": "foto",
    "foto_produto": "foto",
    "influencer_principal": "foto",
    "influencer_extra": "foto",
    "ajuste_rosto": "foto",
    "arte": "arte",
    "video_480": "video",
    "video_2_angulos": "video",
    "video_720": "video",
    "voz_exclusiva": "voz",
}


@dataclass(frozen=True)
class Situacao:
    """Como o pedido está, do jeito que o bot e a Central precisam ver."""

    chave_unica: str
    loja_id: int
    item: str
    creditos: int
    estado: str  # na_fila | rodando | pronto | falhou | cancelado
    credito: str  # reservada | debitada | estornada
    resultado: dict[str, Any] | None
    custo_estimado: Decimal
    custo_real: Decimal | None


def _estado_publico(trabalho: Trabalho) -> str:
    return "pronto" if trabalho.estado == "concluido" else trabalho.estado


def criar_pedido(
    sessao: Session,
    *,
    loja_id: int,
    item: str,
    dados: dict[str, Any],
    chave_unica: str,
    quantidade: int = 1,
    autor: Autor = SISTEMA,
) -> tuple[Situacao, bool]:
    """Reserva os créditos e enfileira. Devolve (situação, criado_agora)."""
    if item not in TIPO_DO_ITEM:
        raise DadosInvalidos(f"item desconhecido: {item!r}")
    chave_unica = chave_unica.strip()
    if not 3 <= len(chave_unica) <= 120:
        raise DadosInvalidos("chave_unica deve ter de 3 a 120 caracteres")
    exigir_termos_aceitos(sessao, loja_id)  # antes de reservar: nada fica pela metade
    reserva = creditos.reservar(
        sessao, loja_id, item, chave_unica, quantidade=quantidade, autor=autor
    )
    trabalho, criado = enfileirar(
        sessao,
        loja_id=loja_id,
        tipo=TIPO_DO_ITEM[item],
        dados={**dados, "item": item, "quantidade": quantidade},
        chave_unica=chave_unica,
        autor=autor,
        custo_estimado=reserva.custo_estimado,
        fornecedor=reserva.fornecedor,
    )
    return _situacao(reserva, trabalho), criado


def _situacao(reserva: Reserva, trabalho: Trabalho) -> Situacao:
    return Situacao(
        chave_unica=reserva.chave_unica,
        loja_id=reserva.loja_id,
        item=reserva.item,
        creditos=reserva.creditos,
        estado=_estado_publico(trabalho),
        credito=reserva.estado,
        resultado=trabalho.resultado if trabalho.estado == "concluido" else None,
        custo_estimado=reserva.custo_estimado,
        custo_real=reserva.custo_real,
    )


def obter_pedido(sessao: Session, chave_unica: str, loja_id: int | None = None) -> Situacao:
    reserva = sessao.scalar(select(Reserva).where(Reserva.chave_unica == chave_unica))
    trabalho = sessao.scalar(select(Trabalho).where(Trabalho.chave_unica == chave_unica))
    if reserva is None or trabalho is None or (loja_id is not None and reserva.loja_id != loja_id):
        raise NaoEncontrado("pedido não encontrado")
    return _situacao(reserva, trabalho)


# --- chamados pelo trabalhador da fila ----------------------------------------------------


def _tem_reserva(sessao: Session, chave_unica: str) -> bool:
    return sessao.scalar(select(Reserva.id).where(Reserva.chave_unica == chave_unica)) is not None


def ao_concluir(sessao: Session, trabalho: Trabalho) -> None:
    """Trabalho pronto: desconta de vez e guarda o custo real (se o pedido veio por aqui)."""
    if _tem_reserva(sessao, trabalho.chave_unica):
        creditos.confirmar(sessao, trabalho.chave_unica, custo_real=trabalho.custo_real)


def ao_falhar_de_vez(sessao: Session, trabalho: Trabalho) -> None:
    """Falhou nas 3 tentativas: a lojista não paga pela falha."""
    if _tem_reserva(sessao, trabalho.chave_unica):
        creditos.estornar(sessao, trabalho.chave_unica, "geração falhou (3 tentativas)")
