"""
Configuration centrale de l'orchestrateur.

Toutes les URLs de base et cles sont lues depuis les variables
d'environnement (voir .env.example). Rien n'est code en dur dans les
connecteurs : ce fichier est le seul endroit a modifier si une URL change.

Les chemins de cache/lookup (Copernicus, DVF) sont ancres sur l'emplacement
du projet (BASE_DIR), pas sur le repertoire courant : ils pointent donc
toujours vers backend/data/... quel que soit l'endroit d'ou la commande est
lancee. Comme ce projet vit sous D:\\Talan\\Typhoon-2, ces telechargements
se font sous D:, pas sous C:. Voir docs/GUIDE_ORCHESTRATEUR_API.md, section
"Espace disque" si vous voulez aussi deplacer le venv Python et le cache
pip sous D: (ce sont eux qui consomment le plus d'espace sur C: sinon).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # BDNB (aucune cle necessaire, confirme par un test reel - voir le guide)
    bdnb_api_key: str | None = None
    bdnb_base_url: str = "https://api.bdnb.io"

    # Georisques v1 (public, sans cle)
    georisques_base_url: str = "https://www.georisques.gouv.fr/api/v1"

    # Geocodage (BAN / Geoplateforme IGN, public, sans cle)
    geocoding_url: str = "https://data.geopf.fr/geocodage/search"

    # IGN Altimetrie (Geoplateforme, public, sans cle)
    ign_altitude_base_url: str = "https://data.geopf.fr/altimetrie/1.0"

    # Open-Meteo Climate API (public, sans cle en usage non-commercial)
    open_meteo_climate_url: str = "https://climate-api.open-meteo.com/v1/climate"

    # Copernicus Climate Data Store (compte + jeton requis, voir le guide
    # et le docstring de app/connectors/copernicus.py). Desactive par defaut
    # car le premier lancement declenche un telechargement multi-gigaoctets.
    # --- CHANGEZ ICI --- passez a True pour activer Copernicus dans le workflow.
    # Vous pouvez aussi le definir via COPERNICUS_ENABLED=true dans .env.
    copernicus_enabled: bool = False
    copernicus_cache_dir: str = str(BASE_DIR / "data" / "lookup" / "copernicus")

    # Lookup local DVF - meme logique de chemin absolu.
    dvf_lookup_dir: str = str(BASE_DIR / "data" / "lookup" / "dvf")

    # Mistral (agent recommandations — RAG travaux, cf.
    # app/recommandations/ et backend/recommendation_travaux-main/)
    mistral_api_key: str | None = None

    # Divers
    http_timeout_seconds: float = 15.0


settings = Settings()
