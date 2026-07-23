"""Route Chat : interface pour l'Agent Conversationnel (Agent #3).

POST /api/chat/{session_id}
Reçoit une question du client et retourne une réponse
basée sur le contexte du rapport d'analyse.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent_graph.subgraphs.chat_subgraph import build_chat_subgraph, ChatState
from backend.agents.conversationnel.agent import repondre_question_client

router = APIRouter()


class ChatRequest(BaseModel):
    """Message du client."""

    question: str = Field(min_length=1, description="Question posée par le client")
    historique: list[dict] = Field(default_factory=list, description="Messages précédents")


class ChatResponse(BaseModel):
    """Réponse du conseiller."""

    reponse: str
    session_id: str


@router.post("/chat/{session_id}", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    """Répond à une question du client sur son diagnostic."""
    try:
        # Récupérer le contexte du rapport
        # TODO: Charger depuis la base de données persistée
        rapport_contexte = _load_rapport(session_id)

        reponse = repondre_question_client(
            question=request.question,
            rapport_contexte=rapport_contexte,
            historique=request.historique,
        )

        return ChatResponse(
            reponse=reponse,
            session_id=session_id,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du chat : {str(e)}")


def _load_rapport(session_id: str) -> dict:
    """Charge le contexte du rapport pour une session.

    TODO: Remplacer par une vraie persistance (SQLite/PostgreSQL).
    """
    return {
        "session_id": session_id,
        "score_global": 68.5,
        "analyse_risque": {
            "risques_dominants": ["rga", "inondation", "tempete"],
            "synthese": "Le bien est principalement exposé au retrait-gonflement des argiles (RGA) et aux inondations.",
        },
        "recommandations": [
            {
                "titre": "Renforcement des fondations",
                "priorite": 1,
                "cout_estime_bas": 8000,
                "cout_estime_haut": 25000,
                "gain_resilience_pct": 70.0,
            },
            {
                "titre": "Drainage périphérique",
                "priorite": 2,
                "cout_estime_bas": 5000,
                "cout_estime_haut": 15000,
                "gain_resilience_pct": 65.0,
            },
        ],
    }
