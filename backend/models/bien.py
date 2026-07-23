"""Modèle représentant un bien immobilier."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BienImmobilier(BaseModel):
    """Caractéristiques d'un bien immobilier soumis à l'analyse."""

    adresse: str = Field(description="Adresse complète")
    code_insee: str = Field(default="", description="Code INSEE de la commune")
    type_bien: str = Field(description="maison | appartement")
    surface_m2: float = Field(gt=0, description="Surface habitable en m²")
    annee_construction: int = Field(description="Année de construction")
    materiau_principal: str = Field(description="brique | parpaing | bois | pierre | autre")
    etage: int | None = Field(default=None, description="Étage (si appartement)")
    sous_sol: bool = Field(default=False, description="Présence d'un sous-sol")
    nombre_niveaux: int = Field(default=1, ge=1, description="Nombre de niveaux")
    toiture_type: str = Field(default="tuiles", description="tuiles | ardoises | bac_acier | toit_plat | autre")
    isolation: str | None = Field(default=None, description="Niveau d'isolation")
    annee_derniere_renovation: int | None = Field(default=None, description="Année de la dernière rénovation")

    def age(self, annee_reference: int = 2025) -> int:
        """Calcule l'âge du bien."""
        return annee_reference - self.annee_construction

    def a_besoin_renovation(self) -> bool:
        """Vrai si le bien a plus de 30 ans sans rénovation récente."""
        if self.annee_derniere_renovation:
            return (2025 - self.annee_derniere_renovation) > 15
        return self.age() > 30
