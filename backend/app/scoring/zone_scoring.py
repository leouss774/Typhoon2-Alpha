"""
Zone Risk Assessment — orchestration et agrégation multi-points (Person 1).

Point d'entrée principal : run_zone_risk_assessment(zone_geometry)

Logique :
  1. Génération d'une grille d'échantillonnage régulière dans les bounds
  2. Pour chaque point, construction d'un building_data MINIMAL (sans appels API
     externes, qui sont souvent bloqués dans les sandbox de dev)
  3. Scoring individuel via score_address()
  4. Agrégation en distributions par péril + worst-case + rating global
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone


from app.scoring.risk_model import compute_risk_scores

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#   Modèles de données
# ---------------------------------------------------------------------------

@dataclass
class PointEchantillon:
    """Un point d'échantillonnage dans la zone."""
    index: int
    lat: float
    lon: float
    adresse_approx: str | None = None
    score: dict | None = None  # Résultat de compute_risk_scores()
    erreur: str | None = None


@dataclass
class DistributionPeril:
    """Distribution des scores d'un péril sur l'ensemble des points."""
    scores: list[float]
    min_score: float
    max_score: float
    moyenne: float
    mediane: float
    ecart_type: float
    pct_faible: float       # % de points en risque faible (<20)
    pct_modere: float       # % de points en risque modéré (20-44)
    pct_eleve: float        # % de points en risque élevé (45-69)
    pct_critique: float     # % de points en risque critique (>=70)
    worst_case: float       # score maximal observé


@dataclass
class RatingZone:
    """Résultat agrégé pour une zone complète."""
    nb_points: int
    nb_points_valides: int = 0
    nb_points_erreur: int = 0
    score_moyen: float = 0.0
    score_pondere: float = 0.0
    rating_global: str = "Non evaluable"
    perils: dict[str, DistributionPeril] = field(default_factory=dict)
    worst_case_peril: str | None = None
    worst_case_score: float | None = None
    points_echantillon: list[dict] = field(default_factory=list)
    land_only: bool = False
    message: str | None = None


# ---------------------------------------------------------------------------
#   Grille d'échantillonnage
# ---------------------------------------------------------------------------

def _generer_grille_rectangulaire(
    bounds: tuple[float, float, float, float],
    spacing_km: float = 0.5,
    max_points: int = 50,
) -> list[tuple[float, float]]:
    """Génère une grille de points dans les bounds."""
    lat_min, lon_min, lat_max, lon_max = bounds
    lat_moy = (lat_min + lat_max) / 2
    deg_per_km_lat = 1.0 / 111.0
    deg_per_km_lon = 1.0 / (111.0 * math.cos(math.radians(lat_moy)))
    step_lat = spacing_km * deg_per_km_lat
    step_lon = spacing_km * deg_per_km_lon

    points: list[tuple[float, float]] = []
    lat = lat_min
    while lat <= lat_max and len(points) < max_points:
        lon = lon_min
        while lon <= lon_max and len(points) < max_points:
            points.append((lat, lon))
            lon += step_lon
        lat += step_lat
    return points


# ---------------------------------------------------------------------------
#   Building data minimal (sans appels réseau)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#   Simulation géographique basée sur les coordonnées
#   (remplace les API externes dans les environnements sans accès réseau)
# ---------------------------------------------------------------------------

def _noise(lat: float, lon: float, seed: int = 0) -> float:
    """Bruit déterministe 0..1 à partir des coordonnées + graine."""
    h = math.sin(lat * 127.1 + lon * 311.7 + seed * 37.3) * 43758.5453
    return abs(h - math.floor(h))


def _niveau_alerte(score: float) -> str:
    if score >= 70:
        return "fort"
    if score >= 40:
        return "moyen"
    return "faible"


