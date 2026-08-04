from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.logging import get_logger
from partner_api.auth import require_api_key
from partner_api.schemas import AnalyzeRequest, AnalyzeResponse
from partner_api.service import AddressNotFound, analyze_address

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest, partner: str = Depends(require_api_key)) -> AnalyzeResponse:
    logger.info("partner_api /v1/analyze -- partenaire=%r adresse=%r", partner, payload.address)
    try:
        return await analyze_address(payload.address)
    except AddressNotFound as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("partner_api /v1/analyze -- echec pour %r", payload.address)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
