"""
Property ID Generator — construit l'objet Property ID à partir des
données existantes du diagnostic.

Respecte le principe fondamental : aucune nouvelle donnée métier n'est
créée ici. Seulement de l'agrégation et de l'organisation des sorties
des agents existants (collector_agent → building_data, scoring_agent →
risk_scores, digital_twin_agent → digital_twin, recommandations_agent →
recommandations).

Architecture (cf. README racine, section "Backend — communication
inter-agents") :
  - Reçoit le state final (TyphoonState) complet après exécution du
    graphe LangGraph.
  - Extrait et réorganise les clés pertinentes dans la structure
    PropertyID (voir schemas.py).
  - Calcule les métadonnées (ID unique, résumé des risques, timeline).

Génération de l'ID unique :
  Format : TY-{année}-{numéro séquentiel 6 chiffres}
  Exemple : TY-2026-000001
  Le compteur est thread-safe (threading.Lock) et persistant via
  le service (fichier JSON).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.property_id.certification.service import generate_certification
from app.property_id.schemas import (
    BuildingInfo,
    FutureModules,
    PropertyID,
    RiskSummary,
    Scores,
    TimelineEvent,
)

logger = get_logger(__name__)

_id_lock = threading.Lock()
_sequence_counter: int = 0


def set_sequence(counter: int) -> None:
    """Définit la valeur initiale du compteur séquentiel.
    Appelé au démarrage par init_service()."""
    with _id_lock:
        global _sequence_counter  # noqa: PLW0603
        _sequence_counter = counter


def _next_property_id() -> str:
    """Génère le prochain identifiant unique TY-YYYY-NNNNNN.

    Thread-safe via _id_lock. Incrémente le compteur, formate l'ID.
    """
    with _id_lock:
        global _sequence_counter  # noqa: PLW0603
        _sequence_counter += 1
        seq = _sequence_counter

    year = datetime.now(timezone.utc).strftime("%Y")
    return f"TY-{year}-{seq:06d}"


def _get_current_sequence() -> int:
    """Retourne la valeur actuelle du compteur (lecture seule)."""
    with _id_lock:
        return _sequence_counter


def generate(
    building_data: dict[str, Any],
    risk_scores: dict[str, Any],
    digital_twin: dict[str, Any],
) -> PropertyID:
    """Génère un Property ID complet à partir des sorties des agents.

    Paramètres
    ----------
    building_data : dict
        Sortie du collector_agent (adresse, bdnb, georisques, climat...).
    risk_scores : dict
        Sortie du scoring_agent (score_global, zones, projection_2050).
    digital_twin : dict
        Contrat final du digital_twin_agent (geometry, bien, adresse...).

    Retourne
    -------
    PropertyID
        Le Property ID complet, avec certification et timeline.
    """
    logger.info("property_id.generator — génération du Property ID")

    now = datetime.now(timezone.utc).isoformat()
    pid = _next_property_id()

    # --- Extraction des données source ---
    adresse_info = building_data.get("adresse", {}) or {}
    bdnb = building_data.get("bdnb") or {}
    batiment = bdnb.get("batiment") if isinstance(bdnb, dict) else bdnb
    if not isinstance(batiment, dict):
        batiment = {}

    geometry = digital_twin.get("geometry", {}) or {}
    bien = digital_twin.get("bien", {}) or {}

    # --- Champs bâtiment ---
    construction_year = batiment.get("annee_construction") or bien.get("annee_construction")
    building_type = bien.get("type") or batiment.get("usage_niveau_1_txt")
    materials = geometry.get("materiau_mur")
    floors = geometry.get("floors_count")

    # Toiture : éviter le "(None)" dans le formatage
    roof_shape = geometry.get("roof_shape")
    roof_material = geometry.get("materiau_toiture")
    if roof_shape and roof_material:
        roof = f"{roof_shape} ({roof_material})"
    elif roof_shape:
        roof = roof_shape
    else:
        roof = None

    building = BuildingInfo(
        address=adresse_info.get("label") or digital_twin.get("adresse", ""),
        construction_year=construction_year,
        building_type=building_type,
        materials=materials,
        floors=floors,
        roof=roof,
        geometry=geometry,
    )

    # --- Scores ---
    overall = risk_scores.get("score_global", 0)
    climate = risk_scores.get("projection_2050", {}).get("score_global", 0)
    insurance = overall  # MVP : insurance = overall

    scores = Scores(
        overall=overall,
        climate=climate,
        insurance=insurance,
    )

    # --- Résumé des risques ---
    zones = risk_scores.get("zones", {}) or {}
    highest_risk_zone = max(
        zones,
        key=lambda z: zones[z].get("score", 0),
    ) if zones else None

    risk_summary = RiskSummary(
        highest_risk=highest_risk_zone or "N/A",
        risk_level=risk_scores.get("niveau_risque", "N/A"),
        main_hazard=risk_scores.get("alea_principal", "N/A"),
    )

    # --- Recommandations (aggregation de toutes les zones) ---
    recommendations: list[dict[str, Any]] = []
    for zone_name, zone_data in zones.items():
        recos = zone_data.get("recommandations", []) or []
        for r in recos:
            if isinstance(r, dict):
                r["zone"] = zone_name
            recommendations.append(r)

    # --- Timeline ---
    timeline: list[TimelineEvent] = [
        TimelineEvent(
            date=now,
            event="Property ID créé",
            details={
                "property_id": pid,
                "adresse": building.address,
            },
        ),
    ]

    # --- Certification ---
    certification = generate_certification(building_data, risk_scores, digital_twin)
    if certification is not None:
        timeline.append(
            TimelineEvent(
                date=certification.issued_at,
                event=f"Certification {certification.level.value}",
                details={
                    "level": certification.level.value,
                    "score": certification.score,
                    "status": certification.status.value,
                },
            ),
        )

    return PropertyID(
        property_id=pid,
        generated_at=now,
        building=building,
        scores=scores,
        risk_summary=risk_summary,
        recommendations=recommendations,
        digital_twin=digital_twin,
        timeline=timeline,
        certification=certification,
        future_modules=FutureModules(),
    )
