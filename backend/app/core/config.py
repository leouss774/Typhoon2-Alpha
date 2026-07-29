"""Configuration centrale de l'orchestrateur Typhoon.

Toutes les URLs de base et clés sont lues depuis les variables
d'environnement (voir .env.example). Rien n'est codé en dur.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    environment: str = "development"

    # BDNB (aucune clé nécessaire)
    bdnb_api_key: str | None = None
    bdnb_base_url: str = "https://api.bdnb.io"

    # Georisques v1 (public, sans clé)
    georisques_base_url: str = "https://www.georisques.gouv.fr/api/v1"

    # Geocodage (BAN / Géoplateforme IGN, public, sans clé)
    geocoding_url: str = "https://data.geopf.fr/geocodage/search"

    # IGN Altimétrie (Géoplateforme, public, sans clé)
    ign_altitude_base_url: str = "https://data.geopf.fr/altimetrie/1.0"

    # Open-Meteo Climate API (public, sans clé en usage non-commercial)
    open_meteo_climate_url: str = "https://climate-api.open-meteo.com/v1/climate"

    # Copernicus
    copernicus_enabled: bool = True
    copernicus_cache_dir: str = str(BASE_DIR / "data" / "lookup" / "copernicus")

    # DVF
    dvf_enabled: bool = False
    dvf_lookup_dir: str = str(BASE_DIR / "data" / "lookup" / "dvf")

    # Mistral (recommandations)
    mistral_api_key: str | None = None
    mistral_api_url: str = "https://api.mistral.ai/v1/chat/completions"
    mistral_model: str = "mistral-large-latest"
    mistral_timeout_seconds: float = 30.0
    mistral_max_retries: int = 2
    use_mock_mistral: bool = False

    # Annonces immobilières
    annonces_rapidapi_enabled: bool = False
    annonces_rapidapi_key: str | None = None
    annonces_rapidapi_host: str | None = None
    annonces_rapidapi_search_path: str = "/v2/leboncoin/search"
    annonces_rapidapi_search_param: str = "query"

    # Anthropic (Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ChromaDB
    chroma_persist_dir: str = str(BASE_DIR / "data" / "vectordb")
    chroma_collection_name: str = "recommandations_travaux"

    # Sécurité
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"

    # Feature flags
    use_mock_llm: bool = True

    # Divers
    http_timeout_seconds: float = 15.0


settings = Settings()
