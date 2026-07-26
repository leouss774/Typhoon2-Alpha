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
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complete du bien")
    formulaire: dict | None = Field(
        default=None,
        description="Champs geometry saisis explicitement (priorite sur l'inference BDNB) : "
        "has_basement, has_garage, garage_position, has_garden, garden_surface_m2, roof_shape...",
    )


@router.post("/diagnostic")
async def run_diagnostic(payload: DiagnosticRequest) -> dict:
    thread_id = str(uuid.uuid4())
    logger.info("=" * 70)
    logger.info("POST /diagnostic  adresse=%r  thread_id=%s", payload.adresse, thread_id)
    t0 = time.perf_counter()

    try:
        final_state = await diagnostic_graph.ainvoke(
            {"adresse": payload.adresse, "formulaire": payload.formulaire},
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
