"""Cliente do Claude: nova tentativa só quando a API está cheia (auditoria de 14/11)."""

import httpx
import pytest
from pydantic import SecretStr

from app.geracao.fornecedores.base import ErroFornecedor
from app.geracao.fornecedores.claude import ClienteClaude

OK = {"content": [{"type": "text", "text": '{"ok": true}'}], "stop_reason": "end_turn"}


def _cliente(respostas: list[httpx.Response]) -> tuple[ClienteClaude, list[float], list[int]]:
    esperas: list[float] = []
    chamadas: list[int] = []

    def responder(_: httpx.Request) -> httpx.Response:
        chamadas.append(1)
        return respostas.pop(0)

    http = httpx.Client(transport=httpx.MockTransport(responder))
    return ClienteClaude(SecretStr("chave"), http, esperas.append), esperas, chamadas


def test_api_cheia_tenta_de_novo_e_responde():
    cliente, esperas, chamadas = _cliente(
        [httpx.Response(529), httpx.Response(429), httpx.Response(200, json=OK)]
    )
    assert cliente.json("sistema", "texto") == {"ok": True}
    assert len(chamadas) == 3 and esperas == [2.0, 8.0]


def test_api_cheia_3_vezes_desiste_com_erro():
    cliente, _, chamadas = _cliente([httpx.Response(529) for _ in range(3)])
    with pytest.raises(ErroFornecedor):
        cliente.json("sistema", "texto")
    assert len(chamadas) == 3


def test_pedido_recusado_nao_tenta_de_novo():
    cliente, esperas, chamadas = _cliente([httpx.Response(400, text="pedido inválido")])
    with pytest.raises(ErroFornecedor):
        cliente.json("sistema", "texto")
    assert len(chamadas) == 1 and esperas == []
