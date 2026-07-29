"""API de recherche d'artisans correspondant aux travaux recommandés."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.artisans.service import matcher

router = APIRouter(prefix="/artisans", tags=["artisans"])


class ArtisanMatchRequest(BaseModel):
    adresse: str = Field(..., min_length=5)
    zones: list[dict[str, Any]]
    limite: int = Field(default=5, ge=1, le=20)


@router.post("/match")
async def match_artisans(payload: ArtisanMatchRequest) -> dict[str, Any]:
    try:
        return await matcher(payload.adresse, payload.zones, payload.limite)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
