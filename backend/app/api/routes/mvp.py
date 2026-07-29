"""
Routes pour le MVP zone-insurer (scoring simplifié sans murs/sous-sol).

POST /mvp/assess — évalue bâtiment(s) en mode single ou multi, avec Mistral
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.schemas.mvp import MvpRequest, MvpResponse
from app.services.mvp_assessor import assess

logger = get_logger(__name__)
router = APIRouter(prefix="/mvp", tags=["mvp"])


@router.post("/assess", response_model=MvpResponse)
async def assess_mvp(payload: MvpRequest) -> MvpResponse:
    """
    Évalue les risques climatiques avec le modèle MVP simplifié
    (sans murs ni sous-sol). Supporte mode single (adresse) et
    multi (polygone). Recommandations générées par Mistral via RAG.
    """
    logger.info("POST /mvp/assess -- mode=%s, address=%r, polygon=%d pts", payload.mode, payload.address, len(payload.polygon))
    try:
        report = await assess(
            mode=payload.mode,
            address=payload.address,
            points=[p.model_dump() for p in payload.points],
            polygon=[p.model_dump() for p in payload.polygon],
        )
        return MvpResponse(**report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("POST /mvp/assess -- echec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")
