"""Erros do núcleo. Cada um traz um `motivo` em português, seguro para mostrar a quem chamou."""


class ErroNucleo(Exception):
    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


class DadosInvalidos(ErroNucleo):
    """O que chegou não passou na validação."""


class NaoEncontrado(ErroNucleo):
    """Loja ou pessoa não existe."""


class Conflito(ErroNucleo):
    """Viola uma regra de unicidade (Telegram já usado, loja já tem dona, @ já cadastrado)."""


class SemPermissao(ErroNucleo):
    """Quem pediu não tem o papel necessário (ex.: só a dona pode)."""


class SemConsentimento(ErroNucleo):
    """Falta um aceite obrigatório (ex.: termos e privacidade antes de gerar)."""


class PalavraBloqueada(ErroNucleo):
    """Errou a palavra-senha 5 vezes: espera 15 minutos."""


class PalavraNecessaria(ErroNucleo):
    """A ação pede a palavra-senha e ela não foi digitada nos últimos 30 minutos."""
