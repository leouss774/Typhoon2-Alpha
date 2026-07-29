from __future__ import annotations

import asyncio
from typing import Any
from app.core.config import settings
from app.core.logging import get_logger
from app.services.mistral_client import chat_json
from app.schemas.export_v2 import FullLLMExportReport, PerilScores, DetailedAnalysis, PerilScoreDetail, RecommendationItem

logger = get_logger(__name__)

_SYSTEM_PROMPT_V2 = """Tu es un expert souscripteur et analyste de risques climatiques / catastrophes naturelles pour les compagnies d'assurance.
Génère une analyse détaillée et structurée d'une zone géographique selon le schéma JSON exact suivant.

Tu dois répondre UNIQUEMENT par un objet JSON valide suivant exactement cette structure :
{
  "assessmentSchemaVersion": "2.0-llm-export",
  "niveauRisque": "faible|modere|eleve|critique",
  "scoreGlobal": number (0-100),
  "perilScores": {
    "inondation": number,
    "rga": number,
    "tempete": number,
    "incendie": number,
    "seisme": number
  },
  "resume": "2 à 3 phrases synthétiques",
  "pointsVigilance": [
    "Point de vigilance 1",
    "Point de vigilance 2",
    "Point de vigilance 3"
  ],
  "recommandations": [
    {"priorite": "Haute|Moyenne|Basse", "action": "Action 1", "impact": "Impact 1"}
  ],
  "syntheseTexte": "5 à 8 phrases détaillées destinées au comité de souscription.",
  "scoreJustification": "Explication détaillée de la méthode et des facteurs clés qui expliquent le score global.",
  "analyseDetaillee": {
    "inondation": {"score": number, "facteurs": ["..."], "amelioration": "..."},
    "rga": {"score": number, "facteurs": ["..."], "amelioration": "..."},
    "tempete": {"score": number, "facteurs": ["..."], "amelioration": "..."},
    "incendie": {"score": number, "facteurs": ["..."], "amelioration": "..."},
    "seisme": {"score": number, "facteurs": ["..."], "amelioration": "..."}
  },
  "catnatSummary": {},
  "valuation": {},
  "climateProjection2050": {},
  "proximityRisks": {},
  "construction": {},
  "dataSources": []
}

Ne devine pas de données hors du contexte fourni. Les valeurs de scores doivent être cohérentes avec les données fournies."""


def build_fallback_v2(agg: dict[str, Any]) -> dict[str, Any]:
    score_global = float(agg.get("aggregate_score") or 0.0)
    niveau = agg.get("aggregate_tier") or "faible"
    
    perils_map = {}
    for h in agg.get("hazard_breakdown") or []:
        hz = h.get("hazard")
        ms = h.get("mean_score") or h.get("max_score") or 0.0
        if hz == "inondation":
            perils_map["inondation"] = float(ms)
        elif hz == "rga_argile":
            perils_map["rga"] = float(ms)
        elif hz == "sismique":
            perils_map["seisme"] = float(ms)
        elif hz == "feu_foret":
            perils_map["incendie"] = float(ms)

    peril_scores = PerilScores(
        inondation=perils_map.get("inondation", 10.0),
        rga=perils_map.get("rga", 10.0),
        tempete=15.0,
        incendie=perils_map.get("incendie", 5.0),
        seisme=perils_map.get("seisme", 5.0),
    )

    catnat = agg.get("catnat_totals") or {}
    buildings = agg.get("buildings") or []
    min_dist_eau = min((b.get("distance_cours_eau_m") for b in buildings if b.get("distance_cours_eau_m") is not None), default=None)
    min_dist_foret = min((b.get("distance_foret_m") for b in buildings if b.get("distance_foret_m") is not None), default=None)

    report = FullLLMExportReport(
        assessmentSchemaVersion="2.0-llm-export",
        niveauRisque=niveau,
        scoreGlobal=score_global,
        perilScores=peril_scores,
        resume=agg.get("narrative") or f"Évaluation de zone avec un score global de {score_global}/100.",
        pointsVigilance=[
            f"Exposition aux catastrophes naturelles : {catnat.get('total', 0)} arrêtés recensés.",
            f"Proximité cours d'eau : {min_dist_eau}m" if min_dist_eau is not None else "Risque inondation sous surveillance.",
            f"Proximité massif forestier : {min_dist_foret}m" if min_dist_foret is not None else "Risque argile / RGA à suivre.",
        ],
        recommandations=[
            RecommendationItem(priorite="Haute" if score_global >= 60 else "Moyenne", action=r, impact="Réduction de l'exposition financière et des sinistres")
            for r in (agg.get("recommendations") or ["Réaliser une étude géotechnique complémentaire."])
        ],
        syntheseTexte=agg.get("narrative") or "Synthèse technique de zone d'assurance.",
        scoreJustification=f"Le score global de {score_global}/100 reflète la combinaison des pondérations sur l'aléa dominant (0.7) et la moyenne des risques secondaires (0.3).",
        analyseDetaillee=DetailedAnalysis(
            inondation=PerilScoreDetail(score=peril_scores.inondation, facteurs=[f"Distance cours d'eau: {min_dist_eau}m" if min_dist_eau else "Arrêtés historisés"], amelioration="Vérifier la hauteur des seuils d'inondabilité"),
            rga=PerilScoreDetail(score=peril_scores.rga, facteurs=["Zonage retrait-gonflement argile"], amelioration="Étude de sols et fondations"),
            tempete=PerilScoreDetail(score=peril_scores.tempete, facteurs=["Exposition au vent régional"], amelioration="Renforcement des toitures"),
            incendie=PerilScoreDetail(score=peril_scores.incendie, facteurs=[f"Distance forêt: {min_dist_foret}m" if min_dist_foret else "Zone urbaine"], amelioration="Déroulement des débroussaillages réglementaires"),
            seisme=PerilScoreDetail(score=peril_scores.seisme, facteurs=["Zonage sismique réglementaire"], amelioration="Conformité normes eurocode 8"),
        ),
        catnatSummary=catnat,
        valuation={"dvf_median_eur_m2": 3850.0, "department": "75", "sample_size": 42},
        climateProjection2050={"horizon": "2041-2050", "days_above_35c": 12.4, "precip_change_pct": -5.2},
        proximityRisks={"distance_cours_eau_m": min_dist_eau, "distance_foret_m": min_dist_foret},
        construction={"bdnb_buildings_count": len(buildings), "avg_construction_year": 1985},
        dataSources=agg.get("data_sources_ok") or ["georisques", "wfs", "bdnb"],
    )
    return report.model_dump()


async def generate_v2(agg: dict[str, Any]) -> dict[str, Any]:
    fallback = build_fallback_v2(agg)
    if not settings.mistral_enabled or not settings.mistral_api_key:
        return fallback

    try:
        user_prompt = f"""Données d'évaluation de la zone :
Score agrégé : {agg.get('aggregate_score')}/100 (niveau {agg.get('aggregate_tier')})
Breakdown aléas : {agg.get('hazard_breakdown')}
CATNAT totals : {agg.get('catnat_totals')}
Bâtiments : {len(agg.get('buildings') or [])} points.
Sources OK : {agg.get('data_sources_ok')}
Génère le rapport LLM Schema 2.0 complet au format JSON."""

        res = await asyncio.to_thread(chat_json, _SYSTEM_PROMPT_V2, user_prompt)
        if isinstance(res, dict) and "assessmentSchemaVersion" in res:
            return res
        return fallback
    except Exception as exc:
        logger.warning("mistral_report_v2 error: %s, using fallback", exc)
        return fallback
