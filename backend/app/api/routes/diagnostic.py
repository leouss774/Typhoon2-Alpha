"""POST /diagnostic — route principale de diagnostic.

Instancie le StateGraph (collector → scoring → bank → digital_twin).
Retourne le contrat complet pour le frontend.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.app.agents.graph import diagnostic_graph
from backend.app.core.logging import get_logger
from backend.services.analyses_store import get_analysis, set_analysis, analyses_store

logger = get_logger(__name__)
router = APIRouter()


class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complète du bien")
    formulaire: dict | None = Field(default=None, description="Champs saisis explicitement")
    bank_mode: bool = Field(default=False, description="Activer le module bancaire")



@router.post("/diagnostic")
async def run_diagnostic(payload: DiagnosticRequest) -> dict:
    """Diagnostic complet : collecte → scoring → banque → jumeau numérique."""
    thread_id = str(uuid.uuid4())
    logger.info("=" * 70)
    logger.info("POST /diagnostic  adresse=%r  thread_id=%s", payload.adresse, thread_id)
    t0 = time.perf_counter()

    try:
        final_state = await diagnostic_graph.ainvoke(
            {
                "adresse": payload.adresse,
                "formulaire": payload.formulaire or {},
                "session_id": thread_id,
                "copernicus": False,
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

    result = {
        "session_id": thread_id,
        "adresse": payload.adresse,
        "digital_twin": digital_twin,
        "bank_decision": final_state.get("bank_decision", {}),
        "score_global": digital_twin.get("score_global", 0),
        "zones": digital_twin.get("zones", {}),
        "projection_2050": digital_twin.get("projection_2050", {}),
    }

    # Si mode bancaire, stocker pour polling (persistance SQLite)
    if payload.bank_mode:
        set_analysis(thread_id, {**result, "status": "completed"})

    logger.info("diagnostic OK en %.2fs (score=%d)", elapsed, result["score_global"])
    logger.info("=" * 70)
    return result


@router.get("/diagnostic/{session_id}")
async def get_diagnostic(session_id: str) -> dict:
    """Récupère un diagnostic stocké (pour polling mode banque).
    Cherche d'abord dans le cache mémoire, puis dans SQLite.
    """
    analysis = get_analysis(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return analysis
