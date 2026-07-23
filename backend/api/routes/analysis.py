"""Route d'analyse : déclenche le pipeline LangGraph complet.

POST /api/analyze
Reçoit le formulaire client et les données brutes,
lance l'exécution du graphe Typhoon,
retourne le rapport d'analyse complet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent_graph import get_typhoon_app, TyphoonState

router = APIRouter()


class AnalyzeRequest(BaseModel):
    """Corps de la requête d'analyse."""

    session_id: str = Field(default="", description="Identifiant de session")
    client_form: dict = Field(description="Données du formulaire client")
    raw_data: dict = Field(default_factory=dict, description="Données brutes")


class AnalyzeResponse(BaseModel):
    """Réponse de l'analyse complète."""

    session_id: str
    status: str
    score_global: float | None
    rapport: dict | None


@router.post("/analyze", response_model=AnalyzeResponse)
async def run_analysis(request: AnalyzeRequest):
    """Lance le pipeline d'analyse complet via LangGraph."""
    try:
        app = get_typhoon_app()

        initial_state = TyphoonState(
            session_id=request.session_id,
            client_form=request.client_form,
            raw_data=request.raw_data,
        )

        result = await app.ainvoke(initial_state.model_dump())

        rapport = result.get("rapport_final")
        return AnalyzeResponse(
            session_id=request.session_id,
            status="completed" if result.get("validation_passed") else "validation_failed",
            score_global=result.get("score_global"),
            rapport=rapport.model_dump() if rapport and hasattr(rapport, "model_dump") else rapport,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'analyse : {str(e)}")
