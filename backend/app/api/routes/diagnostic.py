"""
Routes de diagnostic Typhoon.

Routes actives :
  POST /diagnostic             → diagnostic complet (graphe LangGraph)
  POST /diagnostic/fast        → rapide (collecte + scoring seulement)
  POST /diagnostic/recommandations → phase 2 (RAG + interprétation)
  GET  /diagnostic/adresse     → MVP géo-risque : adresse → Géorisques → RisqueReport
"""

from __future__ import annotations

import asyncio
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents import digital_twin_agent, interpretation_agent, recommandations_agent, scoring_agent
from app.agents.collector_agent import collect
from app.agents.graph import diagnostic_graph
from app.connectors.geocodage_connector import AdresseNonTrouveeError, geocoder_adresse
from app.connectors.georisques import get_risque_report
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Diagnostic complet (jumeau numérique 3D)
# ---------------------------------------------------------------------------

class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complète du bien")
    formulaire: dict | None = Field(
        default=None,
        description="Champs geometry saisis explicitement (priorité sur l'inférence BDNB).",
    )
    copernicus: bool = Field(
        default=settings.copernicus_enabled,
        description="Activer/désactiver Copernicus (CDS) dans la collecte.",
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
        logger.exception("diagnostic -- échec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    digital_twin = final_state.get("digital_twin")
    if digital_twin is None:
        logger.error("diagnostic -- aucun contrat produit en %.2fs", elapsed)
        raise HTTPException(status_code=502, detail="Le graphe n'a pas produit de contrat digital_twin.")

    logger.info("diagnostic OK en %.2fs (thread_id=%s)", elapsed, thread_id)
    logger.info("=" * 70)
    return digital_twin


@router.post("/diagnostic/fast")
async def run_diagnostic_fast(payload: DiagnosticRequest) -> dict:
    """Variante rapide : collecte + scoring + assemblage. Sans RAG ni interprétation LLM."""
    logger.info("=" * 70)
    logger.info("POST /diagnostic/fast  adresse=%r", payload.adresse)
    t0 = time.perf_counter()

    try:
        building_data = await collect(payload.adresse, enable_copernicus=payload.copernicus)
        state: dict = {"building_data": building_data, "formulaire": payload.formulaire}
        state.update(scoring_agent.run(state))
        state.update(digital_twin_agent.run(state))
    except Exception as exc:
        logger.exception("diagnostic/fast -- échec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu être assemblé.")

    digital_twin["_resume"] = {
        "building_data": state["building_data"],
        "risk_scores": state["risk_scores"],
        "formulaire": payload.formulaire,
    }

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/fast OK en %.2fs", elapsed)
    logger.info("=" * 70)
    return digital_twin


class DiagnosticRecommandationsRequest(BaseModel):
    building_data: dict = Field(..., description="Tel que renvoyé par /diagnostic/fast (_resume.building_data)")
    risk_scores: dict = Field(..., description="Tel que renvoyé par /diagnostic/fast (_resume.risk_scores)")
    formulaire: dict | None = Field(default=None)


@router.post("/diagnostic/recommandations")
async def run_diagnostic_recommandations(payload: DiagnosticRecommandationsRequest) -> dict:
    """Phase 2 lente : RAG (Mistral) + interprétation LLM. Ne relance PAS la collecte."""
    logger.info("=" * 70)
    logger.info("POST /diagnostic/recommandations")
    t0 = time.perf_counter()

    state: dict = {
        "building_data": payload.building_data,
        "risk_scores": payload.risk_scores,
        "formulaire": payload.formulaire,
    }

    try:
        state.update(await recommandations_agent.run(state))
        state.update(await asyncio.to_thread(interpretation_agent.run, state))
        state.update(digital_twin_agent.run(state))
    except Exception as exc:
        logger.exception("diagnostic/recommandations -- échec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu être assemblé.")

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/recommandations OK en %.2fs", elapsed)
    logger.info("=" * 70)
    return digital_twin


# ---------------------------------------------------------------------------
# MVP Géo-risque : adresse → Géorisques → RisqueReport
# ---------------------------------------------------------------------------

@router.get("/diagnostic/adresse")
async def diagnostic_adresse(
    q: str = Query(..., min_length=3, description="Adresse française (texte libre)")
) -> dict:
    """
    Flux souverain : adresse saisie → géocodage BAN → Géorisques → RisqueReport.

    Codes de retour :
      200 : rapport complet (peut contenir erreurs_partielles si une sous-API a échoué)
      422 : adresse non trouvée par la BAN (score_geocodage < 0.4 ou zéro résultat)
      502 : Géorisques totalement indisponible
    """
    logger.info("GET /diagnostic/adresse  q=%r", q)
    t0 = time.perf_counter()

    # Étape 1 — Géocodage BAN
    try:
        geo = await geocoder_adresse(q)
    except AdresseNonTrouveeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "adresse_non_trouvee", "detail": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "geocodage_indisponible", "detail": str(exc)},
        ) from exc

    # Rejeter si score de géocodage trop bas (adresse ambiguë)
    if geo.score < 0.4:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "adresse_ambigue",
                "detail": f"Score de géocodage trop faible ({geo.score:.2f}) pour «{q}». Précisez la ville ou le code postal.",
                "label_propose": geo.label,
            },
        )

    # Étape 2 & 3 — Géorisques → RisqueReport normalisé
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            report = await get_risque_report(
                client=client,
                adresse_saisie=q,
                adresse_normalisee=geo.label,
                lat=geo.lat,
                lon=geo.lon,
                code_insee=geo.code_insee,
            )
    except Exception as exc:
        logger.exception("diagnostic/adresse -- Géorisques inaccessible pour %r", q)
        raise HTTPException(
            status_code=502,
            detail={"error": "source_indisponible", "source": "georisques", "detail": str(exc)},
        ) from exc

    elapsed = time.perf_counter() - t0
    logger.info(
        "diagnostic/adresse OK en %.2fs — %d aléas présents, %d erreurs partielles",
        elapsed, report.alea_count, len(report.erreurs_partielles),
    )

    return report.model_dump()
