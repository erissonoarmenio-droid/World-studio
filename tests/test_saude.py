from fastapi.testclient import TestClient

from app.main import criar_app


def test_saude_responde_ok():
    cliente = TestClient(criar_app())
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"
    assert resposta.json()["componentes"]["processo"] == "ok"


def test_saude_nao_expoe_detalhes_internos():
    corpo = TestClient(criar_app()).get("/saude").text.lower()
    for proibido in ("traceback", "postgres://", "password", "senha", "secret"):
        assert proibido not in corpo


def test_documentacao_desligada_em_producao(monkeypatch):
    from app.config import obter_config

    monkeypatch.setenv("AMBIENTE", "producao")
    obter_config.cache_clear()
    try:
        assert TestClient(criar_app()).get("/docs").status_code == 404
    finally:
        obter_config.cache_clear()
