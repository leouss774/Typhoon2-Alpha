"""
Modèles de validation pour le formulaire de diagnostic habitation.
Fichier séparé de risk_score_pipeline.py, indépendant du pipeline Hubeau.
"""

from typing import List, Optional
from pydantic import BaseModel


class ClientInfo(BaseModel):
    nom: str = ""
    adresse: str = ""


class Construction(BaseModel):
    materiaux: List[str] = []
    date_construction: Optional[str] = None
    age_maison: Optional[str] = None
    superficie_m2: Optional[float] = None


class Plomberie(BaseModel):
    etat_canalisations: str = ""
    detecteurs_eau_presents: bool = False
    nombre_detecteurs_eau: int = 0


class IsolationClimatisation(BaseModel):
    bonne_isolation: bool = False
    type_isolation: str = ""
    climatisation_presente: bool = False
    nombre_unites_clim: int = 0


class RisquesIncendie(BaseModel):
    appareils_a_risque: List[str] = []
    detecteur_fumee: bool = False
    etat_systeme_electrique: str = ""


class Complementaire(BaseModel):
    type_chauffage: str = ""
    piscine_presente: bool = False
    remarques: str = ""


class DiagnosticHabitation(BaseModel):
    client: ClientInfo
    construction: Construction
    plomberie: Plomberie
    isolation_climatisation: IsolationClimatisation
    risques_incendie: RisquesIncendie
    complementaire: Complementaire