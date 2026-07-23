"""
Configuration du Digital Twin Agent.
Mettez votre clé API Mistral ici ou via variable d'environnement.
"""
import os

# ─── Clé API Mistral ───────────────────────────────────────────────────────────
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "PMFQZeDKuNsAyLvtkVvcCUoHTfuMkJdy")

# Modèles disponibles : mistral-large-latest, mistral-medium-latest, open-mixtral-8x7b
MISTRAL_MODEL_ANALYSE    = "mistral-large-latest"   # Analyse principale (puissant)
MISTRAL_MODEL_VULN       = "mistral-small-latest"   # Test vulnérabilité (rapide)
MISTRAL_MODEL_PROJECTION = "mistral-large-latest"   # Projection 2050

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# Températures
TEMPERATURE_ANALYSE    = 0.1   # Très déterministe pour le JSON
TEMPERATURE_VULN       = 0.2   # Un peu plus créatif pour l'explication
TEMPERATURE_PROJECTION = 0.1

# Timeouts (secondes)
TIMEOUT_ANALYSE    = 120
TIMEOUT_VULN       = 30
TIMEOUT_PROJECTION = 120
