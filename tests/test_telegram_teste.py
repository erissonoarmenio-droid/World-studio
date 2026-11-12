# ruff: noqa: E501, S311
"""Ferramenta da loja de teste do Eri pelo @DesfilaBot (06/11): Telegram simulado."""

import random

import pytest
from sqlalchemy import select

from app.creditos import servico as creditos
from app.ferramentas import telegram_teste as tt
from app.geracao import executores
from app.nucleo.db import sessao
from app.nucleo.modelos import Trabalho
from tests.test_executores import ambiente, limpar_trabalhos_rodando  # noqa: F401


class TelegramFalso:
    def __init__(self, eri: int, estranho: int) -> None:
        self.updates = [
            {"update_id": 10, "message": {"from": {"id": eri}, "photo": [{"file_id": "p1a"}, {"file_id": "p1"}]}},
            {"update_id": 11, "message": {"from": {"id": estranho}, "photo": [{"file_id": "x"}]}},
            {"update_id": 12, "message": {"from": {"id": eri}, "document": {"file_id": "p2", "mime_type": "image/jpeg"}, "caption": "sorrindo"}},
            {"update_id": 13, "message": {"from": {"id": eri}, "photo": [{"file_id": "p3"}]}},
            {"update_id": 14, "message": {"from": {"id": eri}, "voice": {"file_id": "v1"}}},
            {"update_id": 15, "message": {"from": {"id": eri}, "document": {"file_id": "a1", "mime_type": "audio/x-m4a"}}},
            {"update_id": 16, "message": {"from": {"id": eri}, "text": "oi"}},
        ]  # fmt: skip
        self.offset = None
        self.pedidos_arquivo: list[str] = []

    def chamar(self, metodo, params=None):
        params = params or {}
        if metodo == "getUpdates":
            if "offset" in params:
                self.offset = params["offset"]
                self.updates = [u for u in self.updates if u["update_id"] >= params["offset"]]
            return list(self.updates)
        if metodo == "getFile":
            self.pedidos_arquivo.append(params["file_id"])
            return {"file_path": f"arquivos/{params['file_id']}"}
        raise AssertionError(metodo)

    @staticmethod
    def baixar(caminho):
        return b"\x89PNG\r\n\x1a\n" + caminho.encode()


@pytest.fixture
def ids():
    return random.randint(10**8, 10**9), random.randint(10**9, 2 * 10**9)


def test_listar_so_le(ids):
    t = TelegramFalso(*ids)
    linhas = tt.listar(t.chamar)
    assert len(linhas) == 7 and t.offset is None and t.pedidos_arquivo == []


def test_importar_so_do_eri_cria_loja_uma_vez_e_marca_lido(ambiente, ids):  # noqa: F811
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    assert r["loja_criada_agora"] is True
    assert [tipo for _, tipo, _ in r["midias"]] == ["influencer"] * 3 + ["voz"] * 2
    assert r["ignoradas"] == 2  # o estranho e o texto
    assert "x" not in t.pedidos_arquivo and "p1" in t.pedidos_arquivo  # maior tamanho
    assert t.offset == 17 and t.updates == []

    de_novo = tt.importar(eri, t.chamar, t.baixar)
    assert de_novo["loja_criada_agora"] is False and de_novo["loja_id"] == r["loja_id"]
    with sessao() as s:
        assert creditos.saldo(s, r["loja_id"]).disponivel == 75  # plano liberado uma vez só


def test_pedido_da_influencer_gera_homem_com_as_fotos(ambiente, ids):  # noqa: F811
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    p = tt.pedir_influencer(
        eri,
        fotos[:2],
        27,
        "black rectangular eyeglasses",
        "plain white tee",
        aparencia="a wide, softly rounded face with full cheeks and short dark stubble beard",
        corpo_midia=fotos[2],
        close=True,
    )
    assert p["criado_agora"] is True
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        assert (
            trabalho.dados["genero"] == "homem" and trabalho.dados["fotos_midia_ids"] == fotos[:2]
        )
        assert (
            trabalho.dados["enquadramento"] == "close"
            and trabalho.dados["corpo_midia_id"] == fotos[2]
        )
        trabalho.estado = "rodando"  # o que o trabalhador faria ao pegar
        s.flush()
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and resultado.dados["modo"] == "da_pessoa"


def test_menos_de_3_fotos_nao_pede(ids):
    with pytest.raises(SystemExit):
        tt.pedir_influencer(ids[0], [1], 27, None, "plain white tee")


def test_pedido_de_foto_com_a_peca(ambiente, ids):  # noqa: F811
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    entrada = {
        "genero": "homem",
        "idade": 26,
        "tracos": "a wide, softly rounded face with full cheeks",
        "corpo": "slim, tall build",
        "peca": "He wears a grey chambray short-sleeve shirt with an embroidered band.",
        "cenario": "a small menswear boutique",
        "cena": "SCENE: standing by the rack, relaxed.",
    }
    p = tt.pedir_foto(eri, fotos[0], fotos[1:3], entrada)
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 2 and len(resultado.dados["midias"]) == 2


