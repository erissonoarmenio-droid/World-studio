"""Consentimentos com versão do texto (tarefa 6).

- Cada pessoa aceita por si. Só ela mesma registra o próprio aceite.
- Os aceites que valem para a loja inteira (Instagram, WhatsApp, ordens fixas,
  modo automático, dados agregados) só a dona dá.
- Aceitar uma versão nova encerra a anterior; revogar marca a data. O histórico
  nunca é apagado (só some junto com a loja, no apagar da LGPD).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.erros import DadosInvalidos, NaoEncontrado, SemConsentimento, SemPermissao
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.modelos import Consentimento, Pessoa
from app.nucleo.modelos.cadastro import TIPOS_CONSENTIMENTO
from app.nucleo.pessoas import obter_pessoa

SO_DA_DONA = frozenset(
    {"dados_agregados", "instagram", "whatsapp", "ordem_fixa", "modo_automatico"}
)


def _agora() -> datetime:
    return datetime.now(UTC)


def _exigir_a_propria_pessoa(sessao: Session, pessoa_id: int, tipo: str, autor: Autor) -> Pessoa:
    if tipo not in TIPOS_CONSENTIMENTO:
        raise DadosInvalidos(f"tipo de consentimento desconhecido: {tipo!r}")
    pessoa = obter_pessoa(sessao, pessoa_id)
    if autor.tipo != "pessoa" or autor.pessoa_id != pessoa.id:
        raise SemPermissao("o aceite precisa ser dado pela própria pessoa")
    if tipo in SO_DA_DONA and pessoa.papel != "dona":
        raise SemPermissao("esse aceite vale para a loja inteira e só a dona pode dar")
    return pessoa


def consentimento_ativo(sessao: Session, pessoa_id: int, tipo: str) -> Consentimento | None:
    return sessao.scalar(
        select(Consentimento).where(
            Consentimento.pessoa_id == pessoa_id,
            Consentimento.tipo == tipo,
            Consentimento.revogado_em.is_(None),
        )
    )


def registrar_aceite(
    sessao: Session,
    pessoa_id: int,
    tipo: str,
    versao: str,
    autor: Autor,
    detalhes: dict[str, Any] | None = None,
    agora: datetime | None = None,
) -> Consentimento:
    pessoa = _exigir_a_propria_pessoa(sessao, pessoa_id, tipo, autor)
    versao = versao.strip()
    if not versao or len(versao) > 20:
        raise DadosInvalidos("versão do texto vazia ou longa demais")
    agora = agora or _agora()

    atual = consentimento_ativo(sessao, pessoa.id, tipo)
    if atual is not None and atual.versao == versao and atual.detalhes == (detalhes or {}):
        return atual  # aceitar de novo a mesma coisa não muda nada
    if atual is not None:
        atual.revogado_em = agora  # a versão nova substitui a anterior
        sessao.flush()

    novo = Consentimento(
        pessoa_id=pessoa.id,
        loja_id=pessoa.loja_id,
        tipo=tipo,
        versao=versao,
        aceito_em=agora,
        detalhes=detalhes or {},
    )
    sessao.add(novo)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="consentimento_aceito",
        autor=autor,
        loja_id=pessoa.loja_id,
        detalhes={"pessoa_id": pessoa.id, "tipo": tipo, "versao": versao},
    )
    return novo


def revogar(
    sessao: Session, pessoa_id: int, tipo: str, autor: Autor, agora: datetime | None = None
) -> Consentimento:
    pessoa = _exigir_a_propria_pessoa(sessao, pessoa_id, tipo, autor)
    atual = consentimento_ativo(sessao, pessoa.id, tipo)
    if atual is None:
        raise NaoEncontrado("não há aceite em vigor desse tipo")
    atual.revogado_em = agora or _agora()
    sessao.flush()
    registrar_evento(
        sessao,
        acao="consentimento_revogado",
        autor=autor,
        loja_id=pessoa.loja_id,
        detalhes={"pessoa_id": pessoa.id, "tipo": tipo, "versao": atual.versao},
    )
    return atual


def historico(sessao: Session, pessoa_id: int) -> list[Consentimento]:
    return list(
        sessao.scalars(
            select(Consentimento)
            .where(Consentimento.pessoa_id == pessoa_id)
            .order_by(Consentimento.aceito_em, Consentimento.id)
        )
    )


def exigir_termos_aceitos(sessao: Session, loja_id: int) -> None:
    """Nenhuma geração entra na fila sem a dona ter aceitado os termos e a privacidade."""
    aceite = sessao.scalar(
        select(Consentimento.id)
        .join(Pessoa, Pessoa.id == Consentimento.pessoa_id)
        .where(
            Consentimento.loja_id == loja_id,
            Consentimento.tipo == "termos_privacidade",
            Consentimento.revogado_em.is_(None),
            Pessoa.papel == "dona",
        )
    )
    if aceite is None:
        raise SemConsentimento(
            "a dona da loja ainda não aceitou os termos de uso e a política de privacidade"
        )
