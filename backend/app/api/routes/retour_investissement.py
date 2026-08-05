"""
POST /diagnostic/retour-investissement — volet économique « coût des travaux
de résilience vs. gain » (cf. docs/STRATEGIE_RETOUR_INVESTISSEMENT.md).

Entrées : les mêmes blocs que /diagnostic/recommandations (building_data +
risk_scores tels que renvoyés dans digital_twin._resume par
/diagnostic/fast), plus éventuellement la surface du bien (emprise au sol,
geometry du jumeau) — sinon repli BDNB.

Sortie : contrat économique déterministe et sourcé (niveaux A/B/C + ROI +
valeur immobilière qualitative), avec 3 statuts seulement : calcule /
fourchette / null. Aucun montant n'est produit sans source.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.economie.service import compute_retour_investissement

logger = get_logger(__name__)
router = APIRouter()


class RetourInvestissementRequest(BaseModel):
    building_data: dict = Field(..., description="Tel que renvoyé par /diagnostic/fast (digital_twin._resume.building_data)")
    risk_scores: dict = Field(..., description="Tel que renvoyé par /diagnostic/recommandations (zones enrichies de recommandations et cout_estime)")
    formulaire: dict | None = Field(default=None)
    surface_m2: float | None = Field(
        default=None,
        description="Emprise au sol du bien (geometry du jumeau) — sinon repli BDNB. "
        "Proxy : valeur de marché = prix médian DVF × surface.",
    )


@router.post("/diagnostic/retour-investissement")
async def run_retour_investissement(payload: RetourInvestissementRequest) -> dict:
    """Calcule le contrat économique (déterministe, sans LLM)."""
    logger.info("=" * 70)
    logger.info("POST /diagnostic/retour-investissement")

    try:
        # Calcul CPU pur : ne doit pas bloquer la boucle asyncio.
        result = await asyncio.to_thread(
            compute_retour_investissement,
            payload.building_data,
            payload.risk_scores,
            payload.surface_m2,
        )
    except Exception as exc:
        logger.exception("retour-investissement -- echec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    logger.info("POST /diagnostic/retour-investissement OK — confiance=%s", result["confidence"].get("niveau"))
    logger.info("=" * 70)
    return result
