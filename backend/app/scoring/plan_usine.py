"""
Niveau 2 — Analyse fine avec plan d'usine.

Reçoit les équipements critiques et les zones personnalisées de l'usine
(import DXF/GeoJSON ou formulaire manuel) et calcule une vulnérabilité
spécifique par zone, qui enrichit le score de risque du niveau 1.

Le plan est OPTIONNEL : sans plan, le score du niveau 1 reste valide.
Avec plan, la vulnérabilité est affinée et le score de confiance augmente.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.scoring.risk_model import _clamp, _combine_risk, _niveau

logger = get_logger(__name__)

# Sensibilité par type d'équipement (0-100)
SENSIBILITE_EQUIPEMENT = {
    "machine_outil": 70,
    "ligne_production": 80,
    "four": 75,
    "compresseur": 50,
    "groupe_froid": 60,
    "pompe": 45,
    "chaudiere": 70,
    "reservoir": 65,
    "cuve": 75,
    "silo": 60,
    "pont_roulant": 55,
    "robot": 65,
    "automate": 70,
    "serveur": 85,
    "laboratoire": 60,
    "autre": 50,
}

# Poids par type de zone (0-100)
POIDS_ZONE = {
    "production": 0.35,
    "stockage": 0.25,
    "bureaux": 0.10,
    "cuves": 0.20,
    "expedition": 0.10,
}

# Libellés français par type de zone
TYPE_ZONE_LABELS = {
    "production": "de production",
    "stockage": "de stockage",
    "bureaux": "de bureaux",
    "cuves": "de cuves / réservoirs",
    "expedition": "d'expédition",
}


def _sensibilite_equipement(equipement: dict[str, Any]) -> float:
    """Calcule la sensibilité d'un équipement (0-100)."""
    type_eq = str(equipement.get("type", "autre")).lower()
    base = SENSIBILITE_EQUIPEMENT.get(type_eq, SENSIBILITE_EQUIPEMENT["autre"])

    # Bonus selon la valeur de l'équipement
    valeur = equipement.get("valeur_remplacement_eur")
    if isinstance(valeur, (int, float)):
        if valeur > 1_000_000:
            base += 15
        elif valeur > 500_000:
            base += 10
        elif valeur > 100_000:
            base += 5

    # Bonus si matières dangereuses
    if equipement.get("matieres_dangereuses"):
        base += 15

    # Bonus si critique pour la production
    if equipement.get("critique_production"):
        base += 10

    return _clamp(base)


def _vulnerabilite_zone(
    zone: dict[str, Any],
    equipements: list[dict[str, Any]],
) -> tuple[float, str, list[str]]:
    """Calcule la vulnérabilité d'une zone (0-100) à partir de ses équipements.

    Retourne (vulnerabilite, description, sources).
    """
    type_zone = str(zone.get("type", "production")).lower()
    poids = POIDS_ZONE.get(type_zone, 0.20)
    type_label = TYPE_ZONE_LABELS.get(type_zone, "mixte")
    nom = zone.get("nom") or zone.get("id", type_zone)

    # Vulnérabilité de base selon le type de zone
    v_base = {
        "production": 55,
        "stockage": 50,
        "bureaux": 30,
        "cuves": 65,
        "expedition": 40,
    }.get(type_zone, 50)

    # Équipements de la zone
    eq_zone = [e for e in equipements if e.get("zone") == zone.get("id")]

    phrases: list[str] = []
    sources: list[str] = []

    if not eq_zone:
        v_final = v_base
        phrases.append(
            f"Zone {type_label} « {nom} » sans équipement déclaré : "
            f"vulnérabilité de base {v_final:.0f}/100 pour ce type de zone."
        )
        sources.append(f"plan_usine.zone.{zone.get('id', '?')}")
        return v_final, " ".join(phrases), sources

    # Vulnérabilité = moyenne pondérée des sensibilités des équipements
    sensibilites = [_sensibilite_equipement(e) for e in eq_zone]
    v_eq = sum(sensibilites) / len(sensibilites)

    # Combinaison : base + équipements
    v_final = v_base * (1 - poids) + v_eq * poids

    # Description narrative de la zone
    phrases.append(
        f"Zone {type_label} « {nom} » : vulnérabilité estimée à {v_final:.0f}/100 "
        f"(base {v_base:.0f}/100 pour ce type de zone, renforcée par {len(eq_zone)} équipement(s))."
    )

    surface = zone.get("surface_m2")
    if isinstance(surface, (int, float)) and surface > 0:
        phrases.append(f"Elle s'étend sur {surface:,.0f} m².".replace(",", " "))

    phrases.append(f"Sensibilité moyenne des équipements : {v_eq:.0f}/100.")

    dangereux = [e for e in eq_zone if e.get("matieres_dangereuses")]
    if dangereux:
        noms = ", ".join(str(e.get("nom") or e.get("type", "équipement")) for e in dangereux)
        phrases.append(
            f"{len(dangereux)} équipement(s) implique(nt) des matières dangereuses "
            f"(risque d'incendie, d'explosion ou de pollution) : {noms}."
        )

    critiques = [e for e in eq_zone if e.get("critique_production")]
    if critiques:
        noms = ", ".join(str(e.get("nom") or e.get("type", "équipement")) for e in critiques)
        phrases.append(
            f"{len(critiques)} équipement(s) est (sont) critique(s) pour la production : "
            f"{noms}."
        )

    sources.append(f"plan_usine.zone.{zone.get('id', '?')}")
    return _clamp(v_final), " ".join(phrases), sources


