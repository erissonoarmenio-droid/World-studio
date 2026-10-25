"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import Evento, Loja, Pessoa

__all__ = ["Evento", "Loja", "Pessoa"]
