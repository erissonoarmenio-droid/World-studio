"""Convite para sócia ou funcionária entrar na loja (tarefa 5).

- Só a dona gera (o Eri também, para dar suporte no piloto).
- O código aparece uma única vez, para a dona repassar; no banco fica só o hash.
- Vale uma vez e por 48 h.
- `pode_aprovar_gastos` só muda por ação da dona.

O código tem 8 letras/números de um alfabeto sem caracteres parecidos (~10^12
combinações) e vence em 48 h, por isso um hash SHA-256 basta (não é senha
escolhida por pessoa, que precisaria de Argon2). Tentativas erradas não viram
evento aqui (a recusa desfaz a transação); o limite de tentativas por pessoa
fica no módulo `conversa`, que conta antes de chamar.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.erros import DadosInvalidos, NaoEncontrado, SemPermissao
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.lojas import obter_loja
from app.nucleo.modelos import Convite, Pessoa
from app.nucleo.pessoas import adicionar_pessoa, obter_pessoa

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sem 0/O, 1/I/L
TAMANHO = 8
VALIDADE = timedelta(hours=48)


def _agora() -> datetime:
    return datetime.now(UTC)


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


def _normalizar(codigo: str) -> str:
    return "".join(c for c in codigo.upper() if c.isalnum())


def _exigir_dona(sessao: Session, loja_id: int, autor: Autor) -> None:
    """A ação precisa ser da dona desta loja."""
    if autor.tipo != "pessoa":
        raise SemPermissao("só a dona da loja pode fazer isso")
    pessoa = obter_pessoa(sessao, autor.pessoa_id)  # type: ignore[arg-type]
    if pessoa.loja_id != loja_id or pessoa.papel != "dona":
        raise SemPermissao("só a dona da loja pode fazer isso")


def gerar_convite(
    sessao: Session, loja_id: int, papel: str, autor: Autor, agora: datetime | None = None
) -> tuple[Convite, str]:
    """Devolve o convite e o código em texto (mostrar uma vez e não guardar)."""
    if papel not in ("socia", "funcionaria"):
        raise DadosInvalidos("convite só para sócia ou funcionária")
    obter_loja(sessao, loja_id)
    if autor.tipo != "eri":
        _exigir_dona(sessao, loja_id, autor)

    codigo = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
    convite = Convite(
        loja_id=loja_id,
        papel=papel,
        codigo_hash=_hash(codigo),
        criado_por=autor.pessoa_id,
        expira_em=(agora or _agora()) + VALIDADE,
    )
    sessao.add(convite)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="convite_criado",
        autor=autor,
        loja_id=loja_id,
        detalhes={"convite_id": convite.id, "papel": papel},
    )
    return convite, f"{codigo[:4]}-{codigo[4:]}"


def usar_convite(
    sessao: Session, codigo: str, dados: dict[str, Any], agora: datetime | None = None
) -> Pessoa:
    """A pessoa convidada entra com o código. Recusa código errado, usado ou vencido."""
    agora = agora or _agora()
    convite = sessao.scalar(
        select(Convite).where(Convite.codigo_hash == _hash(_normalizar(codigo))).with_for_update()
    )
    if convite is None:
        raise NaoEncontrado("código de convite não encontrado")
    if convite.usado_em is not None:
        raise DadosInvalidos("esse código de convite já foi usado")
    if convite.expira_em <= agora:
        raise DadosInvalidos("esse código de convite venceu (vale 48 horas)")

    if "papel" in dados:
        raise DadosInvalidos("o papel vem do convite, não pode ser escolhido")
    pessoa = adicionar_pessoa(
        sessao, convite.loja_id, {**dados, "papel": convite.papel}, Autor("sistema")
    )
    convite.usado_por = pessoa.id
    convite.usado_em = agora
    sessao.flush()
    registrar_evento(
        sessao,
        acao="convite_usado",
        autor=Autor("pessoa", pessoa.id),
        loja_id=convite.loja_id,
        detalhes={"convite_id": convite.id, "pessoa_id": pessoa.id},
    )
    return pessoa


def definir_permissao_gastos(
    sessao: Session, pessoa_id: int, permitir: bool, autor: Autor
) -> Pessoa:
    """Só a dona libera ou tira de outra pessoa a permissão de aprovar gastos."""
    pessoa = obter_pessoa(sessao, pessoa_id)
    _exigir_dona(sessao, pessoa.loja_id, autor)
    if pessoa.papel == "dona":
        raise DadosInvalidos("a dona sempre pode aprovar gastos")
    if pessoa.pode_aprovar_gastos != permitir:
        pessoa.pode_aprovar_gastos = permitir
        sessao.flush()
        registrar_evento(
            sessao,
            acao="permissao_gastos_alterada",
            autor=autor,
            loja_id=pessoa.loja_id,
            detalhes={"pessoa_id": pessoa.id, "pode_aprovar_gastos": permitir},
        )
    return pessoa
