"""Tarefa 11: fotos e vídeos no R2 (simulado com moto)."""

import io
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws

from app.nucleo import midia as mod
from app.nucleo.erros import DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import ERI, listar_eventos
from app.nucleo.lojas import criar_loja_com_dona
from app.nucleo.midia import (
    Armazenamento,
    apagar,
    enviar,
    ler,
    link_temporario,
    listar_midias,
    pasta_da_loja,
)

PNG = b"\x89PNG\r\n\x1a\nfalso"


@pytest.fixture
def r2():
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="midias-teste")
        yield Armazenamento(cliente, "midias-teste")


@pytest.fixture
def duas_lojas(sessao_limpa):
    a, _ = criar_loja_com_dona(sessao_limpa, {"nome": "Loja A"}, {"nome": "Ana"}, ERI)
    b, _ = criar_loja_com_dona(sessao_limpa, {"nome": "Loja B"}, {"nome": "Bia"}, ERI)
    return a, b


def mandar(s, loja, r2, **extra):
    args = {
        "loja_id": loja.id,
        "conteudo": PNG,
        "tipo": "peca",
        "content_type": "image/png",
        "origem": "lojista",
        "autor": ERI,
        "armazenamento": r2,
    }
    return enviar(s, **{**args, **extra})


def test_enviar_guarda_na_pasta_da_loja(sessao_limpa, duas_lojas, r2):
    a, _ = duas_lojas
    m = mandar(sessao_limpa, a, r2)
    assert m.chave.startswith(f"lojas/{a.id}/peca/") and m.chave.endswith(".png")
    assert m.tamanho == len(PNG)
    assert r2.listar(pasta_da_loja(a.id)) == [m.chave]
    assert ler(sessao_limpa, m.id, a.id, r2) == PNG
    ultimo = listar_eventos(sessao_limpa, a.id)[-1]
    assert ultimo.acao == "midia_enviada" and ultimo.detalhes["tipo"] == "peca"


def test_outra_loja_nao_le_nem_apaga(sessao_limpa, duas_lojas, r2):
    a, b = duas_lojas
    m = mandar(sessao_limpa, a, r2)
    with pytest.raises(NaoEncontrado):
        ler(sessao_limpa, m.id, b.id, r2)
    with pytest.raises(NaoEncontrado):
        link_temporario(sessao_limpa, m.id, b.id, r2)
    with pytest.raises(NaoEncontrado):
        apagar(sessao_limpa, m.id, b.id, ERI, r2)
    assert ler(sessao_limpa, m.id, a.id, r2) == PNG  # continua lá


def test_link_vale_uma_hora(sessao_limpa, duas_lojas, r2):
    a, _ = duas_lojas
    m = mandar(sessao_limpa, a, r2)
    url = link_temporario(sessao_limpa, m.id, a.id, r2)
    parametros = parse_qs(urlparse(url).query)
    validade = parametros.get("X-Amz-Expires") or parametros.get("Expires")
    assert validade is not None
    if "X-Amz-Expires" in parametros:
        assert validade == ["3600"]


def test_apagar_tira_do_r2_e_do_banco(sessao_limpa, duas_lojas, r2):
    a, _ = duas_lojas
    m = mandar(sessao_limpa, a, r2)
    apagar(sessao_limpa, m.id, a.id, ERI, r2)
    assert r2.listar(pasta_da_loja(a.id)) == []
    assert listar_midias(sessao_limpa, a.id) == []
    assert listar_eventos(sessao_limpa, a.id)[-1].acao == "midia_apagada"


def test_apagar_pasta_inteira(sessao_limpa, duas_lojas, r2):
    a, b = duas_lojas
    for _ in range(3):
        mandar(sessao_limpa, a, r2)
    mandar(sessao_limpa, b, r2)
    assert r2.apagar_pasta(pasta_da_loja(a.id)) == 3
    assert r2.listar(pasta_da_loja(a.id)) == []
    assert len(r2.listar(pasta_da_loja(b.id))) == 1  # a outra loja intacta
    assert r2.apagar_pasta(pasta_da_loja(a.id)) == 0


@pytest.mark.parametrize(
    ("extra", "trecho"),
    [
        ({"tipo": "virus"}, "tipo de mídia"),
        ({"content_type": "application/x-msdownload"}, "não aceito"),
        ({"content_type": "text/html"}, "não aceito"),
        ({"conteudo": b""}, "vazio"),
        ({"origem": "x"}, "origem"),
    ],
)
def test_envio_invalido(sessao_limpa, duas_lojas, r2, extra, trecho):
    a, _ = duas_lojas
    with pytest.raises(DadosInvalidos, match=trecho):
        mandar(sessao_limpa, a, r2, **extra)
    assert r2.listar("lojas/") == []  # nada foi parar no R2


