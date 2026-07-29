"""Forme documentaire du JSON produit par collector_agent.collect()."""

from __future__ import annotations

from typing import Any, TypedDict


class ErreurSource(TypedDict):
    source: str
    erreur: str


class BuildingData(TypedDict, total=False):
    adresse: dict[str, Any]
    departement: str
    departement_nom: str | None
    dans_perimetre_paca: bool
    altitude_m: float | None
    bdnb: dict[str, Any] | None
    georisques: dict[str, Any]
    climat: dict[str, Any]
    dvf_local: list[dict[str, Any]] | None
    erreurs: list[ErreurSource]
    genere_le: str
