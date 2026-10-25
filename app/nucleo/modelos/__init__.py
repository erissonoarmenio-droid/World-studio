"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import Convite, Evento, Loja, Pessoa

__all__ = ["Convite", "Evento", "Loja", "Pessoa"]
