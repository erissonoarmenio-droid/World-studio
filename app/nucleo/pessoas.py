"""Pessoas de cada loja (dona, sócia, funcionária).

`pode_aprovar_gastos`: a dona sempre pode; as outras só com liberação da dona
(tarefa 5). Papel e permissão não mudam por `editar_pessoa`.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.modelos import Loja, Pessoa

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DadosPessoa(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome: str = Field(min_length=2, max_length=120)
    papel: str = "dona"
    telegram_id: int | None = Field(default=None, gt=0)
    whatsapp: str | None = None
    email: str | None = Field(default=None, max_length=254)

    @field_validator("papel")
    @classmethod
    def papel_conhecido(cls, v: str) -> str:
        if v not in ("dona", "socia", "funcionaria"):
            raise ValueError("papel deve ser dona, socia ou funcionaria")
        return v

    @field_validator("whatsapp")
    @classmethod
    def so_digitos(cls, v: str | None) -> str | None:
        if v is None:
            return None
        digitos = re.sub(r"\D", "", v)
        if not 10 <= len(digitos) <= 13:
            raise ValueError("WhatsApp deve ter de 10 a 13 dígitos (com DDD)")
        return digitos

    @field_validator("email")
    @classmethod
    def email_valido(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _EMAIL.match(v):
            raise ValueError("e-mail inválido")
        return v.lower()


class EdicaoPessoa(DadosPessoa):
    """Campos que podem ser editados (todos opcionais; papel não entra)."""

    nome: str | None = Field(default=None, min_length=2, max_length=120)  # type: ignore[assignment]
    papel: None = None  # type: ignore[assignment]


def validar(modelo: type[BaseModel], dados: dict[str, Any]) -> BaseModel:
    """Valida e transforma o erro do pydantic num motivo legível."""
    try:
        return modelo.model_validate(dados)
    except ValidationError as erro:
        primeiro = erro.errors()[0]
        campo = ".".join(str(p) for p in primeiro["loc"]) or "dados"
        raise DadosInvalidos(f"{campo}: {primeiro['msg']}") from None


def _garantir_telegram_livre(sessao: Session, telegram_id: int | None, exceto: int | None) -> None:
    if telegram_id is None:
        return
    dono = sessao.scalar(select(Pessoa.id).where(Pessoa.telegram_id == telegram_id))
    if dono is not None and dono != exceto:
        raise Conflito("esse Telegram já está ligado a outra pessoa")


def adicionar_pessoa(sessao: Session, loja_id: int, dados: dict[str, Any], autor: Autor) -> Pessoa:
    d: DadosPessoa = validar(DadosPessoa, dados)  # type: ignore[assignment]
    if sessao.get(Loja, loja_id) is None:
        raise NaoEncontrado("loja não encontrada")
    if d.papel == "dona":
        ja_tem = sessao.scalar(
            select(Pessoa.id).where(Pessoa.loja_id == loja_id, Pessoa.papel == "dona")
        )
        if ja_tem is not None:
            raise Conflito("essa loja já tem uma dona")
    _garantir_telegram_livre(sessao, d.telegram_id, exceto=None)

    pessoa = Pessoa(loja_id=loja_id, pode_aprovar_gastos=d.papel == "dona", **d.model_dump())
    sessao.add(pessoa)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="pessoa_criada",
        autor=autor,
        loja_id=loja_id,
        detalhes={"pessoa_id": pessoa.id, "papel": pessoa.papel},
    )
    return pessoa


def obter_pessoa(sessao: Session, pessoa_id: int) -> Pessoa:
    pessoa = sessao.get(Pessoa, pessoa_id)
    if pessoa is None:
        raise NaoEncontrado("pessoa não encontrada")
    return pessoa


def obter_pessoa_por_telegram(sessao: Session, telegram_id: int) -> Pessoa | None:
    return sessao.scalar(select(Pessoa).where(Pessoa.telegram_id == telegram_id))


def editar_pessoa(
    sessao: Session, pessoa_id: int, mudancas: dict[str, Any], autor: Autor
) -> Pessoa:
    proibidos = {"papel", "pode_aprovar_gastos", "loja_id", "id"} & mudancas.keys()
    if proibidos:
        raise DadosInvalidos(f"não pode ser mudado por aqui: {', '.join(sorted(proibidos))}")
    e = validar(EdicaoPessoa, mudancas)
    pessoa = obter_pessoa(sessao, pessoa_id)
    campos = e.model_dump(exclude_unset=True)
    if "telegram_id" in campos:
        _garantir_telegram_livre(sessao, campos["telegram_id"], exceto=pessoa.id)
    if campos.get("nome", "x") is None:
        raise DadosInvalidos("nome não pode ficar vazio")
    alterados = [c for c, v in campos.items() if getattr(pessoa, c) != v]
    for campo in alterados:
        setattr(pessoa, campo, campos[campo])
    if alterados:
        sessao.flush()
        registrar_evento(
            sessao,
            acao="pessoa_editada",
            autor=autor,
            loja_id=pessoa.loja_id,
            detalhes={"pessoa_id": pessoa.id, "campos": sorted(alterados)},
        )
    return pessoa
