"""
Configuration de l'agent recommandations (copie/adaptee de
recommendation_travaux/config.py — cf. PROMPT_INTEGRATION_ouss.md).

Chemins ancres sur l'emplacement de ce package (pas sur le repertoire
courant), meme logique que app/core/config.py pour le reste du backend :
la commande peut etre lancee depuis n'importe ou, `data/referentiel.json`
et `data/index.json` restent trouves.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Charge le .env racine du projet en priorite, puis backend/.env en repli
# (load_dotenv n'ecrase pas les variables deja definies : l'ordre fait la
# precedence). Certains postes ne renseignent que backend/.env — sans ce
# repli, /diagnostic/recommandations repond 502 "MISTRAL_API_KEY manquant"
# alors que la cle existe.
ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "backend" / ".env")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

CHAT_MODEL = "mistral-large-latest"
EMBED_MODEL = "mistral-embed"

# backend/app/recommandations/config.py -> backend/app/recommandations/
PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
REFERENTIEL_PATH = DATA_DIR / "referentiel.json"
INDEX_PATH = DATA_DIR / "index.json"

CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500

TOP_K = 6  # nombre de fiches recuperees par requete RAG

# Timeout HTTP par requete Mistral, en millisecondes.
REQUEST_TIMEOUT_MS = 300_000  # 5 minutes
