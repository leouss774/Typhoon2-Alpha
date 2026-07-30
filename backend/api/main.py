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
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from backend.services.pdf_generator import generate_bank_report_pdf
from backend.services import dvf_service
from backend.services.analyses_store import get_analysis, set_analysis
from pydantic import BaseModel

# Imports de l'orchestrateur
from backend.api.orchestrator import run_analysis

# Chat depuis le routeur legacy
from backend.app.api.routes.legacy import legacy_chat

logger = logging.getLogger(__name__)

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

        # Stockage partagé (accessible par le chat)
        set_analysis(session_id, result)

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


@app.post("/api/bank/analyze")
async def lancer_analyse_banque(req: AnalyseRequest):
    """Route dédiée aux acteurs bancaires — version ASYNC.
    
    Lance l'analyse en arrière-plan et retourne immédiatement.
    Le Dashboard frontend fait du polling via GET /api/analysis/{session_id}
    jusqu'à ce que le statut passe à "completed".
    """
    session_id = req.session_id or f"bank-session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form

    if not form_data.get("adresse"):
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    # 1. Stocker immédiatement un statut "processing"
    set_analysis(session_id, {"status": "processing", "session_id": session_id})

    # 2. Lancer l'analyse en arrière-plan (ne pas attendre)
    async def background_task():
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(run_analysis, form_data=form_data, session_id=session_id),
                timeout=120.0
            )
            result["status"] = "completed"
            set_analysis(session_id, result)
        except asyncio.TimeoutError:
            set_analysis(session_id, {
                "status": "error",
                "session_id": session_id,
                "error": "L'analyse a dépassé le temps limite (120s).",
            })
        except Exception as e:
            logger.exception("Erreur analyse bancaire")
            set_analysis(session_id, {
                "status": "error",
                "session_id": session_id,
                "error": f"Erreur lors de l'analyse : {str(e)}",
            })

    asyncio.create_task(background_task())

    # 3. Retourner immédiatement (l'analyse tourne en tâche de fond)
    return {
        "status": "ok",
        "session_id": session_id,
        "status_analysis": "processing",
    }


