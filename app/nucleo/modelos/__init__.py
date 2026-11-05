"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import (
    CodigoRecuperacao,
    Consentimento,
    Convite,
    Evento,
    Fiscal,
    Loja,
    Midia,
    PalavraSenha,
    PerfilLoja,
    Pessoa,
)
from app.nucleo.modelos.creditos import Assinatura, Lancamento, Lote, Reserva
from app.nucleo.modelos.fila import Trabalho

__all__ = [
    "Assinatura",
    "Lancamento",
    "Lote",
    "Reserva",
    "CodigoRecuperacao",
    "Consentimento",
    "Convite",
    "Evento",
    "Fiscal",
    "Loja",
    "Midia",
    "PalavraSenha",
    "PerfilLoja",
    "Pessoa",
    "Trabalho",
]
