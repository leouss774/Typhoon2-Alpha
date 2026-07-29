"""TyphoonState — état partagé entre les noeuds du StateGraph LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict


class TyphoonState(TypedDict, total=False):
    # Entrée
    adresse: str
    formulaire: dict[str, Any] | None
    copernicus: bool

    # Ecrit par collector_agent
    building_data: dict[str, Any]

    # Ecrit par scoring_agent
    risk_scores: dict[str, Any]

    # Ecrit par bank_decision
    bank_decision: dict[str, Any]

    # Ecrit par digital_twin_agent (sortie finale)
    digital_twin: dict[str, Any]