def test_arquivo_grande_demais(sessao_limpa, duas_lojas, r2, monkeypatch):
    a, _ = duas_lojas
    monkeypatch.setattr(mod, "TAMANHO_MAXIMO", 10)
    with pytest.raises(DadosInvalidos, match="200 MB"):
        mandar(sessao_limpa, a, r2, conteudo=b"x" * 11)


def test_loja_inexistente(sessao_limpa, r2):
    from app.nucleo.modelos import Loja

    with pytest.raises(NaoEncontrado):
        mandar(sessao_limpa, Loja(id=999_999), r2)


def test_saude_do_r2(r2):
    assert r2.ok() is True and r2.diagnostico() == "ok"
    outro = Armazenamento(r2.cliente, "nao-existe")
    assert outro.ok() is False and outro.diagnostico() == "NoSuchBucket"


def test_cliente_real_exige_configuracao(monkeypatch):
    from app.config import obter_config

    obter_config.cache_clear()
    with pytest.raises(RuntimeError, match="R2 não configurado"):
        mod.cliente_r2()

    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "segredo")
    obter_config.cache_clear()
    try:
        cliente = mod.cliente_r2()
        assert cliente.meta.endpoint_url == "https://abc123.r2.cloudflarestorage.com"
        assert "segredo" not in repr(obter_config())  # a chave não aparece em log
    finally:
        monkeypatch.delenv("R2_ACCOUNT_ID")
        monkeypatch.delenv("R2_ACCESS_KEY_ID")
        monkeypatch.delenv("R2_SECRET_ACCESS_KEY")
        obter_config.cache_clear()


def test_saude_mostra_r2_quando_configurado(r2, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import obter_config
    from app.main import criar_app

    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "segredo")
    obter_config.cache_clear()
    monkeypatch.setattr(mod, "armazenamento_midias", lambda: r2)
    try:
        assert TestClient(criar_app()).get("/saude").json()["componentes"]["r2"] == "ok"
        monkeypatch.setattr(mod, "armazenamento_midias", lambda: Armazenamento(r2.cliente, "x"))
        r = TestClient(criar_app()).get("/saude")
        # R2 fora não derruba o servidor: mostra degradado, mas responde 200.
        assert r.status_code == 200 and r.json()["componentes"]["r2"] == "fora"
        assert r.json()["status"] == "degradado"
    finally:
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(k)
        obter_config.cache_clear()


def test_roteiro_do_teste_no_ar(r2, monkeypatch):
    """O mesmo roteiro que o Eri vai rodar no Shell do Render, aqui com o R2 simulado."""
    from app.ferramentas import teste_r2

    monkeypatch.setattr(mod, "armazenamento_midias", lambda: r2)
    monkeypatch.setattr(teste_r2, "armazenamento_midias", lambda: r2)
    for nome in ("enviar", "ler", "link_temporario", "apagar"):
        original = getattr(mod, nome)
        monkeypatch.setattr(
            teste_r2, nome, lambda *a, _o=original, **k: _o(*a, **k, armazenamento=r2)
        )
    monkeypatch.setattr(
        teste_r2.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(teste_r2.PNG)
    )
    assert teste_r2.main() == 0


def test_saude_nao_quebra_com_configuracao_errada(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import obter_config
    from app.main import criar_app

    monkeypatch.setenv("R2_ACCOUNT_ID", "https://colado-errado")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "segredo")
    obter_config.cache_clear()
    mod.armazenamento_midias.cache_clear()

    def quebra():
        raise ValueError("endpoint inválido")

    monkeypatch.setattr(mod, "armazenamento_midias", quebra)
    try:
        r = TestClient(criar_app()).get("/saude")
        assert r.status_code == 200 and r.json()["componentes"]["r2"] == "fora"
    finally:
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(k)
        obter_config.cache_clear()


def test_chaves_do_r2_coladas_com_enter_sao_limpas(monkeypatch):
    from app.config import Config

    monkeypatch.setenv("R2_ACCOUNT_ID", " conta\n")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "chave\n")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "segredo \r\n")
    c = Config(_env_file=None)
    assert c.r2_account_id == "conta"
    assert c.r2_access_key_id == "chave"
    assert c.r2_secret_access_key.get_secret_value() == "segredo"


def test_diagnostico_sem_resposta_do_servidor_nao_quebra():
    from app.nucleo.midia import Armazenamento

    class ClienteQuebrado:
        def head_object(self, **_):
            raise ValueError("cabeçalho inválido")

    assert Armazenamento(ClienteQuebrado(), "b").diagnostico() == "ValueError"
