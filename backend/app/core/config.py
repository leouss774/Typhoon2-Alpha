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
    # env_file ancre sur BASE_DIR (et non sur le repertoire courant) : le
    # .env est trouve que uvicorn soit lance depuis backend/ ou depuis la
    # racine du depot, comme pour les chemins de cache/lookup ci-dessous.
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

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
    copernicus_enabled: bool = True
    copernicus_cache_dir: str = str(BASE_DIR / "data" / "lookup" / "copernicus")

    # Lookup local DVF - meme logique de chemin absolu. Les CSV par
    # departement (voir backend/data/lookup/dvf/README.md) ne sont pas
    # versionnes dans le repo et pesent lourd : chaque poste doit les
    # telecharger localement. Ce flag permet de desactiver DVF en un
    # instant sur un poste qui ne les a pas encore (evite de voir
    # "dvf_local" en erreur sur chaque diagnostic), sans toucher au code.
    # --- CHANGEZ ICI --- passez a False si les CSV ne sont pas presents
    # sur ce poste. Vous pouvez aussi le definir via DVF_ENABLED=false
    # dans .env (pratique pour ne pas modifier ce fichier vous-meme et
    # eviter les allers-retours si plusieurs personnes partagent le repo).
    dvf_enabled: bool = False
    dvf_lookup_dir: str = str(BASE_DIR / "data" / "lookup" / "dvf")

    # Mistral (agent recommandations — RAG travaux, cf.
    # app/recommandations/ et backend/recommendation_travaux-main/)
    mistral_api_key: str | None = None

    # Annonces immobilieres "en vente" (carte zone, marqueurs colores par
    # score climatique - cf. app/connectors/annonces_lookup.py). Pas d'API
    # publique GRATUITE fiable pour ca (SeLoger/LeBonCoin n'en proposent
    # pas) : les wrappers RapidAPI testes ("Annonces Immobilieres France",
    # "leboncoin1") sont payants a l'appel des le 1er call, meme avec une
    # cle valide - un essai reel a facture 0,40e sans avertissement prealable.
    #
    # DISABLE PAR DEFAUT (securite anti-facturation) : meme si une cle/host
    # trainent dans .env, aucun appel RapidAPI n'est fait tant que ce flag
    # n'est pas explicitement mis a True. Sans RapidAPI, la carte retombe
    # uniquement sur DVF (gratuit, officiel, mais ventes deja realisees -
    # pas des annonces actuellement en ligne) : liste vide sinon, jamais de
    # nouvel appel facturable silencieux.
    # --- CHANGEZ ICI --- ANNONCES_RAPIDAPI_ENABLED=true dans .env UNIQUEMENT
    # si vous acceptez consciemment le cout par appel de votre wrapper.
    annonces_rapidapi_enabled: bool = False
    annonces_rapidapi_key: str | None = None
    annonces_rapidapi_host: str | None = None
    # Path + nom du parametre de recherche : varie selon le wrapper RapidAPI
    # souscrit (ex. "Annonces Immobilieres France" utilise un code postal,
    # d'autres wrappers Leboncoin/SeLoger utilisent une recherche libre par
    # ville/mots-cles). A ajuster une fois le vrai endpoint de recherche
    # identifie (pas "/health", qui n'est qu'un endpoint de statut) - voir
    # app/connectors/annonces_lookup.py::_call_rapidapi.
    annonces_rapidapi_search_path: str = "/v2/leboncoin/search"
    annonces_rapidapi_search_param: str = "query"

    # Divers
    http_timeout_seconds: float = 15.0


settings = Settings()
