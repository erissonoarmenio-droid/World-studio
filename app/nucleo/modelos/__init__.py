"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import (
    CodigoRecuperacao,
    Consentimento,
    Convite,
    Evento,
    Fiscal,
    Loja,
    PalavraSenha,
    PerfilLoja,
    Pessoa,
)

__all__ = [
    "CodigoRecuperacao",
    "Consentimento",
    "Convite",
    "Evento",
    "Fiscal",
    "Loja",
    "PalavraSenha",
    "PerfilLoja",
    "Pessoa",
]
