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


def _sensibilite_equipement(equipement: dict[str, Any]) -> int:
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


def _zone_aliases(zone: dict[str, Any]) -> set[str]:
    """Ensemble des identifiants sous lesquels une zone peut être référencée
    par un équipement : son `id` ET son `nom` (le VLM renvoie souvent le nom
    de la zone dans `equipements[].zone`). La comparaison est insensible à la
    casse et aux espaces superflus."""
    aliases: set[str] = set()
    for key in ("id", "nom"):
        value = zone.get(key)
        if isinstance(value, str) and value.strip():
            aliases.add(value.strip().lower())
    return aliases


def _attribuer_equipement(equipement: dict[str, Any], zones: list[dict[str, Any]]) -> str | None:
    """Résout la zone d'un équipement vers un identifiant de zone.

    L'équipement référence sa zone par `zone` (nom ou id, comme le renvoie le
    VLM) ; on cherche parmi les `zones` une correspondance par `id` ou `nom`.
    Retourne l'id de la zone, ou None si aucune zone ne correspond.
    """
    ref = equipement.get("zone")
    if not isinstance(ref, str) or not ref.strip():
        return None
    ref_norm = ref.strip().lower()
    for zone in zones:
        if ref_norm in _zone_aliases(zone):
            return str(zone.get("id", f"zone_{zones.index(zone)}"))
    return None


def _enrichir_equipement(
    equipement: dict[str, Any],
    zone_id: str | None,
    f_global: int,
    v_zone: int | None = None,
) -> dict[str, Any]:
    """Enrichit un équipement avec sa sensibilité et son score de risque.

    R = 100 × (F/100)^0.5 × (V_eq/100)^0.5 — même moteur que le scoring des
    zones (risk_model._combine_risk). V_eq = sensibilité de l'équipement,
    éventuellement atténuée par la vulnérabilité de la zone d'accueil.
    """
    sensibilite = _sensibilite_equipement(equipement)
    if v_zone is not None:
        v_eq = sensibilite * 0.6 + v_zone * 0.4
    else:
        v_eq = sensibilite
    risque = _clamp(_combine_risk(f_global, v_eq))
    return {
        **equipement,
        "zone_id": zone_id,
        "sensibilite": sensibilite,
        "risque": risque,
        "niveau": _niveau(risque),
    }


def _vulnerabilite_zone(
    zone: dict[str, Any],
    equipements: list[dict[str, Any]],
    equipements_zone: list[dict[str, Any]],
) -> tuple[int, str, list[str]]:
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

    eq_zone = equipements_zone

    phrases: list[str] = []
    sources: list[str] = []

    if not eq_zone:
        v_final = v_base
        phrases.append(
            f"Zone {type_label} « {nom} » sans équipement déclaré : "
            f"vulnérabilité de base {v_final:.0f}/100 pour ce type de zone."
        )
        sources.append(f"plan_usine.zone.{zone.get('id', '?')}")
        return _clamp(v_final), " ".join(phrases), sources

    # Vulnérabilité = moyenne pondérée des sensibilités des équipements
    sensibilites = [e.get("sensibilite") or _sensibilite_equipement(e) for e in eq_zone]
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


