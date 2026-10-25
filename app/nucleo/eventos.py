"""Registro de eventos: quem fez o quê, quando e quanto custou.

Regra de LGPD: os detalhes guardam NOMES de campos e identificadores, nunca o
conteúdo pessoal (nome, telefone, e-mail) — esse fica só na tabela de origem.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.erros import DadosInvalidos
from app.nucleo.modelos import Evento
from app.nucleo.modelos.cadastro import TIPOS_AUTOR


@dataclass(frozen=True)
class Autor:
    """Quem fez a ação. `pessoa_id` só quando tipo == 'pessoa'."""

    tipo: str
    pessoa_id: int | None = None

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS_AUTOR:
            raise DadosInvalidos(f"autor desconhecido: {self.tipo!r}")
        if (self.tipo == "pessoa") != (self.pessoa_id is not None):
            raise DadosInvalidos("autor 'pessoa' precisa de pessoa_id (e só ele)")


SISTEMA = Autor("sistema")
ERI = Autor("eri")


def registrar_evento(
    sessao: Session,
    *,
    acao: str,
    autor: Autor = SISTEMA,
    loja_id: int | None = None,
    detalhes: dict[str, Any] | None = None,
    custo: Decimal | None = None,
) -> Evento:
    if not acao or len(acao) > 60:
        raise DadosInvalidos("ação do evento vazia ou longa demais")
    if custo is not None and custo < 0:
        raise DadosInvalidos("custo não pode ser negativo")
    evento = Evento(
        acao=acao,
        quem=autor.tipo,
        pessoa_id=autor.pessoa_id,
        loja_id=loja_id,
        detalhes=detalhes or {},
        custo=custo,
    )
    sessao.add(evento)
    sessao.flush()
    return evento


def listar_eventos(sessao: Session, loja_id: int, limite: int = 100) -> list[Evento]:
    """Eventos de uma loja, do mais antigo para o mais novo."""
    consulta = (
        select(Evento)
        .where(Evento.loja_id == loja_id)
        .order_by(Evento.quando, Evento.id)
        .limit(limite)
    )
    return list(sessao.scalars(consulta))
