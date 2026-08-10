"""
Forme documentaire du JSON produit par collector_agent.collect().

Volontairement un TypedDict (pas un modele Pydantic strict) : les
sous-reponses (Georisques, BDNB...) sont du JSON externe dont la forme
exacte peut varier ; on documente la structure sans risquer de faire
echouer l'agrégation sur un champ manquant chez un fournisseur tiers.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ErreurSource(TypedDict):
    source: str
    erreur: str


class BuildingData(TypedDict, total=False):
    adresse: dict[str, Any]  # label, citycode, postcode, city, score, lat, lon
    departement: str
    departement_nom: str | None
    dans_perimetre_paca: bool
    altitude_m: float | None
    bdnb: dict[str, Any] | None
    georisques: dict[str, Any]
    climat: dict[str, Any]
    dvf_local: list[dict[str, Any]] | None
    drias_local: list[dict[str, Any]] | None
    erreurs: list[ErreurSource]
    genere_le: str
