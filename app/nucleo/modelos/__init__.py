"""Todas as tabelas do núcleo (importar aqui registra no metadata do Alembic)."""

from app.nucleo.modelos.cadastro import Consentimento, Convite, Evento, Loja, Pessoa

__all__ = ["Consentimento", "Convite", "Evento", "Loja", "Pessoa"]
