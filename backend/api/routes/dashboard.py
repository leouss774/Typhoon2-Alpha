"""Route Dashboard : retourne les données pour l'affichage frontend.

GET /api/dashboard/{session_id}
Récupère le rapport d'analyse complet formaté pour le dashboard
(score global, carte, risques, jumeau numérique, recommandations).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/dashboard/{session_id}")
async def get_dashboard(session_id: str):
    """Retourne les données du dashboard pour une session donnée."""
    # TODO: Récupérer depuis la base de données persistée
    # Pour l'instant, données simulées pour le développement frontend
    return {
        "session_id": session_id,
        "score_global": 68.5,
        "niveau_risque": "élevé",
        "adresse": "15 Rue des Lilas, 33140 Villenave-d'Ornon",
        "coordonnees": {"lat": 44.771, "lng": -0.563},
        "scores_par_alea": {
            "rga": {"score": 82.0, "niveau": "critique", "label": "Retrait-gonflement des argiles"},
            "inondation": {"score": 45.0, "niveau": "modéré", "label": "Inondation"},
            "tempete": {"score": 30.0, "niveau": "modéré", "label": "Tempête"},
            "feu_foret": {"score": 15.0, "niveau": "faible", "label": "Feu de forêt"},
        },
        "risques_dominants": ["rga", "inondation", "tempete"],
        "projections_2050": {
            "rga": 91.0,
            "inondation": 62.0,
            "tempete": 45.0,
        },
        "recommandations": [
            {
                "priorite": 1,
                "titre": "Renforcement des fondations",
                "cout_estime_bas": 8000,
                "cout_estime_haut": 25000,
                "gain_resilience_pct": 70.0,
            },
            {
                "priorite": 2,
                "titre": "Drainage périphérique",
                "cout_estime_bas": 5000,
                "cout_estime_haut": 15000,
                "gain_resilience_pct": 65.0,
            },
        ],
        "synthese": "Le bien présente un niveau de risque élevé. Les risques dominants sont le retrait-gonflement des argiles et les inondations.",
    }
