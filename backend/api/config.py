"""
config.py
---------
Charge la configuration depuis les variables d'environnement / .env.
Aucune clé en dur dans le code : voir .env.example à la racine du projet.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mistral_api_key: str = ""
    mistral_api_url: str = "https://api.mistral.ai/v1/chat/completions"
    mistral_model: str = "mistral-large-latest"

    mistral_timeout_seconds: float = 30.0
    mistral_max_retries: int = 2  # nombre de tentatives de correction en cas de JSON invalide

    # Utile en dev/démo pour ne pas dépendre d'une clé API valide (voir mistral_client.py)
    use_mock_mistral: bool = False


settings = Settings()
