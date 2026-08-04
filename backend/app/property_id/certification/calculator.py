"""
Règles de calcul de la certification Typhoon.

Les seuils et les descriptions sont isolés ici pour permettre :
  - Ajustement des seuils sans modifier le code métier.
  - Traduction / personnalisation des labels facilement.
  - Tests unitaires ciblés.

Règles actuelles (MVP) :
  - Le niveau est déterminé par le score global (overall).
  - Plus le score est bas, meilleur est le niveau.
  - Seuils :
      0–25  → PLATINUM
      26–50 → GOLD
      51–75 → SILVER
      76–100 → BRONZE
"""

from __future__ import annotations

from app.property_id.certification.schemas import CertificationLevel


def get_description_for_level(level: CertificationLevel) -> str:
    """Retourne une description textuelle du niveau de certification."""
    descriptions = {
        CertificationLevel.PLATINUM: (
            "Résilience exceptionnelle. Ce bâtiment présente un risque "
            "climatique minimal et dépasse les normes de construction actuelles."
        ),
        CertificationLevel.GOLD: (
            "Très bonne résilience. Les risques sont faibles et bien gérés. "
            "Quelques améliorations mineures peuvent être envisagées."
        ),
        CertificationLevel.SILVER: (
            "Résilience satisfaisante. Des risques modérés existent mais "
            "restent dans des limites acceptables. Des travaux de mitigation "
            "sont recommandés."
        ),
        CertificationLevel.BRONZE: (
            "Résilience de base. Des risques significatifs sont identifiés. "
            "Des travaux de rénovation sont fortement recommandés pour "
            "améliorer la résilience du bâtiment."
        ),
    }
    return descriptions.get(level, "Niveau non défini.")


def compute_certification_level(
    overall_score: int,
    climate_score: int,
    insurance_score: int,
) -> tuple[CertificationLevel, int]:
    """Calcule le niveau de certification à partir des scores.

    Le niveau est déterminé par la moyenne pondérée des trois scores.
    Actuellement, le score global est prépondérant.
    Pour le MVP, on utilise directement le score global.

    Paramètres
    ----------
    overall_score : int
        Score de risque global (0–100, 0 = meilleur).
    climate_score : int
        Score de projection climatique 2050.
    insurance_score : int
        Score assurance.

    Retourne
    -------
    tuple[CertificationLevel, int]
        (niveau de certification, score consolidé ayant déterminé le niveau)
    """
    # MVP : le score global est le score de certification
    cert_score = overall_score

    if cert_score <= 25:
        level = CertificationLevel.PLATINUM
    elif cert_score <= 50:
        level = CertificationLevel.GOLD
    elif cert_score <= 75:
        level = CertificationLevel.SILVER
    else:
        level = CertificationLevel.BRONZE

    return level, cert_score
