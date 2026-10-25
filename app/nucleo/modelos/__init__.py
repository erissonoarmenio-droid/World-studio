"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import (
    Consentimento,
    Convite,
    Evento,
    Fiscal,
    Loja,
    PerfilLoja,
    Pessoa,
)

__all__ = ["Consentimento", "Convite", "Evento", "Fiscal", "Loja", "PerfilLoja", "Pessoa"]
