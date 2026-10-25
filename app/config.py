"""Configuração lida das variáveis de ambiente.

Segredos (chaves de API, senha do banco) NUNCA ficam no código: no Railway eles
são variáveis do serviço; no computador, um arquivo .env que não vai para o Git.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ambiente: str = "local"  # local | teste | producao
    versao: str = "0.1.0"
    database_url: str = "postgresql+psycopg://localhost:5432/world_estudio"

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
