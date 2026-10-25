"""Perfil da loja e dados fiscais (tarefa 7).

Perfil: cada campo guarda o valor, DE ONDE veio (instagram, conversa, eri) e
QUANDO. O evento registra só o nome do campo e a origem, nunca o valor.

Fiscal: CPF ou CNPJ conferido pelo dígito verificador. A consulta pública do
CNPJ (situação e razão social) entra com o módulo `pagamento`.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.nucleo.erros import DadosInvalidos, SemPermissao
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.lojas import obter_loja
from app.nucleo.modelos import Fiscal, PerfilLoja
from app.nucleo.pessoas import obter_pessoa

SECOES = ("marca", "influencer", "respostas", "preferencias", "observacoes")
ORIGENS = ("instagram", "conversa", "eri")
_CAMPO = re.compile(rf"^({'|'.join(SECOES)})\.[a-z][a-z0-9_]{{0,39}}$")
TAMANHO_MAXIMO = 4000  # caracteres do valor em JSON


def _agora() -> datetime:
    return datetime.now(UTC)


# --- perfil ------------------------------------------------------------------


def atualizar_perfil(
    sessao: Session,
    loja_id: int,
    mudancas: dict[str, Any],
    origem: str,
    autor: Autor,
    agora: datetime | None = None,
) -> PerfilLoja:
    """`mudancas` = {"marca.tom": "descontraído", ...}. Valor None apaga o campo."""
    if origem not in ORIGENS:
        raise DadosInvalidos(f"origem deve ser uma de: {', '.join(ORIGENS)}")
    if not mudancas:
        raise DadosInvalidos("nada para atualizar")
    for campo, valor in mudancas.items():
        if not _CAMPO.match(campo):
            raise DadosInvalidos(f"campo de perfil inválido: {campo!r}")
        try:
            tamanho = len(json.dumps(valor, ensure_ascii=False))
        except (TypeError, ValueError):
            raise DadosInvalidos(f"{campo}: valor não pode ser guardado") from None
        if tamanho > TAMANHO_MAXIMO:
            raise DadosInvalidos(f"{campo}: valor grande demais")

    obter_loja(sessao, loja_id)
    perfil = sessao.get(PerfilLoja, loja_id) or PerfilLoja(loja_id=loja_id, dados={})
    em = (agora or _agora()).isoformat()
    dados = dict(perfil.dados)
    alterados = []
    for campo, valor in mudancas.items():
        atual = dados.get(campo)
        if valor is None:
            if atual is not None:
                del dados[campo]
                alterados.append(campo)
        elif atual is None or atual["valor"] != valor:
            dados[campo] = {"valor": valor, "origem": origem, "em": em}
            alterados.append(campo)
    if not alterados:
        return perfil
    perfil.dados = dados  # novo dict: o SQLAlchemy percebe a mudança
    sessao.add(perfil)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="perfil_atualizado",
        autor=autor,
        loja_id=loja_id,
        detalhes={"campos": sorted(alterados), "origem": origem},
    )
    return perfil


def ler_perfil(sessao: Session, loja_id: int) -> dict[str, dict[str, Any]]:
    """Só os valores, agrupados por seção: {"marca": {"tom": ...}, ...}."""
    perfil = sessao.get(PerfilLoja, loja_id)
    saida: dict[str, dict[str, Any]] = {}
    for campo, info in (perfil.dados if perfil else {}).items():
        secao, nome = campo.split(".", 1)
        saida.setdefault(secao, {})[nome] = info["valor"]
    return saida


# --- fiscal ------------------------------------------------------------------


def _digitos_cpf_ok(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _digitos_cnpj_ok(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n in (12, 13):
        pesos = [*range(n - 7, 1, -1), *range(9, 1, -1)]
        soma = sum(int(d[i]) * pesos[i] for i in range(n))
        resto = soma % 11
        if (0 if resto < 2 else 11 - resto) != int(d[n]):
            return False
    return True


def validar_documento(documento: str) -> tuple[str, str]:
    """Devolve (tipo, só dígitos) ou recusa com motivo."""
    d = re.sub(r"\D", "", documento)
    if len(d) == 11 and _digitos_cpf_ok(d):
        return "cpf", d
    if len(d) == 14 and _digitos_cnpj_ok(d):
        return "cnpj", d
    raise DadosInvalidos("CPF ou CNPJ inválido (confira os números)")


def registrar_fiscal(
    sessao: Session,
    loja_id: int,
    documento: str,
    autor: Autor,
    razao_social: str | None = None,
) -> Fiscal:
    """Só a dona ou o Eri. O número nunca vai para o evento."""
    obter_loja(sessao, loja_id)
    if autor.tipo == "pessoa":
        pessoa = obter_pessoa(sessao, autor.pessoa_id)  # type: ignore[arg-type]
        if pessoa.loja_id != loja_id or pessoa.papel != "dona":
            raise SemPermissao("só a dona da loja pode informar os dados fiscais")
    elif autor.tipo != "eri":
        raise SemPermissao("só a dona da loja pode informar os dados fiscais")
    tipo, digitos = validar_documento(documento)
    if razao_social is not None:
        razao_social = razao_social.strip()
        if not 2 <= len(razao_social) <= 200:
            raise DadosInvalidos("razão social deve ter de 2 a 200 letras")

    fiscal = sessao.get(Fiscal, loja_id) or Fiscal(loja_id=loja_id)
    fiscal.tipo, fiscal.documento, fiscal.razao_social = tipo, digitos, razao_social
    fiscal.situacao = fiscal.conferido_em = None  # nova conferência pública, quando houver
    sessao.add(fiscal)
    sessao.flush()
    registrar_evento(
        sessao, acao="fiscal_registrado", autor=autor, loja_id=loja_id, detalhes={"tipo": tipo}
    )
    return fiscal