def compute_usine_risk(
    plan: dict[str, Any],
    risk_scores: dict[str, Any] | None = None,
    aleas_site: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcule le risque complet d'une usine à partir de son plan (niveau 2).

    Même méthodologie que le scoring des zones (D05) : chaque zone et chaque
    équipement combine F (aléa du site) × V (vulnérabilité) via la moyenne
    géométrique non-compensatoire R = 100 × (F/100)^0.5 × (V/100)^0.5.

    Parameters
    ----------
    plan : dict
        {equipements: [...], zones: [...], nom_usine: str}
    risk_scores : dict | None
        Résultat de compute_risk_scores() (niveau 1). Sans plan, `score_global`
        vaut 50 (aléa du site par défaut) sauf si `aleas_site` est fourni.
    aleas_site : dict | None
        Contexte d'aléa du site (ex. maxScore du RisqueReport Géorisques) :
        {score: int, libelle: str} — remplace le score global par défaut.

    Retourne le contrat complet consommé par le frontend /usine :
      - nom_usine, nb_zones, nb_equipements
      - score_global : int (0-100)
      - zones : list (vulnérabilité / risque / niveau / description / équipements enrichis)
      - equipements : list (sensibilité / risque / niveau / zone_id)
      - confiance : dict (score, niveau, message)
      - aleas_site : dict | None
      - plan_usine : dict (compatibilité ascendante)
    """
    risk_scores = risk_scores or {}
    equipements = plan.get("equipements", []) or []
    zones = plan.get("zones", []) or []
    nom_usine = plan.get("nom_usine", "Usine")

    if not zones:
        logger.info("plan_usine -- aucun zone déclarée, plan ignoré")
        return {
            "nom_usine": nom_usine,
            "nb_zones": 0,
            "nb_equipements": len(equipements),
            "score_global": risk_scores.get("score_global", aleas_site.get("score", 50) if aleas_site else 50),
            "zones": [],
            "equipements": [],
            "confiance": risk_scores.get("confidence", {"score": 0, "niveau": "indetermine"}),
            "aleas_site": aleas_site,
            "plan_usine": {"nom_usine": nom_usine, "zones_plan": {}, "nb_equipements": len(equipements), "nb_zones": 0},
        }

    logger.info(
        "plan_usine -- enrichissement avec %d zone(s) et %d équipement(s) pour %r",
        len(zones), len(equipements), nom_usine,
    )

    # F (aléa global du site) : score fourni explicitement, sinon contexte d'aléa
    # Géorisques, sinon valeur neutre.
    if risk_scores.get("score_global") is not None:
        f_global = int(risk_scores["score_global"])
    elif aleas_site and aleas_site.get("score") is not None:
        f_global = int(aleas_site["score"])
    else:
        f_global = 50

    # Résolution de la zone de chaque équipement (id OU nom) + enrichissement.
    equipements_enrichis: list[dict[str, Any]] = []
    equipements_par_zone: dict[str, list[dict[str, Any]]] = {}
    for eq in equipements:
        zone_id = _attribuer_equipement(eq, zones)
        eq_enrichi = _enrichir_equipement(eq, zone_id, f_global)
        equipements_enrichis.append(eq_enrichi)
        if zone_id is not None:
            equipements_par_zone.setdefault(zone_id, []).append(eq_enrichi)

    # Calcul de la vulnérabilité et du risque par zone.
    zones_plan: dict[str, dict[str, Any]] = {}
    for idx, zone in enumerate(zones):
        zone_id = str(zone.get("id", f"zone_{idx}"))
        eq_zone = equipements_par_zone.get(zone_id, [])
        v_zone, description, sources = _vulnerabilite_zone(zone, equipements, eq_zone)
        risque_zone = _clamp(_combine_risk(f_global, v_zone))

        zones_plan[zone_id] = {
            "id": zone_id,
            "nom": zone.get("nom", zone_id),
            "type": zone.get("type", "production"),
            "surface_m2": zone.get("surface_m2"),
            "vulnerabilite": v_zone,
            "risque": risque_zone,
            "niveau": _niveau(risque_zone),
            "description": description,
            "justification": description,
            "equipements": [e.get("id") for e in eq_zone],
            "sources": sources,
        }

    # Score global du plan = moyenne des risques des zones.
    score_plan = _clamp(sum(z["risque"] for z in zones_plan.values()) / max(len(zones_plan), 1))

    # Confiance : base du niveau 1 (si disponible) sinon 40 (le plan fourni est
    # déjà un signal fort), puis bonus de complétude du plan (+15 si plan fourni,
    # +couverture surfaces / valeurs / attributs métiers).
    confiance_base = risk_scores.get("confidence", {})
    base_confiance = confiance_base.get("score", 40) or 40
    score_confiance = _clamp(base_confiance + 15)
    score_confiance = _clamp(
        score_confiance
        + (10 if all(z.get("surface_m2") for z in zones) else 0)
        + (10 if equipements and all(e.get("valeur_remplacement_eur") is not None for e in equipements) else 0)
        + (5 if equipements and all(e.get("critique_production") is not None or e.get("matieres_dangereuses") is not None for e in equipements) else 0)
    )
    niveau_confiance = (
        "elevee" if score_confiance >= 80
        else "bonne" if score_confiance >= 60
        else "moyenne" if score_confiance >= 40
        else "faible"
    )

    return {
        "nom_usine": nom_usine,
        "nb_zones": len(zones),
        "nb_equipements": len(equipements),
        "score_global": score_plan,
        "aleas_site": aleas_site,
        "zones": list(zones_plan.values()),
        "equipements": equipements_enrichis,
        "confiance": {
            "score": score_confiance,
            "niveau": niveau_confiance,
            "message": "Confiance augmentée grâce au plan d'usine fourni",
        },
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


def enrichir_avec_plan(
    risk_scores: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Enrichit les risk_scores du niveau 1 avec le plan d'usine (niveau 2).

    Point d'entrée historique : délègue au nouveau `compute_usine_risk` et
    fusionne le résultat dans `risk_scores` (compatibilité ascendante).
    """
    resultat = compute_usine_risk(plan, risk_scores)
    return {**risk_scores, **resultat}