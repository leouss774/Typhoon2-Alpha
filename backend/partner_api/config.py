"""
Configuration de la Typhoon Partner API. Fichier separe de
`app.core.config` (celui-ci reste dedie au backend interne) meme si les
deux lisent le meme `.env` a la racine de `backend/` : les cles listees
ici (PARTNER_API_KEYS) n'ont de sens que pour ce service.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/partner_api/config.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent


class PartnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # Cles API partenaires, format "nom1:cle1,nom2:cle2,...". Une entree
    # par groupe/projet consommateur : permet de savoir qui appelle (logs)
    # et de revoquer une cle individuellement (retirer son entree, pas
    # besoin de regenerer les autres).
    partner_api_keys: str = ""


partner_settings = PartnerSettings()
