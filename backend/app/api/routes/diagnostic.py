"""
POST /diagnostic — route commune aux 3 cas d'usage (cf. README racine,
section "Backend — communication inter-agents").

Instancie une execution du StateGraph (`graph.ainvoke`), avec un
`thread_id` unique par requete (cle de checkpoint). Retourne directement
`state.digital_twin`, le contrat pret pour la scene Three.js du front.

Chaque etape est logguee cote serveur (voir `app.core.logging`) : c'est la
"trace des agents" demandee — collecte, scoring, assemblage — visible dans
la console au fil de l'execution, pas seulement dans la reponse finale.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.graph import diagnostic_graph
from app.core.config import settings
from app.core.logging import get_logger
from app.scoring.zone_scoring import run_zone_risk_assessment, rating_zone_to_dict

logger = get_logger(__name__)
router = APIRouter()


class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complete du bien")
    formulaire: dict | None = Field(
        default=None,
        description="Champs geometry saisis explicitement (priorite sur l'inference BDNB) : "
        "has_basement, has_garage, garage_position, has_garden, garden_surface_m2, roof_shape...",
    )
    # La valeur par defaut est pilotee par settings.copernicus_enabled
    # (backend/app/core/config.py). Changez-la la pour basculer le defaut.
    copernicus: bool = Field(
        default=settings.copernicus_enabled,
        description="Activer/desactiver Copernicus (CDS) dans la collecte. "
        "Si false, climat_copernicus sera null dans le building_data sans erreur.",
    )


@router.post("/diagnostic")
async def run_diagnostic(payload: DiagnosticRequest) -> dict:
    thread_id = str(uuid.uuid4())
    logger.info("=" * 70)
    logger.info("POST /diagnostic  adresse=%r  thread_id=%s", payload.adresse, thread_id)
    t0 = time.perf_counter()

    try:
        final_state = await diagnostic_graph.ainvoke(
            {
                "adresse": payload.adresse,
                "formulaire": payload.formulaire,
                "copernicus": payload.copernicus,
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        logger.exception("diagnostic -- echec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    digital_twin = final_state.get("digital_twin")
    if digital_twin is None:
        logger.error("diagnostic -- aucun contrat produit (etat final incomplet) en %.2fs", elapsed)
        raise HTTPException(status_code=502, detail="Le graphe n'a pas produit de contrat digital_twin.")

    logger.info("diagnostic OK en %.2fs (thread_id=%s)", elapsed, thread_id)
    logger.info("=" * 70)
    return digital_twin


class ZoneRequest(BaseModel):
    """Requête d'évaluation de zone (carte interactive promoteur).

    bounds : tuple[float, float, float, float]
        (lat_min, lon_min, lat_max, lon_max) — bounding box de la zone.
    spacing_km : float
        Espacement entre points de la grille d'échantillonnage (défaut 0.5 km).
    max_points : int
        Nombre maximum de points de la grille (défaut 50).
    land_only : bool
        Si True, ignore les données BDNB (mode terrain nu).
    """
    bounds: tuple[float, float, float, float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box (lat_min, lon_min, lat_max, lon_max)",
    )
    spacing_km: float = Field(default=0.5, ge=0.05, le=5.0)
    max_points: int = Field(default=50, ge=5, le=200)
    land_only: bool = Field(default=False)


@router.post("/diagnostic/zone")
async def run_zone_diagnostic(payload: ZoneRequest) -> dict:
    """Évalue les risques climatiques sur une zone géographique.

    Génère une grille d'échantillonnage régulière, score chaque point
    avec les données simulées (ou réelles si collector_agent est branché),
    et retourne l'agrégation complète : score global, distribution par péril,
    worst-case, et la liste des points pour le rendu cartographique.
    """
    logger.info(">>> POST /diagnostic/zone  bounds=%s", payload.bounds)
    t0 = time.perf_counter()

    try:
        rating = await run_zone_risk_assessment(
            bounds=payload.bounds,
            spacing_km=payload.spacing_km,
            max_points=payload.max_points,
            land_only=payload.land_only,
            collect_fn=None,  # Pas d'appels API réels → simulation géographique
        )
    except Exception as exc:
        logger.exception("zone_diagnostic -- echec bounds=%s", payload.bounds)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    result = rating_zone_to_dict(rating)
    logger.info(">>> POST /diagnostic/zone OK en %.2fs (%d points, score=%.1f)", elapsed, result["nb_points"], result["score_moyen"])
    return result
