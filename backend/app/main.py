"""
API FastAPI — Zone Risk Assessment pour Promoteurs Immobiliers (Person 1).

Endpoints :
  POST /api/v1/zone/assess    — évalue une zone complète
  GET  /api/v1/health         — vérification de santé
"""

from __future__ import annotations

import time
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.collector_agent import collect
from app.scoring.zone_scoring import run_zone_risk_assessment, rating_zone_to_dict
from app.scoring.promoteur_report import generer_rapport_promoteur
from app.schemas.zone_assessment import (
    ZoneAssessmentRequest,
    ZoneAssessmentResponse,
    PromoteurReportSchema,
)

app = FastAPI(
    title="Typhoon — API Promoteurs Immobiliers",
    description="Évaluation du risque climatique pour une zone (parcelle, commune, IRIS).",
    version="0.1.0",
)

# CORS pour le frontend standalone (MapLibre)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "typhoon-zone", "version": "0.1.0"}


@app.post("/api/v1/zone/assess", response_model=ZoneAssessmentResponse)
async def assess_zone(req: ZoneAssessmentRequest) -> ZoneAssessmentResponse:
    """Évalue une zone complète (échantillonnage multi-points + agrégation).

    La zone est définie par ses limites rectangulaires (bounds). Une grille
    hexagonale de points est générée, chacun est évalué individuellement, et
    les résultats sont agrégés en distributions par péril.
    """
    bounds = (req.zone.lat_min, req.zone.lon_min, req.zone.lat_max, req.zone.lon_max)

    t0 = time.time()
    try:
        rating = await run_zone_risk_assessment(
            bounds=bounds,
            spacing_km=req.spacing_km,
            max_points=req.max_points,
            max_concurrency=req.max_concurrency,
            land_only=req.land_only,
            collect_fn=collect,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Zone assessment failed",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        )

    duree = round(time.time() - t0, 1)
    data = rating_zone_to_dict(rating)
    nb_points = data["nb_points"]

    if nb_points == 0:
        return ZoneAssessmentResponse(
            status="error",
            zone=req.zone,
            nb_points=0,
            score_moyen=0.0,
            score_pondere=0.0,
            rating_global="Non évaluable",
            land_only=req.land_only,
            perils={},
            duree_evaluation_s=duree,
            message="Aucun point d'échantillonnage valide dans cette zone.",
        )

    perils_dist = {}
    for nom, p in data["perils"].items():
        perils_dist[nom] = p  # Pydantic validera via PerilDistribution

    # Person 3 — Rapport promoteur
    rapport = generer_rapport_promoteur(
        score_moyen=data["score_moyen"],
        rating_global=data["rating_global"],
        perils=rating.perils,  # on passe les vrais objets DistributionPeril
        land_only=data["land_only"],
        worst_case_peril=data["worst_case_peril"],
        worst_case_score=data["worst_case_score"],
        nb_points_valides=data["nb_points_valides"],
        nb_points_erreur=data["nb_points_erreur"],
    )

    return ZoneAssessmentResponse(
        status="ok",
        zone=req.zone,
        nb_points=nb_points,
        nb_points_valides=data["nb_points_valides"],
        nb_points_erreur=data["nb_points_erreur"],
        score_moyen=data["score_moyen"],
        score_pondere=data["score_pondere"],
        rating_global=data["rating_global"],
        land_only=data["land_only"],
        worst_case_peril=data["worst_case_peril"],
        worst_case_score=data["worst_case_score"],
        perils=perils_dist,
        duree_evaluation_s=duree,
        points_echantillon=data["points_echantillon"] if req.include_samples else None,
        rapport_promoteur=PromoteurReportSchema(**rapport.to_dict()),
    )
