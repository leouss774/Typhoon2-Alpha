"""Modèle représentant les données du formulaire client."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FormulaireClient(BaseModel):
    """Données soumises par le client via le formulaire."""

    nom: str = Field(default="", description="Nom du propriétaire")
    email: str = Field(default="", description="Email de contact")
    telephone: str | None = Field(default=None, description="Téléphone")
    adresse: str = Field(description="Adresse complète du bien")
    code_postal: str = Field(default="", description="Code postal")
    ville: str = Field(default="", description="Ville")
    type_bien: str = Field(description="maison | appartement")
    surface_m2: float = Field(gt=0, description="Surface en m²")
    annee_construction: int = Field(description="Année de construction")
    materiau_principal: str = Field(description="brique | parpaing | bois | pierre")
    sous_sol: bool = Field(default=False)
    etage: int | None = Field(default=None, ge=0)
    nombre_pieces: int | None = Field(default=None, ge=1)
    toiture_type: str = Field(default="tuiles")
    isolation_presente: bool = Field(default=False)
    sinistres_anterieurs: list[str] = Field(default_factory=list)
    budget_travaux_max: float | None = Field(default=None, gt=0, description="Budget max pour travaux (€)")
    consentement_rgpd: bool = Field(default=False)

    @field_validator("email")
    @classmethod
    def valider_email(cls, v: str) -> str:
        if v and "@" not in v:
            raise ValueError("Email invalide")
        return v

    @field_validator("annee_construction")
    @classmethod
    def valider_annee(cls, v: int) -> int:
        if v < 1800 or v > 2026:
            raise ValueError("Année de construction invalide")
        return v

    @field_validator("consentement_rgpd")
    @classmethod
    def valider_rgpd(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Le consentement RGPD est requis")
        return v
