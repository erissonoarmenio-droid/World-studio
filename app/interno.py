"""API interna (`/interno/...`): a mesma porta para a Central, o Cérebro e o site.

Só entra quem manda o cabeçalho `X-Chave-Interna` com a chave guardada no Render
(variável CHAVE_INTERNA, criada com o botão "Generate"). Sem a variável, tudo é recusado.
O bot roda no mesmo servidor e chama as funções direto, sem passar por aqui.
"""

import hmac
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app import pedidos
from app.config import obter_config
from app.creditos import servico as creditos
from app.nucleo.db import sessao
from app.nucleo.erros import (
    Conflito,
    DadosInvalidos,
    ErroNucleo,
    LojaDesligada,
    NaoEncontrado,
    SemConsentimento,
    SemCreditos,
    SemPermissao,
    TetoAtingido,
)
from app.nucleo.eventos import ERI, SISTEMA

CODIGO_DO_ERRO: dict[type[ErroNucleo], int] = {
    DadosInvalidos: 422,
    NaoEncontrado: 404,
    Conflito: 409,
    SemPermissao: 403,
    SemConsentimento: 403,
    LojaDesligada: 403,
    SemCreditos: 402,
    TetoAtingido: 429,
}


def resposta_de_erro(_: Request, erro: Exception) -> JSONResponse:
    """Erro do núcleo vira resposta com o motivo em português (seguro para mostrar)."""
    assert isinstance(erro, ErroNucleo)
    codigo = next((c for t, c in CODIGO_DO_ERRO.items() if isinstance(erro, t)), 400)
    corpo: dict[str, Any] = {"erro": type(erro).__name__, "motivo": erro.motivo}
    if isinstance(erro, SemCreditos):
        corpo["faltam"] = erro.faltam
    return JSONResponse(status_code=codigo, content=corpo)


def exigir_chave(x_chave_interna: Annotated[str | None, Header()] = None) -> None:
    chave = obter_config().chave_interna
    if chave is None or not chave.get_secret_value():
        raise HTTPException(503, "API interna desligada (falta a CHAVE_INTERNA no servidor)")
    if not x_chave_interna or not hmac.compare_digest(
        x_chave_interna.encode(), chave.get_secret_value().encode()
    ):
        raise HTTPException(401, "chave interna inválida")


rota = APIRouter(prefix="/interno", dependencies=[Depends(exigir_chave)], tags=["interno"])


class _Corpo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NovoPedido(_Corpo):
    loja_id: int
    item: str = Field(max_length=30)
    chave_unica: str = Field(min_length=3, max_length=120)
    quantidade: int = Field(default=1, ge=1, le=20)
    dados: dict[str, Any] = Field(default_factory=dict)


class AjusteCreditos(_Corpo):
    creditos: int = Field(ge=-1000, le=1000)
    motivo: str = Field(min_length=3, max_length=200)


class LiberarPlano(_Corpo):
    plano: str
    referencia: str = Field(min_length=3, max_length=120)


class Motivo(_Corpo):
    motivo: str = Field(default="", max_length=200)


def _num(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def _pedido_json(s: pedidos.Situacao) -> dict[str, Any]:
    return {
        "chave_unica": s.chave_unica,
        "loja_id": s.loja_id,
        "item": s.item,
        "creditos": s.creditos,
        "estado": s.estado,
        "credito": s.credito,
        "resultado": s.resultado,
        "custo_estimado_usd": _num(s.custo_estimado),
        "custo_real_usd": _num(s.custo_real),
    }


def _saldo_json(loja_id: int) -> dict[str, Any]:
    with sessao() as s:
        saldo = creditos.saldo(s, loja_id)
        assinatura = creditos.obter_assinatura(s, loja_id)
        return {
            "loja_id": loja_id,
            "disponivel": saldo.disponivel,
            "reservado": saldo.reservado,
            "vence_logo": saldo.vence_logo,
            "proximo_vencimento": saldo.proximo_vencimento.isoformat()
            if saldo.proximo_vencimento
            else None,
            "plano": assinatura.plano if assinatura else None,
            "situacao": assinatura.situacao if assinatura else "sem plano",
            "renova_em": assinatura.renova_em.isoformat() if assinatura else None,
        }


@rota.post("/pedidos")
def novo_pedido(corpo: NovoPedido) -> JSONResponse:
    with sessao() as s:
        situacao, criado = pedidos.criar_pedido(
            s,
            loja_id=corpo.loja_id,
            item=corpo.item,
            dados=corpo.dados,
            chave_unica=corpo.chave_unica,
            quantidade=corpo.quantidade,
            autor=SISTEMA,
        )
        return JSONResponse(status_code=201 if criado else 200, content=_pedido_json(situacao))


@rota.get("/pedidos/{chave_unica}")
def ver_pedido(chave_unica: str) -> dict[str, Any]:
    with sessao() as s:
        return _pedido_json(pedidos.obter_pedido(s, chave_unica))


@rota.get("/lojas/{loja_id}/saldo")
def ver_saldo(loja_id: int) -> dict[str, Any]:
    return _saldo_json(loja_id)


@rota.post("/lojas/{loja_id}/creditos")
def ajustar_creditos(loja_id: int, corpo: AjusteCreditos) -> dict[str, Any]:
    with sessao() as s:
        creditos.ajustar(s, loja_id, corpo.creditos, corpo.motivo, autor=ERI)
    return _saldo_json(loja_id)


@rota.post("/lojas/{loja_id}/plano")
def liberar_plano(loja_id: int, corpo: LiberarPlano) -> dict[str, Any]:
    """Liberar o plano na mão (piloto) ou pelo aviso do Mercado Pago (passo 1.5)."""
    with sessao() as s:
        creditos.ativar_plano(s, loja_id, corpo.plano, corpo.referencia, autor=ERI)
    return _saldo_json(loja_id)


@rota.post("/lojas/{loja_id}/pausar")
def pausar_loja(loja_id: int, corpo: Motivo) -> dict[str, Any]:
    with sessao() as s:
        creditos.pausar(s, loja_id, corpo.motivo or "pausada pelo Eri", autor=ERI)
    return _saldo_json(loja_id)


@rota.post("/lojas/{loja_id}/retomar")
def retomar_loja(loja_id: int) -> dict[str, Any]:
    with sessao() as s:
        creditos.retomar(s, loja_id, autor=ERI)
    return _saldo_json(loja_id)