def test_foto_com_trava_do_rosto_faz_2_passadas_por_opcao(ambiente, ids):  # noqa: F811
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    entrada = {
        "genero": "homem",
        "idade": 26,
        "tracos": "a wide, softly rounded face with full cheeks and a broad, rounded jaw",
        "corpo": "tall build",
        "peca": "He wears a grey chambray short-sleeve shirt with an embroidered band.",
        "cenario": "a small menswear boutique",
        "cena": "SCENE: standing by the rack, relaxed.",
    }
    p = tt.pedir_foto(eri, fotos[0], fotos[1:2], entrada, rostos=fotos[1:3], oculos="black")
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 4  # 2 cenas + 2 travas
    assert len(resultado.dados["midias"]) == 2 and len(resultado.dados["antes_da_trava"]) == 2


def test_trava_avulsa_numa_foto_pronta(ambiente, ids):  # noqa: F811
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    p = tt.travar_rosto(
        eri, fotos[0], fotos[1:3], "a wide, softly rounded face with full cheeks and wide jaw"
    )
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and resultado.dados["no"] == "rosto_fixo"


def test_juiz_de_rosto_marca_a_foto_reprovada(ambiente, ids, monkeypatch):  # noqa: F811
    from app.geracao.fornecedores.base import Resposta

    class JuizFalso:
        def enviar(self, pedido):
            texto = '{"reconheceria": 6, "largura_rosto": "mais_fino", "comprimento_rosto": "igual", "cabeca_vs_corpo": "igual", "tom_pele": "igual", "olhos": "igual", "nariz": "igual", "boca": "igual", "cabelo": "igual", "idade_ref": 26, "idade_foto": 26, "diferencas": ["rosto mais fino"]}'
            return Resposta(estado="pronto", saidas=[{"text": texto}])

    monkeypatch.setattr(executores, "JUIZ_DIRETO", JuizFalso)
    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    p = tt.travar_rosto(
        eri, fotos[0], fotos[1:3], "a wide, softly rounded face with full cheeks and wide jaw"
    )
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
    juiz = executores.executar_tipo_foto(trabalho).dados["juiz_rosto"][0]
    assert juiz["julgado"] and not juiz["aprovado"] and "rosto: mais fino" in juiz["motivos"]


def test_segunda_pessoa_com_clone_proprio_pede_a_ficha_dela(ambiente, ids):  # noqa: F811
    from app.nucleo.consentimentos import consentimento_ativo

    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    fotos = [i for i, tipo, _ in r["midias"] if tipo == "influencer"]
    ela = tt.nova_pessoa(eri, "Teste Mulher", "autorizou por meio do Eri em 07/11")
    with sessao() as s:
        assert consentimento_ativo(s, ela["pessoa_id"], "clone") is not None
    p = tt.pedir_influencer(
        eri,
        fotos[:2],
        42,
        None,
        "a plain white crew-neck t-shirt",
        aparencia="an oval face with straight dark eyebrows and long straight hair with highlights",
        close=True,
        pessoa_id=ela["pessoa_id"],
        genero="mulher",
    )
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        assert (
            trabalho.dados["pessoa_id"] == ela["pessoa_id"] and trabalho.dados["genero"] == "mulher"
        )
        trabalho.estado = "rodando"
        s.flush()
        s.expunge(trabalho)
    resultado = executores.executar_tipo_foto(trabalho)
    assert ambiente.envios == 1 and "juiz_rosto" in resultado.dados


def test_dirigir_mostra_falas_e_video_pede_480_com_o_roteiro(ambiente, ids):  # noqa: F811
    from tests.geracao.test_diretor_ugc import BOM

    class Falso:
        def json(self, sistema, texto, imagens=None):
            assert imagens and imagens[0][1] == "image/png"
            return BOM

    eri, estranho = ids
    t = TelegramFalso(eri, estranho)
    r = tt.importar(eri, t.chamar, t.baixar)
    quadro = [i for i, tipo, _ in r["midias"] if tipo == "influencer"][0]
    d = tt.dirigir(eri, quadro, "mostra a camisa", "camisa terracota", "mulher", cerebro=Falso())
    assert [v["angulo"] for v in d["videos"]] == ["problema_solucao", "prova_pessoal"]
    assert d["videos"][0]["falas"][0]["fala"] == "Gente, olha isso, chegou hoje."
    assert "imagem_url" not in d["videos"][0]["entrada"]
    p = tt.gerar_video(eri, quadro, d["videos"][1]["entrada"])
    with sessao() as s:
        trabalho = s.scalar(select(Trabalho).where(Trabalho.chave_unica == p["chave"]))
        assert trabalho.tipo == "video" and trabalho.dados["item"] == "video_480"
        assert trabalho.dados["entradas"][0]["planos"][2]["fala"] == "Me chama no direct, tá?"


def test_texto_do_terminal_base64_preserva_acento():
    """E51: o Shell do Render apaga acentos; base64 passa só letras simples."""
    import base64

    from app.ferramentas.telegram_teste import texto_do_terminal

    original = "Algodão leve e a manga para no meio do braço"
    codificado = "b64:" + base64.b64encode(original.encode()).decode()
    assert texto_do_terminal(codificado) == original


def test_texto_do_terminal_recusa_texto_sem_acento():
    import pytest

    from app.ferramentas.telegram_teste import texto_do_terminal

    with pytest.raises(SystemExit):
        texto_do_terminal("Algodo leve, veste reto no ombro e a manga para no meio do brao")
    assert texto_do_terminal("camisa preta") == "camisa preta"  # curto passa
