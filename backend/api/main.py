"""
API Typhoon — Serveur FastAPI principal.

Routes :
  POST   /api/analyze              → Lancer une analyse (formulaire → orchestre → recommandations)
  GET    /api/analysis/{id}        → Récupérer une analyse existante
  POST   /api/jumeau/vulnerability-test → Test de vulnérabilité rapide
  GET    /health                   → Health check

Lancement :
  uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Imports de l'orchestrateur
from api.orchestrator import run_analysis

app = FastAPI(
    title="Typhoon API — Analyse multi-agents de résilience climatique",
    version="1.0.0",
    description="API qui orchestre le formulaire client, le collecteur API et l'agent recommandation",
)

# CORS — autoriser le frontend (Vite sur localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage temporaire des analyses (en mémoire, à remplacer par une DB)
analyses_store: dict[str, dict[str, Any]] = {}


# ─── Schémas ──────────────────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    session_id: str | None = None
    client_form: dict[str, Any]
    raw_data: dict[str, Any] = {}


class VulnerabilityTestRequest(BaseModel):
    zone_name: str
    lat: float | None = None
    lon: float | None = None
    zone_data: dict[str, Any] = {}


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/analyze")
async def lancer_analyse(req: AnalyseRequest):
    """Route principale : reçoit le formulaire client, lance l'analyse et retourne le JSON final."""
    session_id = req.session_id or f"session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form

    # Vérification que l'adresse est présente
    if not form_data.get("adresse"):
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    try:
        # L'analyse peut prendre du temps (appels API multiples)
        # On utilise un timeout de 120s pour éviter les requêtes pendantes
        result = await asyncio.wait_for(
            asyncio.to_thread(run_analysis, form_data=form_data, session_id=session_id),
            timeout=120.0
        )

        # Stockage en mémoire
        analyses_store[session_id] = result

        return {
            "status": "ok",
            "session_id": session_id,
            "analysis": result,
        }

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="L'analyse a dépassé le temps limite (120s). Les données API peuvent être temporairement indisponibles.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de l'analyse : {str(e)}",
        )


@app.get("/api/analysis/{session_id}")
async def get_analysis(session_id: str):
    """Récupère une analyse existante par son ID de session."""
    analysis = analyses_store.get(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return analysis


@app.post("/api/jumeau/vulnerability-test")
async def test_vulnerabilite(req: VulnerabilityTestRequest):
    """Test de vulnérabilité rapide pour une zone cliquée sur le jumeau 3D."""
    zone_name = req.zone_name
    zone_data = req.zone_data

    # Génération d'un test de vulnérabilité simple
    score = zone_data.get("risque", 50)
    niveau = zone_data.get("niveau", "modere")

    if score >= 70:
        verdict = "DANGER"
        action = "Intervention urgente requise"
    elif score >= 55:
        verdict = "RISQUE_ELEVE"
        action = "Travaux de mitigation recommandés dans les 12 mois"
    elif score >= 35:
        verdict = "VIGILANCE"
        action = "Travaux de mitigation recommandés dans les 24 mois"
    else:
        verdict = "ACCEPTABLE"
        action = "Aucune action urgente, suivi périodique conseillé"

    return {
        "verdict": verdict,
        "score_risque": score,
        "scenario": f"Zone {zone_name} — niveau {niveau} ({score}/100)",
        "resume": f"Analyse rapide de la zone '{zone_name}'. Score de risque : {score}/100. {action}.",
        "score_avant": score,
        "score_apres_travaux": max(0, score - 20),
        "points_de_vigilance": [
            f"Le niveau actuel de la zone {zone_name} est jugé {niveau}",
            "Une étude plus approfondie est recommandée",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
