"""Route Recommandations : liste des travaux proposés.

GET /api/recommendations/{session_id}
Retourne la liste des recommandations de travaux avec coûts et gains.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/recommendations/{session_id}")
async def get_recommendations(session_id: str):
    """Retourne les recommandations de travaux pour une session."""
    return {
        "session_id": session_id,
        "recommandations": [
            {
                "priorite": 1,
                "titre": "Renforcement des fondations",
                "description": "Traitement des sols argileux par injection de résine expansive et reprise en sous-œuvre.",
                "cout_estime_bas": 8000,
                "cout_estime_haut": 25000,
                "gain_resilience_pct": 70.0,
                "aleas_adresses": ["rga"],
            },
            {
                "priorite": 2,
                "titre": "Drainage périphérique",
                "description": "Installation d'un système de drainage avec pompe de relevage et clapets anti-retour.",
                "cout_estime_bas": 5000,
                "cout_estime_haut": 15000,
                "gain_resilience_pct": 65.0,
                "aleas_adresses": ["inondation"],
            },
            {
                "priorite": 3,
                "titre": "Renforcement de la toiture",
                "description": "Pose de fixations anti-arrachement et renforcement de la charpente.",
                "cout_estime_bas": 6000,
                "cout_estime_haut": 18000,
                "gain_resilience_pct": 55.0,
                "aleas_adresses": ["tempete"],
            },
        ],
        "cout_total_bas": 19000,
        "cout_total_haut": 58000,
        "gain_moyen": 63.3,
    }
