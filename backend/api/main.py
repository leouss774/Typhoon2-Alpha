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
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# Imports de l'orchestrateur
from backend.api.orchestrator import run_analysis

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
    analyses_store[session_id] = {"status": "processing", "session_id": session_id}

    # 2. Lancer l'analyse en arrière-plan (ne pas attendre)
    async def background_task():
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(run_analysis, form_data=form_data, session_id=session_id),
                timeout=120.0
            )
            result["status"] = "completed"
            analyses_store[session_id] = result
        except asyncio.TimeoutError:
            analyses_store[session_id] = {
                "status": "error",
                "session_id": session_id,
                "error": "L'analyse a dépassé le temps limite (120s).",
            }
        except Exception as e:
            logger.exception("Erreur analyse bancaire")
            analyses_store[session_id] = {
                "status": "error",
                "session_id": session_id,
                "error": f"Erreur lors de l'analyse : {str(e)}",
            }

    asyncio.create_task(background_task())

    # 3. Retourner immédiatement (l'analyse tourne en tâche de fond)
    return {
        "status": "ok",
        "session_id": session_id,
        "status_analysis": "processing",
    }


@app.get("/api/analysis/{session_id}")
async def get_analysis(session_id: str):
    """Récupère une analyse existante par son ID de session.
    
    Retours possibles :
    - {"status": "processing"}              → analyse en cours
    - {"status": "error", "error": "..."}  → erreur
    - {données complètes + "status": "completed"} → terminé
    """
    analysis = analyses_store.get(session_id)
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
    
    Pour l'instant, retourne un rapport texte formaté.
    En production, utiliser reportlab, weasyprint ou un template HTML → PDF.
    """
    analysis = analyses_store.get(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    
    db = analysis.get("decision_bancaire", {}) or {}
    if not db:
        raise HTTPException(status_code=404, detail="Décision bancaire introuvable")
    
    # Construction du rapport texte (sera remplacé par un vrai PDF)
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("  RAPPORT D'ANALYSE DE RISQUE CRÉDIT")
    report_lines.append("  Outil d'aide à la décision — Aucune décision automatique")
    report_lines.append("=" * 60)
    report_lines.append(f"")
    report_lines.append(f"Bien : {analysis.get('adresse', 'N/A')}")
    report_lines.append(f"Session : {session_id}")
    report_lines.append(f"Date : {analysis.get('date_analyse', 'N/A')}")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("📊 SCORE DE RISQUE DU BIEN")
    report_lines.append("─" * 60)
    report_lines.append(f"  Score risque bancaire : {db.get('score_risque_bancaire', 'N/A')}/100")
    report_lines.append(f"  Score climatique : {db.get('score_climatique', 'N/A')}/100")
    report_lines.append(f"  Niveau de risque : {db.get('niveau_risque_global', 'N/A')}")
    report_lines.append(f"  Impact ESG : {db.get('impact_esg', 'N/A')}")
    report_lines.append(f"  Indice de confiance : {db.get('indice_confiance', 'N/A')}%")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("⚠️ PRINCIPAUX RISQUES IDENTIFIÉS")
    report_lines.append("─" * 60)
    for r in (db.get("risques_identifies") or []):
        report_lines.append(f"  • {r.get('nom')}: {r.get('score')}/100 — {r.get('zone_impactee')}")
        if r.get('description'):
            report_lines.append(f"    {r['description'][:120]}")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("💰 ÉVALUATION FINANCIÈRE")
    report_lines.append("─" * 60)
    report_lines.append(f"  Valeur de marché : {db.get('valeur_marche', 'N/A')} €")
    report_lines.append(f"  Décote appliquée : {db.get('decote_pct', 0)}%")
    report_lines.append(f"  Valeur ajustée : {db.get('valeur_ajustee', 'N/A')} €")
    report_lines.append(f"  Taux proposé : {db.get('taux_propose', 'N/A')}%")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("🛡️ GARANTIES D'ASSURANCE RECOMMANDÉES")
    report_lines.append("─" * 60)
    for g in (db.get("garanties_assurance") or []):
        report_lines.append(f"  {'🔴' if g.get('obligatoire') else '🟡'} {g.get('type')}")
        if g.get('detail'):
            report_lines.append(f"     {g['detail'][:100]}")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("🏗️ RECOMMANDATIONS DE PRÉVENTION")
    report_lines.append("─" * 60)
    for p in (db.get("prevention_recommandations") or [])[:5]:
        report_lines.append(f"  #{p.get('priorite')} [{p.get('zone')}] {p.get('travaux')}")
        report_lines.append(f"     Coût: {p.get('cout_estime')} | Gain: +{p.get('gain_resilience')}%")
    report_lines.append(f"")
    report_lines.append("─" * 60)
    report_lines.append("📄 RAPPORT SYNTHÉTIQUE")
    report_lines.append("─" * 60)
    rapport = db.get("rapport_synthetique", "")
    for line in rapport.split("\n"):
        report_lines.append(f"  {line}")
    report_lines.append(f"")
    report_lines.append("=" * 60)
    report_lines.append("  Document généré automatiquement — Outil d'aide à la décision")
    report_lines.append("  Aucune décision d'acceptation ou de refus n'est contenue dans ce rapport.")
    report_lines.append("=" * 60)
    
    report_text = "\n".join(report_lines)
    
    return PlainTextResponse(
        content=report_text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=rapport-credit-{session_id}.txt"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
