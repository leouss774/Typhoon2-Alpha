"""Configuration de l'application via Pydantic Settings.

Les variables sont chargées depuis l'environnement
ou le fichier .env à la racine du projet.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration centralisée de l'application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    ENVIRONMENT: str = "development"

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./data/vectordb"
    CHROMA_COLLECTION_NAME: str = "recommandations_travaux"

    # DRIAS
    DRIAS_DATA_PATH: str = "./data/raw/drias"

    # Sécurité
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"
    BDNB_API_KEY: str = ""

    # Feature flags
    USE_MOCK_LLM: bool = True  # True = réponses simulées sans vraie API
    
    # Mistral
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_API_URL: str = "https://api.mistral.ai/v1/chat/completions"
    MISTRAL_TIMEOUT_SECONDS: int = 3
    MISTRAL_MAX_RETRIES: int = 0
    USE_MOCK_MISTRAL: bool = True


@lru_cache()
def get_settings() -> Settings:
    """Retourne l'instance unique des settings (cachée)."""
    return Settings()
