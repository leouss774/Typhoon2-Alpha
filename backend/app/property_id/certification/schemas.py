"""
Modèles Pydantic du module Certification Typhoon.

La certification est une section du Property ID — pas un objet séparé.
Elle représente le niveau de confiance actuel du bâtiment selon les
critères de la plateforme Typhoon.

Convention (cf. app/property_id/schemas.py) :
  - Utilise BaseModel de Pydantic avec des champs typés.
  - Les énumérations sont utilisées pour les niveaux fixes.
  - Tous les champs de date sont en format ISO 8601 (str).

Extensibilité :
  - CertificationLevel est un Enum pour switch/case propre.
  - Les seuils sont dans calculator.py, pas ici.
  - BadgeConfig vient de badge.py (séparation des préoccupations).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CertificationLevel(str, Enum):
    """Niveaux de certification Typhoon.

    Ordre croissant : BRONZE < SILVER < GOLD < PLATINUM.
    Utilisé pour les comparaisons (ex: level >= GOLD).
    """
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
    PLATINUM = "Platinum"


class CertificationStatus(str, Enum):
    """Statut de validité de la certification."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    PENDING = "PENDING"


class BadgeStyle(BaseModel):
    """Style visuel du badge de certification.

    Dérivé de BadgeConfig dans badge.py — sérialisable pour l'API.
    """

    primary_color: str = Field(..., description="Couleur principale du badge (hex)")
    secondary_color: str = Field(..., description="Couleur secondaire (dégradé, hex)")
    accent_color: str = Field(..., description="Couleur d'accent (hex)")
    label: str = Field(..., description="Libellé du niveau (ex: 'Or')")
    description: str = Field(..., description="Courte description du niveau")


class CertificationBadge(BaseModel):
    """Badge visuel de certification.

    Contient toutes les informations nécessaires au rendu côté frontend.
    Le badge n'est pas une image uploadée — c'est un composant vectoriel
    défini par la plateforme Typhoon.
    """

    name: str = Field(..., description="Nom complet du badge (ex: 'Typhoon Gold')")
    version: str = Field(..., description="Version du système de badge (ex: '1.0')")
    icon_svg_path: str = Field(..., description="Chemin SVG du logo Typhoon dans le badge")
    style: BadgeStyle = Field(..., description="Style visuel du badge")


class Certification(BaseModel):
    """Section de certification dans le Property ID.

    Contrairement au Property ID (qui est l'identité numérique évolutive
    du bâtiment), la certification est un indicateur de confiance ponctuel
    qui change lorsque les scores évoluent.
    """

    level: CertificationLevel = Field(..., description="Niveau de certification actuel")
    score: int = Field(..., ge=0, le=100, description="Score global ayant déterminé le niveau")
    issued_at: str = Field(..., description="Date d'émission (ISO 8601)")
    expires_at: str = Field(..., description="Date d'expiration (ISO 8601)")
    status: CertificationStatus = Field(default=CertificationStatus.ACTIVE, description="Statut de validité")
    badge: CertificationBadge = Field(..., description="Badge visuel associé")

    @staticmethod
    def default_expiry(issued_at: str | None = None) -> str:
        """Calcule la date d'expiration par défaut (1 an après l'émission)."""
        try:
            base = datetime.fromisoformat(issued_at) if issued_at else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            base = datetime.now(timezone.utc)
        expiry = base + timedelta(days=365)
        return expiry.isoformat()


class CertificationEvent(BaseModel):
    """Événement de changement de certification dans la timeline.

    Chaque fois que le niveau de certification change, un événement
    est ajouté à la timeline du Property ID.
    """

    date: str = Field(..., description="Date du changement (ISO 8601)")
    previous_level: Optional[CertificationLevel] = Field(None, description="Ancien niveau (None = première certification)")
    new_level: CertificationLevel = Field(..., description="Nouveau niveau")
    previous_score: Optional[int] = Field(None, ge=0, le=100, description="Ancien score")
    new_score: int = Field(..., ge=0, le=100, description="Nouveau score")
    reason: str = Field(..., description="Raison du changement")
