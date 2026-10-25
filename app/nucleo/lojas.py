"""Lojas: criar (já com a dona), ler e editar. Toda mudança vira evento."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.modelos import Loja, Pessoa
from app.nucleo.pessoas import adicionar_pessoa, validar

UFS = frozenset(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)
_INSTAGRAM = re.compile(r"^[a-z0-9._]{1,30}$")


class DadosLoja(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nome: str = Field(min_length=2, max_length=120)
    instagram: str | None = None
    segmento: str | None = Field(default=None, max_length=60)
    cidade: str | None = Field(default=None, max_length=80)
    uf: str | None = None
    canais_venda: list[str] = Field(default_factory=list, max_length=10)
    horario: str | None = Field(default=None, max_length=200)
    endereco: str | None = Field(default=None, max_length=300)

    @field_validator("instagram")
    @classmethod
    def instagram_valido(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.removeprefix("@").lower()
        if not _INSTAGRAM.match(v):
            raise ValueError("@ do Instagram inválido")
        return v

    @field_validator("uf")
    @classmethod
    def uf_valida(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper()
        if v not in UFS:
            raise ValueError("UF inválida")
        return v

    @field_validator("canais_venda")
    @classmethod
    def canais_curtos(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        limpos = [c.strip() for c in v if c.strip()]
        if any(len(c) > 40 for c in limpos):
            raise ValueError("cada canal de venda tem no máximo 40 letras")
        return limpos


class EdicaoLoja(DadosLoja):
    nome: str | None = Field(default=None, min_length=2, max_length=120)  # type: ignore[assignment]
    canais_venda: list[str] | None = Field(default=None, max_length=10)  # type: ignore[assignment]


def _garantir_instagram_livre(sessao: Session, instagram: str | None, exceto: int | None) -> None:
    if instagram is None:
        return
    outra = sessao.scalar(select(Loja.id).where(Loja.instagram == instagram))
    if outra is not None and outra != exceto:
        raise Conflito("esse @ do Instagram já está cadastrado em outra loja")


def criar_loja_com_dona(
    sessao: Session, loja: dict[str, Any], dona: dict[str, Any], autor: Autor
) -> tuple[Loja, Pessoa]:
    """Cria a loja e a dona juntas (uma loja nunca existe sem dona). Gera 2 eventos."""
    d = validar(DadosLoja, loja)
    if dona.get("papel", "dona") != "dona":
        raise DadosInvalidos("a primeira pessoa da loja precisa ser a dona")
    _garantir_instagram_livre(sessao, d.instagram, exceto=None)  # type: ignore[attr-defined]

    nova = Loja(**d.model_dump())
    sessao.add(nova)
    sessao.flush()
    registrar_evento(sessao, acao="loja_criada", autor=autor, loja_id=nova.id)
    pessoa = adicionar_pessoa(sessao, nova.id, {**dona, "papel": "dona"}, autor)
    return nova, pessoa


def obter_loja(sessao: Session, loja_id: int) -> Loja:
    loja = sessao.get(Loja, loja_id)
    if loja is None:
        raise NaoEncontrado("loja não encontrada")
    return loja


def editar_loja(sessao: Session, loja_id: int, mudancas: dict[str, Any], autor: Autor) -> Loja:
    proibidos = {"id", "plano", "situacao", "criada_em"} & mudancas.keys()
    if proibidos:
        raise DadosInvalidos(f"não pode ser mudado por aqui: {', '.join(sorted(proibidos))}")
    e = validar(EdicaoLoja, mudancas)
    loja = obter_loja(sessao, loja_id)
    campos = e.model_dump(exclude_unset=True)
    if "nome" in campos and campos["nome"] is None:
        raise DadosInvalidos("nome não pode ficar vazio")
    if campos.get("canais_venda", []) is None:
        campos["canais_venda"] = []
    if "instagram" in campos:
        _garantir_instagram_livre(sessao, campos["instagram"], exceto=loja.id)
    alterados = [c for c, v in campos.items() if getattr(loja, c) != v]
    for campo in alterados:
        setattr(loja, campo, campos[campo])
    if alterados:
        sessao.flush()
        registrar_evento(
            sessao,
            acao="loja_editada",
            autor=autor,
            loja_id=loja.id,
            detalhes={"campos": sorted(alterados)},
        )
    return loja
