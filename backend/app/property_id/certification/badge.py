"""
Configuration visuelle des badges de certification Typhoon.

Ce fichier contient toutes les métadonnées visuelles associées
à chaque niveau de certification : couleurs, labels, icônes.

Le badge n'est pas une image uploadée — c'est un composant vectoriel
défini par la plateforme Typhoon. Le SVG est généré côté frontend,
mais les métadonnées (couleurs, libellés) sont fournies par l'API
pour que le front puisse le rendre sans connaissance préalable.

Extensibilité :
  - Ajoutez un nouveau niveau dans BADGE_CONFIG avec ses couleurs.
  - Le frontend l'affiche automatiquement.
  - Aucune modification de schéma ou de base de données nécessaire.
"""

from __future__ import annotations

from app.property_id.certification.calculator import get_description_for_level
from app.property_id.certification.schemas import BadgeStyle, CertificationBadge, CertificationLevel

BADGE_VERSION = "1.0"
TYPHOON_BRAND = "Typhoon"
TYPHOON_ICON_SVG_PATH = "M12 2L2 7v10l10 5 10-5V7L12 2zM12 6v12M8 9l4-3 4 3M8 15l4 3 4-3"

BADGE_CONFIG: dict[CertificationLevel, dict[str, str]] = {
    CertificationLevel.GOLD: {
        "primary_color": "#D4A017",
        "secondary_color": "#B8860B",
        "accent_color": "#F5D76E",
        "label": "Gold",
    },
    CertificationLevel.SILVER: {
        "primary_color": "#A8B8C8",
        "secondary_color": "#7A8A9A",
        "accent_color": "#D0DCE8",
        "label": "Silver",
    },
    CertificationLevel.BRONZE: {
        "primary_color": "#CD7F32",
        "secondary_color": "#A0652A",
        "accent_color": "#E8C88A",
        "label": "Bronze",
    },
}


def build_badge(level: CertificationLevel) -> CertificationBadge:
    """Construit l'objet CertificationBadge pour un niveau donné.

    Paramètres
    ----------
    level : CertificationLevel
        Niveau de certification (Gold, Silver, Bronze).

    Retourne
    -------
    CertificationBadge
        Objet badge complet avec style et métadonnées.
    """
    config = BADGE_CONFIG.get(level, BADGE_CONFIG[CertificationLevel.BRONZE])

    return CertificationBadge(
        name=f"{TYPHOON_BRAND} {config['label']}",
        version=BADGE_VERSION,
        icon_svg_path=TYPHOON_ICON_SVG_PATH,
        style=BadgeStyle(
            primary_color=config["primary_color"],
            secondary_color=config["secondary_color"],
            accent_color=config["accent_color"],
            label=config["label"],
            description=get_description_for_level(level),
        ),
    )
