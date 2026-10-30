"""Atlas Cloud: vídeo (Seedance 2.0) e lipsync. Nunca foto (E15).

POST /api/v1/model/generateVideo → data.id; GET /api/v1/model/prediction/{id};
POST /api/v1/model/uploadMedia (multipart `file`) → URL para usar como referência.
Atenção (29/10): o Cloudflare da Atlas recusou o cliente Python padrão (erro 1010) e aceitou
curl. Conferir com httpx no teste real da Parada B antes de ligar na fila.
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from app.geracao.fornecedores.base import TEMPO_LIMITE, ErroFornecedor, Resposta, chamar
from app.geracao.nos.base import Pedido

BASE = "https://api.atlascloud.ai/api/v1/model"
ROTA = {"video": "generateVideo", "lipsync": "generateVideo", "voz": "generateAudio"}
PRONTO = {"completed", "succeeded"}
FALHOU = {"failed", "error", "canceled", "cancelled"}


class Atlas:
    nome = "atlas"

    def __init__(self, chave: SecretStr, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente or httpx.Client(timeout=TEMPO_LIMITE)
        self._cabecalho = {"Authorization": f"Bearer {chave.get_secret_value()}"}

    def enviar(self, pedido: Pedido) -> Resposta:
        if pedido.no not in ROTA:
            raise ValueError(f"a Atlas não faz o nó {pedido.no}")
        r = chamar(
            self._cliente,
            "POST",
            f"{BASE}/{ROTA[pedido.no]}",
            json=pedido.payload,
            headers=self._cabecalho,
        )
        dados = r.json().get("data") or {}
        if not dados.get("id"):
            raise ErroFornecedor("a Atlas respondeu sem id", status=r.status_code, incerto=True)
        return self._resposta(dados)

    def consultar(self, id_trabalho: str) -> Resposta:
        r = chamar(
            self._cliente, "GET", f"{BASE}/prediction/{id_trabalho}", headers=self._cabecalho
        )
        return self._resposta(r.json().get("data") or {})

    def subir_midia(self, conteudo: bytes, nome_arquivo: str, tipo: str) -> str:
        """Sobe imagem/áudio para usar como referência (o lipsync não aceita data URI)."""
        r = chamar(
            self._cliente,
            "POST",
            f"{BASE}/uploadMedia",
            files={"file": (nome_arquivo, conteudo, tipo)},
            headers=self._cabecalho,
        )
        dados = r.json().get("data") or {}
        url = dados.get("download_url") or dados.get("url")
        if not url:
            raise ErroFornecedor("upload sem URL na resposta", incerto=False)
        return url

    @staticmethod
    def _resposta(dados: dict) -> Resposta:
        status = str(dados.get("status", "")).lower()
        estado = "pronto" if status in PRONTO else "falhou" if status in FALHOU else "na_fila"
        return Resposta(
            estado=estado,
            id=dados.get("id"),
            saidas=list(dados.get("outputs") or []),
            erro=str(dados.get("error") or ""),
        )
