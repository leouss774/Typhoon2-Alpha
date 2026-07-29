from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent.parent  # Typhoon2-Alpha/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bdnb_base_url: str = "https://api.bdnb.io"
    georisques_base_url: str = "https://www.georisques.gouv.fr/api/v1"
    georisques_v2_enabled: bool = False
    georisques_v2_base_url: str = "https://www.georisques.gouv.fr/api/v2"
    georisques_v2_token: str | None = None
    wfs_base_url: str = "https://data.geopf.fr/wfs/ows"
    geocoding_url: str = "https://data.geopf.fr/geocodage/search"
    open_meteo_climate_url: str = "https://climate-api.open-meteo.com/v1/climate"

    mistral_api_key: str | None = None
    mistral_enabled: bool = False

    zone_max_concurrency: int = 8
    zone_max_buildings_per_job: int = 60
    http_timeout_seconds: float = 15.0


settings = Settings()
