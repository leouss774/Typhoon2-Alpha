"""Fixtures partagées pour les tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def client_form_example() -> dict:
    """Formulaire client type pour les tests."""
    return {
        "adresse": "15 Rue des Lilas, 33140 Villenave-d'Ornon",
        "type_bien": "maison",
        "surface_m2": 120,
        "annee_construction": 1985,
        "materiau_principal": "brique",
        "sous_sol": True,
        "nombre_niveaux": 2,
    }


@pytest.fixture
def raw_data_example() -> dict:
    """Données brutes type pour les tests."""
    return {
        "exposition_argile": 0.85,
        "zone_ppri": "moyen",
        "zone_vent": 3,
        "proximite_foret_m": 300,
        "altitude_m": 15,
        "distance_cote_km": 60,
    }


@pytest.fixture
def scores_example() -> dict:
    """Scores d'exemple pour les tests."""
    return {
        "rga": 82.0,
        "inondation": 45.0,
        "tempete": 30.0,
        "feu_foret": 15.0,
        "submersion": 5.0,
    }