def enrichir_avec_plan(
    risk_scores: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Enrichit les risk_scores du niveau 1 avec le plan d'usine (niveau 2).

    Parameters
    ----------
    risk_scores : dict
        Résultat de compute_risk_scores() (niveau 1).
    plan : dict
        {equipements: [...], zones: [...], nom_usine: str}

    Retourne les risk_scores enrichis avec :
      - zones_plan : dict des zones personnalisées avec vulnérabilité spécifique
      - score_plan_global : int (0-100)
      - confiance_plan : dict (score de confiance enrichi)
    """
    equipements = plan.get("equipements", []) or []
    zones = plan.get("zones", []) or []
    nom_usine = plan.get("nom_usine", "Usine")

    if not zones:
        logger.info("plan_usine -- aucun zone déclarée, plan ignoré")
        return risk_scores

    logger.info(
        "plan_usine -- enrichissement avec %d zone(s) et %d équipement(s) pour %r",
        len(zones), len(equipements), nom_usine,
    )

    # Calcul de la vulnérabilité par zone
    zones_plan: dict[str, dict[str, Any]] = {}
    v_scores: list[float] = []
    for zone in zones:
        zone_id = str(zone.get("id", f"zone_{len(zones_plan)}"))
        v_zone, description, sources = _vulnerabilite_zone(zone, equipements)

        # Risque = combinaison F (aléa global du bâtiment) × V (vulnérabilité zone)
        f_global = risk_scores.get("score_global", 50)
        risque_zone = _clamp(_combine_risk(f_global, v_zone))

        zones_plan[zone_id] = {
            "nom": zone.get("nom", zone_id),
            "type": zone.get("type", "production"),
            "surface_m2": zone.get("surface_m2"),
            "vulnerabilite": v_zone,
            "risque": risque_zone,
            "niveau": _niveau(risque_zone),
            "description": description,
            "justification": description,
            "equipements": [e for e in equipements if e.get("zone") == zone_id],
            "sources": sources,
        }
        v_scores.append(v_zone)

    # Score global du plan = moyenne pondérée des risques des zones
    if v_scores:
        score_plan = _clamp(sum(z["risque"] for z in zones_plan.values()) / len(zones_plan))
    else:
        score_plan = risk_scores.get("score_global", 0)

    # Confiance enrichie : +15 pts si plan fourni (données plus complètes)
    confiance_base = risk_scores.get("confidence", {})
    score_confiance = _clamp((confiance_base.get("score", 0) or 0) + 15)
    niveau_confiance = (
        "elevee" if score_confiance >= 80
        else "bonne" if score_confiance >= 60
        else "moyenne" if score_confiance >= 40
        else "faible"
    )

    return {
        **risk_scores,
        "plan_usine": {
            "nom_usine": nom_usine,
            "zones_plan": zones_plan,
            "score_plan_global": score_plan,
            "nb_equipements": len(equipements),
            "nb_zones": len(zones),
            "confiance_plan": {
                "score": score_confiance,
                "niveau": niveau_confiance,
                "message": "Confiance augmentée grâce au plan d'usine fourni",
            },
        },
    }