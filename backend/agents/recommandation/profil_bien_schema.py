"""Minimal declarative building profile used by the scoring engine.

This is intentionally smaller than the final business schema: it only contains
fields required by the first scoring rules and can evolve later without
breaking the engine contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProfilBien:
    disponible: bool = False
    source: Optional[str] = None
    annee_construction: Optional[int] = None
    type_bien: Optional[str] = None
    usage: Optional[str] = None
    surface_m2: Optional[float] = None
    nb_niveaux: Optional[int] = None
    type_toiture: Optional[str] = None
    materiau_murs: Optional[str] = None
    isolation_toiture: Optional[str] = None
    isolation_murs: Optional[str] = None
    isolation_sol: Optional[str] = None
    presence_sous_sol: Optional[bool] = None
    presence_cave: Optional[bool] = None
    presence_garage: Optional[bool] = None
    climatisation: Optional[bool] = None
    chauffage_principal: Optional[str] = None
    installation_electrique_annee: Optional[int] = None
    installation_electrique_renovee: Optional[bool] = None
    presence_detecteurs_fumee: Optional[bool] = None
    exposition_solaire: Optional[str] = None
    zone_mitoyennete: Optional[str] = None
    renovation_toiture_annee: Optional[int] = None
    renovation_facade_annee: Optional[int] = None
    observations: dict[str, str] = field(default_factory=dict)