def _simuler_georisques(lat: float, lon: float) -> dict:
    """Simule les données Géorisques dans le format attendu par compute_risk_scores.

    Les clés correspondent exactement à ce que les sous-scores de risk_model.py
    attendent (libelle_risque_jo, risques_commune.data[].risques_detail[], etc.).
    Le bruit déterministe assure que 2 points proches ont des profils différents.
    """
    # --- Scores de base géographiques (pour toute la France) ---
    # Inondation : plus fort près des côtes basses
    inondation_base = 15.0
    if abs(lat) < 46:  # sud de la France
        inondation_base += max(0, (46 - abs(lat)) / 3) * 35
    elif abs(lat) < 49:
        inondation_base += max(0, (49 - abs(lat)) / 4) * 20
    inondation_score = inondation_base + (_noise(lat, lon, 1) - 0.5) * 55
    inondation_score = max(5, min(100, inondation_score))

    # RGA : plus fort dans les sols argileux (variable selon région)
    rga_base = 20.0 + (_noise(lat, lon, 2) - 0.5) * 60
    rga_score = max(5, min(100, rga_base))

    # Feu de forêt : plus fort dans le sud
    incendie_base = 8.0
    if abs(lat) < 45:
        incendie_base += min(1.0, (45 - abs(lat)) / 2) * 45
    incendie_score = incendie_base + (_noise(lat, lon, 3) - 0.5) * 50
    incendie_score = max(3, min(100, incendie_score))

    # Mouvement de terrain : aléatoire, lié à la géologie locale
    mvt_count = int(round(_noise(lat, lon, 9) * 4))

    # Radon : classe 1-3 selon la région
    radon_classe = 1 + int(_noise(lat, lon, 10) * 3)

    # --- CATNAT dans le FORMAT attendu par _count_catnat ---
    # La clé DOIT être "libelle_risque_jo" (pas libelle_catnat)
    catnat_data: list[dict] = []
    n_flood = int(1 + _noise(lat, lon, 4) * 6)
    for _ in range(n_flood):
        catnat_data.append({"libelle_risque_jo": "Inondation"})
    n_drought = int(0 + _noise(lat, lon, 11) * 5)
    for _ in range(n_drought):
        catnat_data.append({"libelle_risque_jo": "Sécheresse"})
    n_mvt = int(0 + _noise(lat, lon, 12) * 3)
    for _ in range(n_mvt):
        catnat_data.append({"libelle_risque_jo": "Mouvement de terrain"})

    # --- Risques commune dans le FORMAT attendu par _has_hazard ---
    risques_detail = []
    if inondation_score > 25:
        risques_detail.append({"libelle_risque_long": "Inondation", "type_risque": "Inondation"})
    if incendie_score > 25:
        risques_detail.append({"libelle_risque_long": "Feu de forêt", "type_risque": "Feu de forêt"})
    if rga_score > 30:
        risques_detail.append({"libelle_risque_long": "Retrait-gonflement des argiles", "type_risque": "Argiles"})

    # --- Zonage sismique dans le FORMAT attendu par _sismique_subscore ---
    # Doit être une liste de dicts avec "zone_sismicite"
    if lon > 7.0:
        zone_sismique = "4"      # Nice, Alpes-Maritimes
    elif lon > 6.5:
        zone_sismique = "3"      # Var est
    elif lon > 5.5:
        zone_sismique = "2"      # Bouches-du-Rhône
    elif lon > 4.0:
        zone_sismique = "2"      # Sud-Est
    elif lon > 2.0:
        zone_sismique = "1"      # Sud-Ouest / Centre
    else:
        zone_sismique = "1"

    return {
        "risques_commune": {
            "data": [{
                "risques_detail": risques_detail
            }]
        },
        "catnat": {"data": catnat_data},
        "zonage_sismique": [{"zone_sismicite": zone_sismique}],
        "cavites": [{"type": "cavité"}] * (1 if _noise(lat, lon, 13) > 0.45 else 0),
        "mouvements_de_terrain": [{"type": "glissement"}] * mvt_count,
        "zones_inondables": inondation_score > 35,
        "radon": [{"classe_potentiel": radon_classe}],
    }


def _simuler_altitude(lat: float, lon: float) -> float | None:
    """Simule l'altitude en mètres à partir des coordonnées (PACA)."""
    bruit = (_noise(lat, lon, 6) - 0.5) * 0.6 + 0.5  # recentré 0.2..0.8
    if lat < 43.3:
        # Littoral : 0-50m
        return round(3 + bruit * 45, 1)
    elif lat < 43.6:
        # Arrière-pays : 30-250m
        return round(25 + bruit * 220, 1)
    else:
        # Intérieur : 100-800m
        return round(80 + bruit * 700, 1)


