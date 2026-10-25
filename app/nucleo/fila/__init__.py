"""Fila de trabalhos no próprio Postgres (tarefa 9: enfileirar sem gastar duas vezes).

- Cada pedido tem uma `chave_unica` (ex.: "loja7:pedido42:foto:v1"). Pedir de
  novo a mesma coisa devolve o trabalho que já existe, mesmo com dois pedidos
  chegando ao mesmo tempo (o banco decide: INSERT ... ON CONFLICT DO NOTHING).
- Nenhum trabalho entra sem a dona ter aceitado os termos.
- O trabalhador (pegar, concluir, re-tentar) entra na tarefa 10.
"""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.nucleo.consentimentos import exigir_termos_aceitos
from app.nucleo.erros import Conflito, DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.lojas import obter_loja
from app.nucleo.modelos import Trabalho
from app.nucleo.modelos.fila import TIPOS_TRABALHO

TAMANHO_MAXIMO_DADOS = 20_000  # caracteres em JSON; mídias vão por chave do R2, não aqui


def enfileirar(
    sessao: Session,
    *,
    loja_id: int,
    tipo: str,
    dados: dict[str, Any],
    chave_unica: str,
    autor: Autor,
    custo_estimado: Decimal | None = None,
    fornecedor: str | None = None,
) -> tuple[Trabalho, bool]:
    """Devolve (trabalho, criado_agora). criado_agora=False: já existia, nada novo."""
    if tipo not in TIPOS_TRABALHO:
        raise DadosInvalidos(f"tipo de trabalho desconhecido: {tipo!r}")
    chave_unica = chave_unica.strip()
    if not 3 <= len(chave_unica) <= 120:
        raise DadosInvalidos("chave_unica deve ter de 3 a 120 caracteres")
    if not isinstance(dados, dict):
        raise DadosInvalidos("dados do trabalho precisam ser um objeto")
    try:
        tamanho = len(json.dumps(dados))
    except (TypeError, ValueError):
        raise DadosInvalidos("dados do trabalho não podem ser guardados") from None
    if tamanho > TAMANHO_MAXIMO_DADOS:
        raise DadosInvalidos("dados do trabalho grandes demais (mande mídia pela chave do R2)")
    if custo_estimado is not None and custo_estimado < 0:
        raise DadosInvalidos("custo estimado não pode ser negativo")

    obter_loja(sessao, loja_id)
    exigir_termos_aceitos(sessao, loja_id)  # levanta SemConsentimento com o motivo

    novo_id = sessao.scalar(
        insert(Trabalho)
        .values(
            loja_id=loja_id,
            tipo=tipo,
            dados=dados,
            chave_unica=chave_unica,
            custo_estimado=custo_estimado,
            fornecedor=fornecedor,
        )
        .on_conflict_do_nothing(index_elements=["chave_unica"])
        .returning(Trabalho.id)
    )
    if novo_id is None:
        existente = sessao.scalar(select(Trabalho).where(Trabalho.chave_unica == chave_unica))
        assert existente is not None  # o conflito garante que existe
        if existente.loja_id != loja_id or existente.tipo != tipo:
            raise Conflito("essa chave_unica já pertence a outro pedido")
        return existente, False

    trabalho = sessao.get(Trabalho, novo_id)
    assert trabalho is not None
    registrar_evento(
        sessao,
        acao="trabalho_enfileirado",
        autor=autor,
        loja_id=loja_id,
        detalhes={
            "trabalho_id": trabalho.id,
            "tipo": tipo,
            "chave": chave_unica,
            "custo_estimado": str(custo_estimado) if custo_estimado is not None else None,
        },
    )
    return trabalho, True


def obter_trabalho(sessao: Session, trabalho_id: int, loja_id: int | None = None) -> Trabalho:
    """Com `loja_id`, só devolve se o trabalho for dessa loja (uma loja não vê a outra)."""
    trabalho = sessao.get(Trabalho, trabalho_id)
    if trabalho is None or (loja_id is not None and trabalho.loja_id != loja_id):
        raise NaoEncontrado("trabalho não encontrado")
    return trabalho
