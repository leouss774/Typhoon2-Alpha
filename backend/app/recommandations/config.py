"""
Configuration de l'agent recommandations (RAG), embarqué dans le backend Typhoon.

Contrairement au config.py d'origine (recommendation_travaux-main), les chemins ne
sont pas relatifs au repertoire courant : ils sont ancres sur l'emplacement de ce
module (meme logique que backend/app/core/config.py), pour que l'agent fonctionne
quel que soit l'endroit d'ou le process est lance (CLI, uvicorn, tests...).

La cle Mistral est lue depuis l'environnement / le .env du backend (voir
backend/.env.example) - pas besoin d'un .env separe dans ce sous-dossier.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/recommandations/config.py -> backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(_BACKEND_DIR / ".env")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

CHAT_MODEL = "mistral-large-latest"
EMBED_MODEL = "mistral-embed"

DATA_DIR = Path(__file__).resolve().parent / "data"
REFERENTIEL_PATH = str(DATA_DIR / "referentiel.json")
INDEX_PATH = str(DATA_DIR / "index.json")
SOURCES_REGISTRY_PATH = str(DATA_DIR / "sources_registry.csv")

CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500

TOP_K = 6

REQUEST_TIMEOUT_MS = 300_000
THROTTLE_SECONDS = 3
PROGRESS_PATH = str(DATA_DIR / "progress.json")
