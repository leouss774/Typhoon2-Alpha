"""
Schémas Pydantic pour le diagnostic adresse → Géorisques → RisqueReport.
Plan : typhoon_adresse_georisques_plan.md §3

Contrat stable, indépendant des détails de l'API Géorisques.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# D03 — bandes de risque (5 niveaux, mêmes clés que le frontend zone.html)
# ---------------------------------------------------------------------------

class NiveauRisque(str, Enum):
    TRES_FAIBLE = "tres_faible"
    FAIBLE      = "faible"
    MODERE      = "modere"
    ELEVE       = "eleve"
    CRITIQUE    = "critique"


def niveau_from_score(score: int | None) -> NiveauRisque | None:
    """Convertit un score 0–100 en bande D03."""
    if score is None:
        return None
    if score < 20:
        return NiveauRisque.TRES_FAIBLE
    if score < 40:
        return NiveauRisque.FAIBLE
    if score < 60:
        return NiveauRisque.MODERE
    if score < 80:
        return NiveauRisque.ELEVE
    return NiveauRisque.CRITIQUE


# ---------------------------------------------------------------------------
# Détail d'un aléa
# ---------------------------------------------------------------------------

class AleaDetail(BaseModel):
    code: str                         # ex: "inondation", "rga", "sismicite", "feu_foret", "radon"
    libelle: str                      # libellé FR affichable
    present: bool | None              # None si la source a échoué (à mon adresse)
    present_commune: bool | None = None # statut au niveau de la commune (ex: existant/concerné)
    niveau: NiveauRisque | None       # None si Géorisques ne fournit pas de gradation
    zonage: str | None = None         # ex: "Zone sismique 2 - faible"
    catnat_historique: list[dict] | None = None  # arrêtés CatNat, si dispo
    source: str = "georisques"
    url_detail: str | None = None     # lien vers la fiche officielle Géorisques
    erreur: str | None = None         # rempli si la sous-source a échoué


# ---------------------------------------------------------------------------
# Recommandations Mistral IA — champ optionnel sur RisqueReport
# ---------------------------------------------------------------------------

class RecommandationsIA(BaseModel):
    """
    Recommandations générées par Mistral à partir du RisqueReport uniquement.

    Règles de contrat :
    - Mistral ne reçoit QUE RisqueReport.model_dump() (jamais les données Géorisques brutes).
    - Si Mistral échoue ou timeout → recommandations=None sur RisqueReport (jamais un 500).
    - Les champs ici sont tous optionnels : un champ vide vaut mieux qu'une hallucination.
    """
    resume: str                           # synthèse en 1–2 phrases
    actions_prioritaires: list[str]       # ex: ["Vérifier l'assurabilité inondation", ...]
    points_vigilance: list[str] = []      # points d'attention supplémentaires
    modele: str = "mistral-small-latest"  # traçabilité du modèle utilisé
    metadata: dict[str, Any] = {}         # nb_tokens, latence_ms, etc.


# ---------------------------------------------------------------------------
# Rapport complet
# ---------------------------------------------------------------------------

class TypeBatiment(BaseModel):
    """Résultat de la détection du type de bâtiment via Overpass (OSM)."""
    type: str = "inconnu"             # "industriel" | "residentiel" | "inconnu"
    confiance: float = 0.0            # 0-1
    tags: dict[str, Any] = {}         # tags OSM trouvés
    nom: str | None = None            # nom du bâtiment si disponible
    erreur: str | None = None


class RisqueReport(BaseModel):
    adresse_saisie: str
    adresse_normalisee: str
    lat: float
    lon: float
    code_insee: str
    date_generation: date
    alea_count: int                   # nombre d'aléas présents (present=True)
    aleas: list[AleaDetail]
    erreurs_partielles: list[str] = []  # ex: ["sismicite: timeout Géorisques"]
    recommandations: RecommandationsIA | None = None  # None si Mistral absent/en erreur
    type_batiment: TypeBatiment | None = None  # détection Overpass (usine vs maison)
    avertissement: str = (
        "Ce rapport agrège les données publiques Géorisques (BRGM / MTE). "
        "Il ne remplace pas l'État des Risques (ERRIAL) obligatoire à la vente/location."
    )
