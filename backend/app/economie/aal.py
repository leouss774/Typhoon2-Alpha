"""
F-C3 — Perte Annuelle Moyenne (AAL), repli fourchette publiée.

Formule complète (F-C1/F-C2 du doc : FEMA 2018, Gnan et al. 2022) :
    AAL = ∫ / somme de classes de probabilité × perte(profondeur) × V
    exige des profondeurs par scénario de période de retour.

Limite honnête assumée (doc §3.4) : aucune profondeur d'inondation n'est
disponible par adresse dans le projet (pas de modèle hydraulique). On
n'invente PAS de profondeur : on affiche le repli F-C3 —

    AAL ∈ [0,47 % ; 0,98 %] × V_reconstruction   par an, en zone inondable

— fourchette médiane publiée pour une maison unifamiliale en zone A
(100 ans), explicitement marquée `fourchette` avec réserve de
transposabilité (littérature US). Sans courbe profondeur-dommage,
l'effet d'une mesure ne peut pas y être appliqué : le bénéfice AAL d'une
mesure reste QUALITATIF (F-C4), jamais chiffré en l'absence de cote.
"""

from __future__ import annotations

from typing import Any

from app.economie.schemas import FOURCHETTE, NULL, bloc, bloc_null
from app.economie.sources import source_refs

# Fourchette médiane AAL / valeur de remplacement / an, zone A (100 ans).
_AAL_MIN_PCT = 0.0047
_AAL_MAX_PCT = 0.0098


def _aliment_inondation_present(building_data: dict[str, Any]) -> bool:
    georisques = building_data.get("georisques") or {}
    catnat = georisques.get("catnat") or {}
    if isinstance(catnat, list):
        data = catnat
    elif isinstance(catnat, dict):
        data = catnat.get("data")
    else:
        data = None
    if isinstance(data, list):
        for a in data:
            if "inondation" in str(a.get("libelle_risque_jo") or "").lower():
                return True
    zi = georisques.get("zones_inondables")
    if isinstance(zi, dict):
        inner = zi.get("data")
        if isinstance(inner, list):
            return len(inner) > 0
        return bool(zi)
    if isinstance(zi, list):
        return len(zi) > 0
    return bool(zi)


def aal_inondation(valeur: dict[str, Any], building_data: dict[str, Any]) -> dict[str, Any]:
    """AAL annuel en zone inondable (F-C3). Retourne un bloc standard."""
    valeur_bloc = valeur.get("valeur_reconstruction")
    if valeur_bloc is None or valeur_bloc.get("statut") == NULL:
        return bloc_null(
            "valeur du bien non déterminée → l'AAL (fourchette % de la valeur) "
            "ne peut pas être calculé"
        )

    if not _aliment_inondation_present(building_data):
        return bloc_null(
            "aucun aléa inondation identifié sur la commune (arrêtés CATNAT / "
            "zone inondable) → AAL inondation non applicable"
        )

    v = valeur_bloc["valeur"]
    return bloc(
        statut=FOURCHETTE,
        min=round(_AAL_MIN_PCT * v, 2),
        max=round(_AAL_MAX_PCT * v, 2),
        sources=source_refs("IJER2024", "FEMA2018"),
        hypotheses=[
            "fourchette médiane publiée d'AAL en zone A (100 ans) — littérature US, "
            "transposée en ORDRE DE GRANDEUR avec réserve de transposabilité en France",
            "sans profondeur d'inondation réelle (pas de PPRI/cote), l'effet d'une "
            "mesure sur l'AAL reste qualitatif (F-C4) et n'est pas chiffré",
        ],
        confidence=40,
    )
