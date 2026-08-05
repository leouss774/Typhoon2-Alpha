"""
F-B1 — Valeur de reconstruction / valeur de marché (ancre en €).

Formule (doc §3.1 et F-B1) :
    V = S × c
    S = surface_m2 (géométrie BDNB, réelle) ; c = coût unitaire €/m²
    Repli honnête : c = prix au m² médian DVF réel de la commune
    (collector_agent -> building_data.dvf_local).

Si ni surface ni prix au m² DVF ne sont disponibles -> `null` (pas de
valeur -> les niveaux B/C/ROI ne produisent aucun montant en €, seul le
Δ de score du niveau A reste affiché).
"""

from __future__ import annotations

from typing import Any

from app.economie.schemas import CALCULE, NULL, bloc, bloc_null
from app.economie.sources import source_refs

# Mêmes filtres que dvf_lookup._filtrer_ventes_valides / _TYPES_PRIX_M2
# (app/connectors/dvf_lookup.py) : ventes Maison/Appartement uniquement,
# surface plancher 9 m², prix au m² écrêté des aberrations.
_TYPES_PRIX_M2 = {"Maison", "Appartement"}
_SURFACE_MIN_M2 = 9.0
_PRIX_M2_BORNES = (200.0, 30000.0)


def _prix_m2_median(dvf_local: list[dict[str, Any]]) -> float | None:
    """Médiane du prix au m² des ventes réelles de la commune (DVF local)."""
    prix: list[float] = []
    for tx in dvf_local or []:
        if str(tx.get("nature_mutation") or "").strip() != "Vente":
            continue
        if tx.get("type_local") not in _TYPES_PRIX_M2:
            continue
        try:
            valeur = float(tx.get("valeur_fonciere"))
            surface = float(tx.get("surface_reelle_bati"))
        except (TypeError, ValueError):
            continue
        if valeur <= 0 or surface < _SURFACE_MIN_M2:
            continue
        p = valeur / surface
        if _PRIX_M2_BORNES[0] <= p <= _PRIX_M2_BORNES[1]:
            prix.append(p)
    if not prix:
        return None
    prix.sort()
    mid = len(prix) // 2
    if len(prix) % 2 == 1:
        return prix[mid]
    return (prix[mid - 1] + prix[mid]) / 2.0


def _surface_m2(building_data: dict[str, Any], surface_m2: float | None) -> float | None:
    """Surface disponible : paramètre explicite (géométrie du jumeau, emprise
    au sol) puis champs surface de la BDNB."""
    if isinstance(surface_m2, (int, float)) and surface_m2 > 0:
        return float(surface_m2)
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    if isinstance(batiment, dict):
        for champ in ("surface_emprise_sol", "s_geom_groupe"):
            v = batiment.get(champ)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    return None


def _confidence(nb_ventes: int, surface_dispo: bool) -> int | None:
    if nb_ventes >= 10 and surface_dispo:
        return 80
    if nb_ventes >= 3 and surface_dispo:
        return 65
    if surface_dispo:
        return 45
    return None


def estimer_valeur(building_data: dict[str, Any], surface_m2: float | None = None) -> dict[str, Any]:
    """Calcule la valeur du bien selon F-B1.

    Retourne un dict :
      {
        "surface_m2": float | None,
        "nb_transactions_dvf": int,
        "prix_m2_median": bloc | None,
        "valeur_reconstruction": bloc | None,   # ancre en €, ou null
        "statut": calcule|null,
      }
    """
    dvf_local = building_data.get("dvf_local")
    nb_transactions = len(dvf_local or [])
    surface = _surface_m2(building_data, surface_m2)

    prix_median = _prix_m2_median(dvf_local) if isinstance(dvf_local, list) else None

    # 1) Prix au m² médian réel (bloc informationnel, pas un montant global).
    prix_bloc = None
    if prix_median is not None:
        prix_bloc = bloc(
            statut=CALCULE,
            valeur=round(prix_median),
            min=round(prix_median),
            max=round(prix_median),
            sources=source_refs("DVF"),
            hypotheses=[
                "médiane du prix au m² des ventes Maison/Appartement de la commune "
                f"(DVF, {nb_transactions} transaction(s) collectée(s))"
            ],
            confidence=45 if nb_transactions >= 3 else 30,
        )

    # 2) Valeur globale (ancre en €) : exige surface + prix au m².
    if prix_median is None:
        valeur = bloc_null(
            "aucune transaction DVF exploitable sur la commune (ou DVF désactivé) "
            "→ aucun prix au m² réel disponible"
        )
    elif surface is None:
        valeur = bloc_null(
            "prix au m² DVF disponible mais surface du bien non déterminée "
            "(géométrie/BDNB absente) → pas de valeur globale"
        )
    else:
        valeur = bloc(
            statut=CALCULE,
            valeur=round(prix_median * surface),
            min=round(prix_median * surface),
            max=round(prix_median * surface),
            sources=source_refs("DVF", "HAZUS_METHODE"),
            hypotheses=[
                "surface = emprise au sol du bâtiment (proxy BDNB), pas la surface "
                "habitable — valeur de MARCHÉ, pas valeur de reconstruction"
            ],
            confidence=_confidence(nb_transactions, True),
        )

    return {
        "surface_m2": surface,
        "nb_transactions_dvf": nb_transactions,
        "prix_m2_median": prix_bloc,
        "valeur_reconstruction": valeur,
        "statut": NULL if valeur.get("statut") == NULL else CALCULE,
    }
