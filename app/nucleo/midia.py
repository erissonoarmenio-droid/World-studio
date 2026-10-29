"""Fotos, vídeos e áudios no Cloudflare R2 (tarefa 11).

- Bucket privado, uma pasta por loja: lojas/<loja_id>/<tipo>/<id aleatório>.<ext>.
- Nada público: para mostrar ou enviar, um link temporário de 1 hora.
- Toda leitura confere o dono: uma loja nunca lê mídia de outra.
- Só tipos de arquivo esperados (imagem, vídeo, áudio) e até 200 MB.
"""

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import obter_config
from app.nucleo.erros import DadosInvalidos, NaoEncontrado
from app.nucleo.eventos import Autor, registrar_evento
from app.nucleo.lojas import obter_loja
from app.nucleo.modelos import Midia
from app.nucleo.modelos.cadastro import TIPOS_MIDIA

TIPOS_ARQUIVO = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
}
TAMANHO_MAXIMO = 200 * 1024 * 1024
VALIDADE_LINK = 3600  # 1 hora


@dataclass
class Armazenamento:
    """Um bucket do R2. Nos testes, o cliente aponta para o R2 simulado (moto)."""

    cliente: Any
    bucket: str

    def guardar(self, chave: str, conteudo: bytes, content_type: str) -> None:
        self.cliente.put_object(
            Bucket=self.bucket, Key=chave, Body=conteudo, ContentType=content_type
        )

    def ler(self, chave: str) -> bytes:
        return self.cliente.get_object(Bucket=self.bucket, Key=chave)["Body"].read()

    def apagar(self, chave: str) -> None:
        self.cliente.delete_object(Bucket=self.bucket, Key=chave)

    def link(self, chave: str, segundos: int = VALIDADE_LINK) -> str:
        return self.cliente.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": chave}, ExpiresIn=segundos
        )

    def apagar_pasta(self, prefixo: str) -> int:
        """Apaga tudo que começa com o prefixo. Devolve quantos arquivos apagou."""
        total = 0
        paginas = self.cliente.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefixo
        )
        for pagina in paginas:
            chaves = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
            if chaves:
                self.cliente.delete_objects(Bucket=self.bucket, Delete={"Objects": chaves})
                total += len(chaves)
        return total

    def listar(self, prefixo: str) -> list[str]:
        paginas = self.cliente.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefixo
        )
        return [o["Key"] for p in paginas for o in p.get("Contents", [])]

    def diagnostico(self) -> str:
        """'ok' ou o código do erro (sem segredos). Lista no máximo 1 arquivo: confere a
        chave E que o bucket existe (um HEAD de arquivo responde 404 nos dois casos), sem
        precisar de permissão de operações de bucket."""
        try:
            self.cliente.list_objects_v2(Bucket=self.bucket, MaxKeys=1)
            return "ok"
        except Exception as erro:
            resposta = getattr(erro, "response", None) or {}
            codigo = str(resposta.get("Error", {}).get("Code", ""))
            return codigo or type(erro).__name__

    def ok(self) -> bool:
        """Teste rápido para o /saude. Nunca deixa o erro vazar."""
        return self.diagnostico() == "ok"


def cliente_r2() -> Any:
    config = obter_config()
    if not config.r2_configurado:
        raise RuntimeError("R2 não configurado (faltam as variáveis R2_* no Render)")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=config.r2_access_key_id,
        aws_secret_access_key=config.r2_secret_access_key.get_secret_value(),  # type: ignore[union-attr]
        region_name="auto",
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
    )


@lru_cache
def armazenamento_midias() -> Armazenamento:
    return Armazenamento(cliente_r2(), obter_config().r2_bucket_midias)


def pasta_da_loja(loja_id: int) -> str:
    return f"lojas/{loja_id}/"


def enviar(
    sessao: Session,
    *,
    loja_id: int,
    conteudo: bytes,
    tipo: str,
    content_type: str,
    origem: str,
    autor: Autor,
    armazenamento: Armazenamento | None = None,
) -> Midia:
    if tipo not in TIPOS_MIDIA:
        raise DadosInvalidos(f"tipo de mídia desconhecido: {tipo!r}")
    extensao = TIPOS_ARQUIVO.get(content_type)
    if extensao is None:
        raise DadosInvalidos("tipo de arquivo não aceito (só imagem, vídeo mp4 e áudio)")
    if not conteudo:
        raise DadosInvalidos("arquivo vazio")
    if len(conteudo) > TAMANHO_MAXIMO:
        raise DadosInvalidos("arquivo passa de 200 MB")
    if not 2 <= len(origem) <= 30:
        raise DadosInvalidos("origem inválida")
    obter_loja(sessao, loja_id)

    chave = f"{pasta_da_loja(loja_id)}{tipo}/{uuid.uuid4().hex}.{extensao}"
    (armazenamento or armazenamento_midias()).guardar(chave, conteudo, content_type)
    midia = Midia(
        loja_id=loja_id,
        chave=chave,
        tipo=tipo,
        content_type=content_type,
        tamanho=len(conteudo),
        origem=origem,
    )
    sessao.add(midia)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="midia_enviada",
        autor=autor,
        loja_id=loja_id,
        detalhes={"midia_id": midia.id, "tipo": tipo, "tamanho": len(conteudo)},
    )
    return midia


def obter_midia(sessao: Session, midia_id: int, loja_id: int) -> Midia:
    """Só devolve se a mídia for dessa loja. A outra loja recebe 'não encontrada'."""
    midia = sessao.get(Midia, midia_id)
    if midia is None or midia.loja_id != loja_id:
        raise NaoEncontrado("mídia não encontrada")
    return midia


def link_temporario(
    sessao: Session, midia_id: int, loja_id: int, armazenamento: Armazenamento | None = None
) -> str:
    midia = obter_midia(sessao, midia_id, loja_id)
    return (armazenamento or armazenamento_midias()).link(midia.chave)


def ler(
    sessao: Session, midia_id: int, loja_id: int, armazenamento: Armazenamento | None = None
) -> bytes:
    midia = obter_midia(sessao, midia_id, loja_id)
    return (armazenamento or armazenamento_midias()).ler(midia.chave)


def apagar(
    sessao: Session,
    midia_id: int,
    loja_id: int,
    autor: Autor,
    armazenamento: Armazenamento | None = None,
) -> None:
    midia = obter_midia(sessao, midia_id, loja_id)
    (armazenamento or armazenamento_midias()).apagar(midia.chave)
    sessao.delete(midia)
    sessao.flush()
    registrar_evento(
        sessao,
        acao="midia_apagada",
        autor=autor,
        loja_id=loja_id,
        detalhes={"midia_id": midia_id, "tipo": midia.tipo},
    )


def listar_midias(sessao: Session, loja_id: int) -> list[Midia]:
    return list(sessao.scalars(select(Midia).where(Midia.loja_id == loja_id).order_by(Midia.id)))