@app.get("/api/analysis/{session_id}")
async def get_analysis_endpoint(session_id: str):
    """Récupère une analyse existante par son ID de session.
    
    Retours possibles :
    - {"status": "processing"}              → analyse en cours
    - {"status": "error", "error": "..."}  → erreur
    - {données complètes + "status": "completed"} → terminé
    """
    analysis = get_analysis(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    
    # Si l'analyse est encore en cours ou en erreur, retourner tel quel
    if analysis.get("status") in ("processing", "error"):
        return analysis
    
    # Analyse terminée : retourner les données complètes
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


@app.get("/api/bank/report/{session_id}/pdf")
async def download_report_pdf(session_id: str):
    """Génère et télécharge le rapport d'analyse complet au format PDF.
    Utilise reportlab pour un rendu professionnel avec tableaux et couleurs.
    """
    analysis = get_analysis(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    
    db = analysis.get("decision_bancaire", {}) or {}
    if not db:
        raise HTTPException(status_code=404, detail="Décision bancaire introuvable")
    
    # Enrichir avec les données de marché DVF
    stats_marche = None
    try:
        adr = analysis.get("adresse", "")
        evo = dvf_service.get_price_evolution(adr)
        current = dvf_service.query_market_value(adr)
        if evo.get("evolution"):
            stats_marche = {
                "prix_m2_actuel": current.get("prix_m2_median"),
                "prix_m2_commune": evo["evolution"][-1]["prix_m2_median"] if evo["evolution"] else None,
                "nb_transactions": current.get("nb_transactions", 0),
                "tendance": evo.get("tendance", "stable"),
            }
    except Exception as e:
        logger.warning(f"Impossible de récupérer les stats marché pour le PDF : {e}")

    pdf_buffer = generate_bank_report_pdf(
        session_id=session_id,
        adresse=analysis.get("adresse", "N/A"),
        decision_bancaire=db,
        stats_marche=stats_marche,
    )
    
    return StreamingResponse(
        content=pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=rapport-credit-{session_id}.pdf",
            "Content-Type": "application/pdf",
        }
    )


class MarketTrendsRequest(BaseModel):
    """Requête pour obtenir l'évolution des prix DVF pour une adresse."""
    adresse: str
    type_bien: str = "Maison"
    surface: float = 100


@app.post("/api/bank/market-trends")
async def get_market_trends(req: MarketTrendsRequest):
    """Retourne l'évolution du prix au m² + comparaison de marché (données DVF réelles)."""
    evolution = dvf_service.get_price_evolution(req.adresse, req.type_bien)
    current = dvf_service.query_market_value(req.adresse, req.surface, req.type_bien)
    
    # Données de comparaison : tous types confondus dans la commune
    try:
        all_types = dvf_service.get_price_evolution(req.adresse, "Maison")
        if all_types.get("evolution") and len(all_types["evolution"]) > 0:
            annee_courante = all_types["evolution"][-1]
            prix_m2_commune_tous = annee_courante["prix_m2_median"]
            tx_total = sum(d["nb_transactions"] for d in all_types["evolution"])
        else:
            prix_m2_commune_tous = None
            tx_total = 0
        
        # Écart entre le type du bien et la moyenne commune
        pm2_bien = current.get("prix_m2_median")
        ecart_pct = None
        if pm2_bien and prix_m2_commune_tous and prix_m2_commune_tous > 0:
            ecart_pct = round((pm2_bien - prix_m2_commune_tous) / prix_m2_commune_tous * 100, 1)
    except Exception:
        prix_m2_commune_tous = None
        tx_total = 0
        ecart_pct = None
    
    return {
        "evolution": evolution.get("evolution", []),
        "source": evolution.get("source", ""),
        "tendance": evolution.get("tendance", "stable"),
        "valeur_actuelle": current.get("valeur_estimee"),
        "prix_m2_bien": current.get("prix_m2_median"),
        "prix_m2_commune": prix_m2_commune_tous,
        "ecart_vs_commune_pct": ecart_pct,
        "nb_transactions": current.get("nb_transactions", 0),
        "volume_total_transactions": tx_total,
        "indice_confiance_dvf": current.get("indice_confiance", 0),
    }


class PdfReportRequest(BaseModel):
    """Requête pour générer un PDF à partir des données d'analyse fournies par le client.
    
    Alternative au endpoint GET /api/bank/report/{session_id}/pdf qui nécessite
    que l'analyse soit stockée côté serveur (perdue si le backend redémarre).
    """
    session_id: str
    adresse: str = ""
    decision_bancaire: dict[str, Any]


@app.post("/api/bank/report/pdf")
async def generate_report_pdf_post(req: PdfReportRequest):
    """Génère et télécharge le rapport PDF à partir des données fournies directement.
    
    Version POST : plus robuste car elle ne dépend pas du stockage serveur.
    Le frontend envoie les données d'analyse récupérées depuis le sessionStorage.
    """
    db = req.decision_bancaire or {}
    if not db:
        raise HTTPException(status_code=400, detail="Données d'analyse manquantes")
    
    stats_marche = None
    try:
        adr = req.adresse or ""
        evo = dvf_service.get_price_evolution(adr)
        current = dvf_service.query_market_value(adr)
        if evo.get("evolution"):
            stats_marche = {
                "prix_m2_actuel": current.get("prix_m2_median"),
                "prix_m2_commune": evo["evolution"][-1]["prix_m2_median"] if evo["evolution"] else None,
                "nb_transactions": current.get("nb_transactions", 0),
                "tendance": evo.get("tendance", "stable"),
            }
    except Exception as e:
        logger.warning(f"Impossible de récupérer les stats marché pour le PDF : {e}")

    pdf_buffer = generate_bank_report_pdf(
        session_id=req.session_id,
        adresse=req.adresse or "N/A",
        decision_bancaire=db,
        stats_marche=stats_marche,
    )
    
    return StreamingResponse(
        content=pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=rapport-credit-{req.session_id}.pdf",
            "Content-Type": "application/pdf",
        }
    )


# ─── Route Chat ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    historique: list[dict] = []


@app.post("/api/chat/{session_id}")
async def chat_endpoint(session_id: str, req: ChatRequest):
    """Route de chat — utilise le handler legacy enrichi."""
    return await legacy_chat(session_id, req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
