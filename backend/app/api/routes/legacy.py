"""Routes de compatibilité (legacy) — pont entre l'ancienne API frontend
et la nouvelle API backend basée sur Typhoon2-Alpha.

Ces routes permettent au frontend React existant de fonctionner
sans changement avec la nouvelle architecture.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.graph import diagnostic_graph
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Stockage temporaire pour les analyses
analyses_store: dict[str, dict] = {}


class LegacyAnalyzeRequest(BaseModel):
    session_id: str | None = None
    client_form: dict
    raw_data: dict = {}


# ─── Routes d'analyse ──────────────────────────────────────────────

@router.post("/analyze")
async def legacy_analyze(req: LegacyAnalyzeRequest):
    """Route legacy : POST /api/analyze → nouveau diagnostic"""
    session_id = req.session_id or f"session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form
    adresse = form_data.get("adresse", "")

    if not adresse:
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    try:
        final_state = await diagnostic_graph.ainvoke(
            {"adresse": adresse, "formulaire": form_data, "copernicus": False},
            config={"configurable": {"thread_id": session_id}},
        )

        analysis = _build_legacy_response(final_state, session_id, adresse, form_data)
        analyses_store[session_id] = analysis

        return {"status": "ok", "session_id": session_id, "analysis": analysis}

    except Exception as e:
        logger.exception("Erreur legacy analyze")
        analysis = _build_fallback(session_id, adresse, str(e))
        analyses_store[session_id] = analysis
        return {"status": "ok", "session_id": session_id, "analysis": analysis}


@router.post("/bank/analyze")
async def legacy_bank_analyze(req: LegacyAnalyzeRequest):
    """Route legacy : POST /api/bank/analyze (async avec polling)"""
    session_id = req.session_id or f"bank-session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form
    adresse = form_data.get("adresse", "")

    if not adresse:
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    analyses_store[session_id] = {"status": "processing", "session_id": session_id}

    import asyncio

    async def background_task():
        try:
            final_state = await diagnostic_graph.ainvoke(
                {"adresse": adresse, "formulaire": form_data, "copernicus": False},
                config={"configurable": {"thread_id": session_id}},
            )
            analysis = _build_legacy_response(final_state, session_id, adresse, form_data)
            analysis["status"] = "completed"
            analyses_store[session_id] = analysis
        except Exception as e:
            analyses_store[session_id] = {"status": "error", "session_id": session_id, "error": str(e)}

    asyncio.create_task(background_task())

    return {"status": "ok", "session_id": session_id, "status_analysis": "processing"}


@router.get("/analysis/{session_id}")
async def legacy_get_analysis(session_id: str):
    """Route legacy : GET /api/analysis/{session_id} (polling)"""
    analysis = analyses_store.get(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return analysis


# ─── Route Dashboard (données simulées pour l'UI) ─────────────────

@router.get("/dashboard/{session_id}")
async def legacy_dashboard(session_id: str):
    """Dashboard legacy - retourne les données du diagnostic stocké ou des données neutres"""
    analysis = analyses_store.get(session_id)
    if analysis and analysis.get("status") == "completed":
        return _dashboard_from_analysis(analysis)
    # Données neutres si pas d'analyse complète
    return {
        "session_id": session_id,
        "score_global": 0,
        "niveau_risque": "non_evalue",
        "adresse": "Analyse en cours...",
        "coordonnees": {"lat": 0, "lng": 0},
        "scores_par_alea": {},
        "risques_dominants": [],
        "projections_2050": {},
        "recommandations": [],
        "synthese": "Analyse en cours de traitement...",
    }


# ─── Route Recommandations ─────────────────────────────────────────

@router.get("/recommendations/{session_id}")
async def legacy_recommendations(session_id: str):
    analysis = analyses_store.get(session_id)
    if not analysis or analysis.get("status") != "completed":
        return {"session_id": session_id, "recommandations": []}
    zones = analysis.get("recommandations", {}).get("zones", {})
    recos = []
    count = 0
    for zone_name, zone in zones.items():
        for r in zone.get("recommandations", []):
            count += 1
            recos.append({
                "priorite": count,
                "titre": r.get("travaux", r.get("mesure", f"Travaux {zone_name}")),
                "description": r.get("explication", r.get("justification", "")),
                "cout_estime_bas": _parse_cost(r.get("cout_estime", "0")),
                "cout_estime_haut": _parse_cost(r.get("cout_estime", "0")) * 2,
                "gain_resilience_pct": r.get("gain_resilience", 0),
                "aleas_adresses": [zone.get("alea_principal", "")],
            })
    return {
        "session_id": session_id,
        "recommandations": recos,
        "cout_total_bas": sum(r["cout_estime_bas"] for r in recos),
        "cout_total_haut": sum(r["cout_estime_haut"] for r in recos),
        "gain_moyen": round(sum(r["gain_resilience_pct"] for r in recos) / max(len(recos), 1), 1),
    }


# ─── Route Chat ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    historique: list[dict] = []


@router.post("/chat/{session_id}")
async def legacy_chat(session_id: str, req: ChatRequest):
    """Chat legacy - réponse simple basée sur le contexte"""
    analysis = analyses_store.get(session_id, {})
    score = analysis.get("resume", {}).get("score_global", "?")
    adresse = analysis.get("adresse", "votre bien")

    # Réponse contextuelle simple (sans appeler LLM)
    question_lower = req.question.lower()
    if "score" in question_lower or "risque" in question_lower:
        reponse = f"Le score de risque global pour {adresse} est de {score}/100. "
        if isinstance(score, (int, float)) and score > 50:
            reponse += "C'est un niveau significatif qui mérite des travaux de mitigation."
        else:
            reponse += "C'est un niveau modéré qui reste gérable avec un entretien régulier."
    elif "cout" in question_lower or "coût" in question_lower or "prix" in question_lower or "travaux" in question_lower:
        reponse = f"Le coût total estimé des travaux pour {adresse} est détaillé dans la section 'Synthèse de la Rénovation' du dashboard. Les aides mobilisables (MaPrimeRénov', Anah, Fonds Barnier) peuvent réduire significativement votre reste à charge."
    elif "priorit" in question_lower:
        reponse = "Les zones les plus prioritaires sont celles avec le score de risque le plus élevé. Consultez le jumeau numérique 3D pour identifier visuellement les zones critiques (en rouge/orange)."
    elif "2050" in question_lower or "projection" in question_lower or "futur" in question_lower:
        reponse = f"La projection 2050 montre une aggravation des risques climatiques pour {adresse}. Les travaux réalisés aujourd'hui vous protègeront mieux demain. Le bouton '2050' dans le jumeau 3D permet de visualiser l'évolution."
    else:
        reponse = f"Pour {adresse} (score global: {score}/100), je vous recommande de consulter le jumeau numérique 3D et la liste des recommandations. Puis-je vous aider sur un aspect spécifique ?"

    return {"reponse": reponse, "session_id": session_id}


# ─── Route Test de vulnérabilité ───────────────────────────────────

class VulnTestRequest(BaseModel):
    zone_name: str
    lat: float | None = None
    lon: float | None = None
    zone_data: dict = {}


@router.post("/jumeau/vulnerability-test")
async def legacy_vuln_test(req: VulnTestRequest):
    """Test de vulnérabilité rapide pour une zone."""
    score = req.zone_data.get("risque", 50)
    niveau = req.zone_data.get("niveau", "modere")

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
        "scenario": f"Zone {req.zone_name} — niveau {niveau} ({score}/100)",
        "resume": f"Analyse rapide de la zone '{req.zone_name}'. Score de risque : {score}/100. {action}.",
        "score_avant": score,
        "score_apres_travaux": max(0, score - 20),
        "points_de_vigilance": [
            f"Le niveau actuel de la zone {req.zone_name} est jugé {niveau}",
            "Une étude plus approfondie est recommandée",
        ],
    }


# ─── Helpers ───────────────────────────────────────────────────────

def _build_legacy_response(final_state: dict, session_id: str, adresse: str, form_data: dict) -> dict:
    dt = final_state.get("digital_twin", {})
    bank = final_state.get("bank_decision", {})
    rs = final_state.get("risk_scores", {})
    bg = final_state.get("building_data", {})
    zones = dt.get("zones", {})
    proj = dt.get("projection_2050", {})
    score = dt.get("score_global", 0)
    niveau = "critique" if score >= 70 else "eleve" if score >= 55 else "modere" if score >= 35 else "faible"
    nb_recos = sum(len(z.get("recommandations", [])) for z in zones.values())

    return {
        "session_id": session_id,
        "adresse": adresse,
        "status": "completed",
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "coordonnees": {"latitude": bg.get("adresse", {}).get("lat", 0), "longitude": bg.get("adresse", {}).get("lon", 0)},
        "formulaire_client": {
            "adresse": form_data.get("adresse", ""),
            "type_bien": form_data.get("type_bien", ""),
            "surface": form_data.get("surface", 0),
            "nb_etages": form_data.get("nb_etages", 1),
            "annee_construction": form_data.get("annee_construction", 2000),
            "type_structure": form_data.get("type_structure", ""),
            "type_toiture": form_data.get("type_toiture", ""),
            "presence_sous_sol": form_data.get("presence_sous_sol", False),
            "presence_cave": form_data.get("presence_cave", False),
        },
        "analyse_risques": {
            "score": {"global": score, "weights": {}, "perils": {}},
            "scores_par_alea": _extract_alea_scores(zones),
            "profil_bien": {"disponible": True},
        },
        "recommandations": {
            "zones": zones,
            "projection_2050": proj,
            "synthese_financiere": {"cout_brut_total": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
            "nb_recommandations": nb_recos,
        },
        "decision_bancaire": bank,
        "resume": {
            "score_global": score,
            "niveau_risque": niveau,
            "nb_recommandations": nb_recos,
            "cout_total_travaux": "0 EUR",
            "aides_mobilisables": "0 EUR",
            "reste_a_charge_net": "0 EUR",
        },
        "donnees_api": {"code_insee": bg.get("adresse", {}).get("citycode", ""), "georisques": bg.get("georisques", {})},
        "_performance": {"mode": "typhoon_v2"},
    }


def _extract_alea_scores(zones: dict) -> dict:
    mapping = {"inondation": "sous_sol", "rga": "fondations", "tempete": "murs_nord", "incendie": "toiture"}
    scores = {}
    for alea, zone in mapping.items():
        z = zones.get(zone, {})
        scores[alea] = {"score": z.get("risque", 0), "niveau": z.get("niveau", "faible"), "label": z.get("alea_principal", alea)}
    return scores


def _parse_cost(cost_str: str) -> int:
    try:
        return int("".join(c for c in cost_str if c.isdigit()))
    except (ValueError, TypeError):
        return 0


def _build_fallback(session_id: str, adresse: str, error: str) -> dict:
    return {
        "session_id": session_id,
        "adresse": adresse,
        "status": "completed",
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "coordonnees": {"latitude": 0, "longitude": 0},
        "formulaire_client": {"adresse": adresse},
        "analyse_risques": {"score": {"global": 0}, "scores_par_alea": {}, "profil_bien": {"disponible": False}},
        "recommandations": {"zones": {}, "projection_2050": {}, "synthese_financiere": {}, "nb_recommandations": 0},
        "decision_bancaire": {},
        "resume": {"score_global": 0, "niveau_risque": "non_evalue", "nb_recommandations": 0, "cout_total_travaux": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
        "donnees_api": {"code_insee": ""},
        "erreur": error,
    }


def _dashboard_from_analysis(analysis: dict) -> dict:
    zone_scores = analysis.get("analyse_risques", {}).get("scores_par_alea", {})
    return {
        "session_id": analysis.get("session_id", ""),
        "score_global": analysis.get("resume", {}).get("score_global", 0),
        "niveau_risque": analysis.get("resume", {}).get("niveau_risque", "non_evalue"),
        "adresse": analysis.get("adresse", ""),
        "coordonnees": analysis.get("coordonnees", {"lat": 0, "lng": 0}),
        "scores_par_alea": zone_scores,
        "risques_dominants": sorted(zone_scores.keys(), key=lambda k: zone_scores[k]["score"], reverse=True)[:3],
        "projections_2050": {k: v.get("score", 0) for k, v in zone_scores.items()},
        "recommandations": analysis.get("recommandations", {}).get("zones", {}),
        "synthese": f"Diagnostic climatique terminé. Score global : {analysis.get('resume', {}).get('score_global', 0)}/100.",
    }
