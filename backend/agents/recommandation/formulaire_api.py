"""
API du formulaire de diagnostic habitation.
Indépendante de risk_score_pipeline.py : les résultats sont enregistrés
dans formulaire_habitation.json (et non dans risques_adresse.json).

Lancer avec :
    uvicorn formulaire_api:app --reload --port 8001
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from formulaire_models import DiagnosticHabitation

app = FastAPI(title="Formulaire diagnostic habitation")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
JSON_FILE = BASE_DIR / "formulaire_habitation.json"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def lire_donnees() -> list:
    if JSON_FILE.exists():
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def ecrire_donnees(donnees: list) -> None:
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)


@app.get("/formulaire")
async def afficher_formulaire():
    """Sert la page HTML du formulaire."""
    return FileResponse(STATIC_DIR / "formulaire.html")


@app.post("/api/formulaire")
async def soumettre_formulaire(payload: DiagnosticHabitation):
    """Reçoit les données du formulaire et les ajoute au fichier JSON."""
    donnees = lire_donnees()
    entree = payload.model_dump()
    entree["id"] = str(uuid.uuid4())
    entree["date_soumission"] = datetime.utcnow().isoformat()
    donnees.append(entree)
    ecrire_donnees(donnees)
    return {"status": "ok", "id": entree["id"]}


@app.get("/api/formulaire")
async def lister_formulaires():
    """Retourne toutes les réponses déjà enregistrées."""
    return lire_donnees()