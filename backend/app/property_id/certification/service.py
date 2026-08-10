"""
Service de certification Typhoon.

Orchestre la génération du bloc Certification dans le Property ID
à partir des données du diagnostic (building_data, risk_scores).

Le bloc Certification est une section optionnelle du Property ID :
  - Si building_data est vide ou insuffisant, retourne None.
  - Sinon, calcule le niveau via calculator.py et construit l'objet
    avec le badge visuel associé.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.property_id.certification.badge import build_badge
from app.property_id.certification.calculator import compute_certification_level as _compute_level
from app.property_id.certification.schemas import Certification, CertificationLevel, CertificationStatus


def generate_certification(
    building_data: dict[str, Any],
    risk_scores: dict[str, Any],
    digital_twin: dict[str, Any],
) -> Certification | None:
    """Génère la certification Typhoon à partir des données du diagnostic.

    Retourne None si le Property ID n'est pas encore assez mature pour une
    certification (ex: building_data vide).

    Paramètres
    ----------
    building_data : dict
        Sortie du collector_agent.
    risk_scores : dict
        Sortie du scoring_agent.
    digital_twin : dict
        Contrat du digital_twin_agent.

    Retourne
    -------
    Certification | None
        La certification complète, ou None si données insuffisantes.
    """
    if not building_data or not risk_scores:
        return None

    overall_score = risk_scores.get("score_global", 0)
    climate_score = risk_scores.get("projection_2050", {}).get("score_global", 0)
    insurance_score = overall_score  # MVP: insurance = overall

    level, cert_score = _compute_level(overall_score, climate_score, insurance_score)

    now_iso = datetime.now(timezone.utc).isoformat()
    badge = build_badge(level)
    expiry = Certification.default_expiry(now_iso)

    return Certification(
        level=level,
        score=cert_score,
        issued_at=now_iso,
        expires_at=expiry,
        status=CertificationStatus.ACTIVE,
        badge=badge,
    )
