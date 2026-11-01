"""Configuração lida das variáveis de ambiente.

Segredos (chaves de API, senha do banco) NUNCA ficam no código: no Render eles
são variáveis do serviço; no computador, um arquivo .env que não vai para o Git.
"""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ambiente: str = "local"  # local | teste | producao
    versao: str = "0.1.1"
    database_url: str = "postgresql+psycopg://localhost:5432/world_estudio"
    trabalhador_ativo: bool = True  # o trabalhador da fila roda dentro do servidor

    # Cloudflare R2 (fotos, vídeos e backup). Vazio = desligado (ex.: nos testes).
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket_midias: str = "world-studio-midias"
    r2_bucket_backup: str = "world-studio-backup"
    pg_dump: str = "pg_dump"  # no Docker: o pg_dump 16 (mesma versão do banco)
    backup_ativo: bool = True  # o backup diário roda junto com o servidor

    # Fornecedores de geração (nós). Vazio = desligado; os testes usam fornecedor simulado.
    google_api_key: SecretStr | None = None  # foto (Nano Banana), voz (TTS) e juiz
    atlas_api_key: SecretStr | None = None  # vídeo (Seedance) e lipsync
    decart_api_key: SecretStr | None = None  # vestir a peça no vídeo (reserva)
    anthropic_api_key: SecretStr | None = None  # diretor (conversa → roteiro do vídeo)

    @property
    def r2_configurado(self) -> bool:
        return bool(self.r2_account_id and self.r2_access_key_id and self.r2_secret_access_key)

    @field_validator(
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        "r2_bucket_midias",
        "r2_bucket_backup",
        "google_api_key",
        "atlas_api_key",
        "decart_api_key",
        "anthropic_api_key",
        mode="before",
    )
    @classmethod
    def tirar_espacos(cls, valor: object) -> object:
        """Ao colar uma chave no painel, vem junto um Enter ou espaço; isso quebra a chamada."""
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("database_url")
    @classmethod
    def usar_driver_psycopg(cls, valor: str) -> str:
        """O provedor entrega 'postgres://' ou 'postgresql://'; o SQLAlchemy precisa do driver."""
        for prefixo in ("postgres://", "postgresql://"):
            if valor.startswith(prefixo):
                return "postgresql+psycopg://" + valor[len(prefixo) :]
        return valor


@lru_cache
def obter_config() -> Config:
    return Config()
