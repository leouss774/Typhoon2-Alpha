"""
Modèles Pydantic de la structure Property ID.

Convention (cf. `app/schemas/house_geometry.py`) :
  - Utilise BaseModel de Pydantic avec des champs typés.
  - Les champs optionnels sont marqués Optional[...] = None pour les
    modules futurs non encore implémentés.

Architecture extensible :
  - `FutureModules` est un bloc placeholder que chaque module métier
    (bank, real_estate, artisan, certifications) vient remplir sans
    modifier la structure centrale.
  - `TimelineEvent` permet d'ajouter des événements futurs (inspection,
    réparation, renouvellement assurance, certification, etc.) sans
    changer le modèle.
  - `Certification` est un module intégré (pas un module futur) :
    il fait partie du Property ID dès la génération initiale.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.property_id.certification.schemas import Certification


class BuildingInfo(BaseModel):
    """Informations descriptives du bâtiment, aggregées depuis building_data
    et digital_twin."""

    address: str = Field(..., description="Adresse postale normalisée")
    construction_year: Optional[int] = Field(None, description="Année de construction")
    building_type: Optional[str] = Field(None, description="Type de bâtiment (ex: maison individuelle)")
    materials: Optional[str] = Field(None, description="Matériau principal des murs")
    floors: Optional[int] = Field(None, description="Nombre d'étages")
    roof: Optional[str] = Field(None, description="Matériau / forme de la toiture")
    geometry: dict[str, Any] = Field(default_factory=dict, description="Bloc geometry du jumeau numérique")


class Scores(BaseModel):
    """Scores de risque calculés par le scoring_agent."""

    overall: int = Field(..., ge=0, le=100, description="Score de risque global (0=faible, 100=critique)")
    climate: int = Field(..., ge=0, le=100, description="Score climatique (projection 2050)")
    insurance: int = Field(..., ge=0, le=100, description="Score assurance (aujourd'hui)")


class RiskSummary(BaseModel):
    """Résumé synthétique des risques principaux."""

    highest_risk: str = Field(..., description="Nom de la zone la plus risquée")
    risk_level: str = Field(..., description="Niveau de risque global (faible/modéré/élevé/critique)")
    main_hazard: str = Field(..., description="Aléa principal le plus préoccupant")


class TimelineEvent(BaseModel):
    """Un événement dans la vie du Property ID.

    Conçue pour être extensible : de nouveaux types d'événements
    (inspection, repair, insurance_renewal, certification, renovation...)
    peuvent être ajoutés sans modifier ce modèle.
    """

    date: str = Field(..., description="Date de l'événement (format ISO)")
    event: str = Field(..., description="Libellé de l'événement")
    details: Optional[dict[str, Any]] = Field(None, description="Détails optionnels liés à l'événement")


class FutureModules(BaseModel):
    """Sections réservées aux futurs modules métier.

    Chaque module est un dict libre (None tant que non implémenté) pour
    permettre aux équipes d'y stocker leur structure sans modification
    du noyau Property ID.
    """

    bank: Optional[dict[str, Any]] = Field(None, description="Banque : Loan Risk, Mortgage Score (non implémenté)")
    real_estate: Optional[dict[str, Any]] = Field(None, description="Immobilier : Market Value, Climate Attractiveness (non implémenté)")
    artisan: Optional[dict[str, Any]] = Field(None, description="Artisan : Completed Repairs, Maintenance History (non implémenté)")
    certifications: Optional[dict[str, Any]] = Field(None, description="Certifications : modules métier futurs (autres systèmes de certification externes)")


class PropertyID(BaseModel):
    """Identité numérique du bâtiment — le coeur du système Typhoon.

    Ce n'est PAS un certificat ni un document statique.
    C'est un profil numérique évolutif qui s'enrichit au fil des
    diagnostics, inspections et interventions sur le bâtiment.

    Format du property_id : TY-{année}-{numéro séquentiel à 6 chiffres}

    Design extensible :
      - `timeline` : historique ouvert, prêt pour inspection, réparation,
        renouvellement assurance, certification, rénovation...
      - `future_modules` : placeholders pour les cas d'usage Banque,
        Immobilier, Artisan, Certifications — null tant que non actifs.
    """

    property_id: str = Field(..., description="Identifiant unique TY-YYYY-NNNNNN")
    generated_at: str = Field(..., description="Date de génération ISO")
    building: BuildingInfo = Field(..., description="Informations sur le bâtiment")
    scores: Scores = Field(..., description="Scores de risque aggregés")
    risk_summary: RiskSummary = Field(..., description="Résumé des risques")
    recommendations: list[dict[str, Any]] = Field(default_factory=list, description="Recommandations de travaux (aggregées depuis toutes les zones)")
    digital_twin: dict[str, Any] = Field(..., description="Contrat complet du jumeau numérique 3D")
    timeline: list[TimelineEvent] = Field(default_factory=list, description="Historique des événements du Property ID")
    certification: Optional[Certification] = Field(None, description="Certification Typhoon — niveau de confiance actuel (calculé lors de la génération)")
    future_modules: FutureModules = Field(default_factory=FutureModules, description="Sections réservées aux futurs modules métier")
