"""
Routes API du Property ID.

POST /property-id/generate
    Déclenche un diagnostic complet puis génère le Property ID associé.

GET /property-id/{id}
    Retourne un Property ID stocké par son identifiant.

GET /property-id
    Liste les Property IDs récents.

Ces routes suivent le même pattern que POST /diagnostic (cf.
app/api/routes/diagnostic.py) : elles instancient le StateGraph,
récupèrent le state final, et l'enrichissent avec le Property ID.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.graph import diagnostic_graph
from app.core.logging import get_logger
from app.property_id.schemas import PropertyID
from app.property_id.service import (
    generate_property_id as _generate_property_id,
    get_property_id,
    list_property_ids,
)

logger = get_logger(__name__)
router = APIRouter()


class PropertyIDGenerateRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complète du bien")
    formulaire: dict | None = Field(default=None, description="Champs géométrie saisis explicitement")


@router.post("/property-id/generate")
async def generate(payload: PropertyIDGenerateRequest) -> PropertyID:
    """Déclenche un diagnostic complet et retourne le Property ID.

    Parcourt le StateGraph (collector_agent → scoring_agent →
    recommandations_agent → digital_twin_agent), puis génère le Property
    ID à partir du state final.

    Retourne l'objet PropertyID complet (pas un certificat PDF —
    voir schemas.py : c'est un profil numérique structuré).
    """
    thread_id = str(uuid.uuid4())
    logger.info("=" * 70)
    logger.info("POST /property-id/generate  adresse=%r  thread_id=%s", payload.adresse, thread_id)
    t0 = time.perf_counter()

    try:
        final_state = await diagnostic_graph.ainvoke(
            {"adresse": payload.adresse, "formulaire": payload.formulaire},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        logger.exception("property-id/generate -- échec diagnostic pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = final_state.get("digital_twin")
    building_data = final_state.get("building_data")
    risk_scores = final_state.get("risk_scores")

    if digital_twin is None or building_data is None or risk_scores is None:
        elapsed = time.perf_counter() - t0
        logger.error("property-id/generate -- state final incomplet après %.2fs", elapsed)
        raise HTTPException(status_code=502, detail="Le graphe n'a pas produit un état complet.")

    property_id = _generate_property_id(building_data, risk_scores, digital_twin)

    elapsed = time.perf_counter() - t0
    logger.info("property-id/generate OK — %s en %.2fs", property_id.property_id, elapsed)
    logger.info("=" * 70)
    return property_id


@router.get("/property-id/{pid}")
async def get_by_id(pid: str) -> PropertyID:
    """Retourne un Property ID stocké par son identifiant.

    Format attendu : TY-YYYY-NNNNNN
    """
    logger.info("GET /property-id/%s", pid)
    result = get_property_id(pid)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Property ID {pid!r} introuvable.")
    return result


@router.get("/property-id")
async def list_all(limit: int = 20) -> list[PropertyID]:
    """Liste les Property IDs les plus récents (limite configurable)."""
    logger.info("GET /property-id (limit=%d)", limit)
    return list_property_ids(limit)