def _simuler_climat(lat: float, lon: float) -> dict | None:
    """Simule des données climatiques Open-Meteo."""
    bruit1 = _noise(lat, lon, 7)
    bruit2 = _noise(lat, lon, 8)
    return {
        "reference_2015_2024": {
            "jours_chaleur_extreme_par_an": round(15 + bruit1 * 30, 1),
            "temperature_moyenne_annuelle": round(14.0 + (43.8 - lat) * 2 + bruit2 * 4, 1),
        },
        "projection_2041_2050": {
            "jours_chaleur_extreme_par_an": round(25 + bruit1 * 35, 1),
            "precipitation_annuelle_moyenne_mm": round(600 + bruit2 * 400, 1),
        },
    }


# ---------------------------------------------------------------------------
#   Building data minimal (sans appels réseau — avec simulation géographique)
# ---------------------------------------------------------------------------

def _building_data_minimal(lat: float, lon: float) -> dict:
    """Construit un building_data pour un point d'échantillonnage.

    N'appelle AUCUNE API externe. Utilise des simulations géographiques
    (basées sur lat/lon) pour produire des profils de risque variés et
    plausibles, différents pour chaque point de la grille.
    """
    georisques_sim = _simuler_georisques(lat, lon)
    altitude_sim = _simuler_altitude(lat, lon)
    climat_sim = _simuler_climat(lat, lon)

    # Code département depuis la latitude (approximatif)
    if lon > 7.0:
        dep, dep_nom = "06", "Alpes-Maritimes"
    elif lon > 6.0:
        dep, dep_nom = "83", "Var"
    elif lon > 5.5:
        dep, dep_nom = "13", "Bouches-du-Rhône"
    elif lon > 5.0:
        dep, dep_nom = "84", "Vaucluse"
    elif lon > 4.5:
        dep, dep_nom = "30", "Gard"
    else:
        dep, dep_nom = "13", "Bouches-du-Rhône"

    return {
        "adresse": {
            "label": f"{lat:.5f},{lon:.5f}",
            "citycode": "",
            "postcode": "",
            "city": "",
            "score_geocodage": 0.5,
            "lat": lat,
            "lon": lon,
        },
        "departement": dep,
        "departement_nom": dep_nom,
        "dans_perimetre_paca": True,
        "altitude_m": altitude_sim,
        "bdnb": None,
        "georisques": georisques_sim,
        "climat_open_meteo": climat_sim,
        "climat_copernicus": None,
        "dvf_local": None,
        "erreurs": [{"source": "zone_mode", "erreur": "Données simulées (mode zone sans API)"}],
        "genere_le": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
#   Collecte et scoring d'un point (sans appels réseau)
# ---------------------------------------------------------------------------

async def _collecter_point(
    lat: float,
    lon: float,
    land_only: bool,
    semaphore: asyncio.Semaphore,
    idx: int,
    collect_fn: Callable[[str], Awaitable[dict]] | None = None,
) -> PointEchantillon:
    """Collecte et score un point de la grille.

    Si collect_fn est fourni (ex: collector_agent.collect), utilise les
    vraies API (Géorisques, IGN, BDNB…). Sinon, utilise _building_data_minimal
    (fallback simulation sans réseau).
    """
    async with semaphore:
        adresse_approx = f"{lat:.5f},{lon:.5f}"
        try:
            if collect_fn is not None:
                # Vraies API : collect() gère déjà le format "lat,lon"
                # avec détection automatique + reverse geocode si besoin
                building_data = await collect_fn(adresse_approx)
            else:
                # Fallback : simulation géographique sans réseau
                building_data = _building_data_minimal(lat, lon)

            scores = compute_risk_scores(building_data)
            return PointEchantillon(
                index=idx,
                lat=lat,
                lon=lon,
                adresse_approx=adresse_approx,
                score=scores,
            )
        except Exception as exc:
            logger.warning("Point %d (%.4f,%.4f) en echec : %s", idx, lat, lon, exc)
            return PointEchantillon(
                index=idx,
                lat=lat,
                lon=lon,
                adresse_approx=adresse_approx,
                erreur=str(exc),
            )


# ---------------------------------------------------------------------------
#   Point d'entrée principal
# ---------------------------------------------------------------------------

async def run_zone_risk_assessment(
    bounds: tuple[float, float, float, float],
    spacing_km: float = 0.5,
    max_points: int = 50,
    max_concurrency: int = 5,
    land_only: bool = False,
    collect_fn: Callable[[str], Awaitable[dict]] | None = None,
) -> RatingZone:
    """Évalue une zone complète : grille d'échantillonnage + scoring + agrégation.

    Parameters
    ----------
    collect_fn : Callable[[str], Awaitable[dict]] | None
        Si fourni (ex: collector_agent.collect), chaque point est collecté
        via les vraies API (Géorisques, IGN, BDNB…).
        Si None, utilise _building_data_minimal (simulation sans réseau).
    """
    points = _generer_grille_rectangulaire(bounds, spacing_km, max_points)
    nb_points = len(points)

    semaphore = asyncio.Semaphore(max_concurrency)
    t0 = time.time()

    tasks = [
        _collecter_point(lat, lon, land_only, semaphore, i, collect_fn)
        for i, (lat, lon) in enumerate(points)
    ]
    echantillons = await asyncio.gather(*tasks)
    duree = time.time() - t0

    points_valides = [p for p in echantillons if p.score is not None]
    points_erreur = [p for p in echantillons if p.erreur is not None]
    nb_valides = len(points_valides)
    nb_erreurs = len(points_erreur)

    if nb_valides == 0:
        return RatingZone(
            nb_points=nb_points,
            nb_points_valides=0,
            nb_points_erreur=nb_erreurs,
            score_moyen=0.0,
            score_pondere=0.0,
            rating_global="Non evaluable",
            perils={},
            points_echantillon=[_point_to_dict(p) for p in echantillons],
            message=f"Aucun point valide sur {nb_points} - {nb_erreurs} en echec",
        )

    logger.info(
        "Zone : %d/%d points valides, %d en echec, %.1fs",
        nb_valides, nb_points, nb_erreurs, duree,
    )

    # Agrégation par péril
    noms_perils = ["inondation", "rga", "tempete", "incendie", "seisme"]
    distributions: dict[str, DistributionPeril] = {}
    worst_overall = 0.0
    worst_peril_name: str | None = None

    for nom in noms_perils:
        scores_peril = []
        for p in points_valides:
            if p.score:
                scores_peril.append(_peril_score_from_zones(p.score, nom))

        if not scores_peril:
            continue

        scores_sorted = sorted(scores_peril)
        n = len(scores_sorted)
        moyenne = sum(scores_peril) / n
        mediane = scores_sorted[n // 2] if n % 2 == 1 else (
            scores_sorted[n // 2 - 1] + scores_sorted[n // 2]
        ) / 2
        variance = sum((s - moyenne) ** 2 for s in scores_peril) / n
        ecart_type = math.sqrt(variance)
        worst = max(scores_peril)
        pct_faible = sum(1 for s in scores_peril if s < 20) / n * 100
        pct_modere = sum(1 for s in scores_peril if 20 <= s < 45) / n * 100
        pct_eleve = sum(1 for s in scores_peril if 45 <= s < 70) / n * 100
        pct_critique = sum(1 for s in scores_peril if s >= 70) / n * 100

        distributions[nom] = DistributionPeril(
            scores=scores_peril,
            min_score=min(scores_peril),
            max_score=max(scores_peril),
            moyenne=round(moyenne, 1),
            mediane=round(mediane, 1),
            ecart_type=round(ecart_type, 1),
            pct_faible=round(pct_faible, 1),
            pct_modere=round(pct_modere, 1),
            pct_eleve=round(pct_eleve, 1),
            pct_critique=round(pct_critique, 1),
            worst_case=round(worst, 1),
        )

        if worst > worst_overall:
            worst_overall = worst
            worst_peril_name = nom

    scores_globaux = [p.score.get("score_global", 0) for p in points_valides]
    score_moyen = sum(scores_globaux) / len(scores_globaux)

    msg = (
        f"{nb_valides}/{nb_points} points evalues"
        + (f", {nb_erreurs} en echec" if nb_erreurs else "")
    )

    return RatingZone(
        nb_points=nb_points,
        nb_points_valides=nb_valides,
        nb_points_erreur=nb_erreurs,
        score_moyen=round(score_moyen, 1),
        score_pondere=round(score_moyen, 1),
        rating_global=_rating_from_mean(score_moyen, worst_overall),
        perils=distributions,
        worst_case_peril=worst_peril_name,
        worst_case_score=round(worst_overall, 1),
        points_echantillon=[_point_to_dict(p) for p in echantillons],
        land_only=land_only,
        message=msg,
    )


def _rating_from_mean(mean_score: float, worst_case: float) -> str:
    """Rating global : ne pas moyenner un point dangereux."""
    if worst_case >= 70:
        return "Eleve"
    if mean_score >= 45:
        return "Eleve"
    if mean_score >= 20:
        return "Modere"
    return "Faible"


def _peril_score_from_zones(result: dict, peril: str) -> float:
    """Extrait un score de péril (0-100) depuis les zones du resultat compute_risk_scores."""
    zones = result.get("zones", {}) if result else {}
    if peril == "inondation":
        return float(zones.get("sous_sol", {}).get("risque", 0) or 0)
    if peril == "rga":
        return float(zones.get("fondations", {}).get("risque", 0) or 0)
    if peril == "tempete":
        murs = [zones.get(z, {}).get("risque", 0) or 0
                for z in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]]
        return sum(murs) / len(murs) if murs else 0.0
    if peril == "incendie":
        return float(zones.get("toiture", {}).get("risque", 0) or 0)
    if peril == "seisme":
        fondations = float(zones.get("fondations", {}).get("risque", 0) or 0)
        murs = [zones.get(z, {}).get("risque", 0) or 0
                for z in ["murs_nord", "murs_sud", "murs_est", "murs_ouest"]]
        mur_moyen = sum(murs) / len(murs) if murs else 0.0
        return (fondations + mur_moyen) / 2.0
    return 0.0


def _result_to_point_dict(result: dict) -> dict | None:
    """Convertit le dict compute_risk_scores en format compatible avec le frontend."""
    if not result:
        return None
    return {
        "score_global": result.get("score_global", 0),
        "inondation": {"score": _peril_score_from_zones(result, "inondation")},
        "rga": {"score": _peril_score_from_zones(result, "rga")},
        "tempete": {"score": _peril_score_from_zones(result, "tempete")},
        "incendie": {"score": _peril_score_from_zones(result, "incendie")},
        "seisme": {"score": _peril_score_from_zones(result, "seisme")},
    }


def _point_to_dict(p: PointEchantillon) -> dict:
    return {
        "index": p.index,
        "lat": p.lat,
        "lon": p.lon,
        "adresse_approx": p.adresse_approx,
        "score": _result_to_point_dict(p.score) if p.score else None,
        "erreur": p.erreur,
    }


def rating_zone_to_dict(rz: RatingZone) -> dict:
    """Sérialise un RatingZone en dictionnaire JSON compatible."""
    perils_dict = {}
    for nom, d in rz.perils.items():
        perils_dict[nom] = {
            "min_score": d.min_score,
            "max_score": d.max_score,
            "moyenne": d.moyenne,
            "mediane": d.mediane,
            "ecart_type": d.ecart_type,
            "pct_faible": d.pct_faible,
            "pct_modere": d.pct_modere,
            "pct_eleve": d.pct_eleve,
            "pct_critique": d.pct_critique,
            "worst_case": d.worst_case,
        }

    return {
        "nb_points": rz.nb_points,
        "nb_points_valides": rz.nb_points_valides,
        "nb_points_erreur": rz.nb_points_erreur,
        "score_moyen": rz.score_moyen,
        "score_pondere": rz.score_pondere,
        "rating_global": rz.rating_global,
        "land_only": rz.land_only,
        "message": rz.message,
        "perils": perils_dict,
        "worst_case_peril": rz.worst_case_peril,
        "worst_case_score": rz.worst_case_score,
        "points_echantillon": rz.points_echantillon,
    }
