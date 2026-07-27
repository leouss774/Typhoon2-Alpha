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


from app.scoring.risk_model import score_address, ScoresAdresse

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
    score: ScoresAdresse | None = None
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
    """Simule les données Géorisques à partir des coordonnées.

    Produit des résultats déterministes mais géographiquement plausibles
    pour la région PACA (coastal vs inland, est vs ouest).
    """
    # --- Inondation : plus fort près des côtes (lat < 43.5), avec bruit ---
    inondation_score = 15.0
    if lat < 43.8:
        inondation_score += max(0, (43.8 - lat) / 0.8) * 50
    inondation_score += (_noise(lat, lon, 1) - 0.5) * 28
    inondation_score = max(5, min(100, inondation_score))

    # --- RGA : plus fort dans l'arrière-pays (lat plus élevée) ---
    rga_score = 15.0
    if lat > 43.0:
        rga_score += min(1.0, (lat - 43.0) / 0.8) * 40
    rga_score += (_noise(lat, lon, 2) - 0.5) * 35
    rga_score = max(5, min(100, rga_score))

    # --- Incendie : plus fort dans les terres sèches ---
    incendie_score = 8.0
    if lat > 43.2:
        incendie_score += min(1.0, (lat - 43.2) / 0.6) * 40
    incendie_score += (_noise(lat, lon, 3) - 0.5) * 25
    incendie_score = max(3, min(100, incendie_score))

    # --- CATNAT historique simulé ---
    catnat_data: list[dict] = []
    if lat < 43.6:
        n_flood = int(2 + _noise(lat, lon, 4) * 5)
        n_storm = int(2 + _noise(lat, lon, 5) * 4)
    else:
        n_flood = int(1 + _noise(lat, lon, 4) * 3)
        n_storm = int(0 + _noise(lat, lon, 5) * 2)
    for _ in range(n_flood):
        catnat_data.append({"libelle_catnat": "Inondation et coulées de boue"})
    for _ in range(n_storm):
        catnat_data.append({"libelle_catnat": "Tempête"})

    # --- Zonage sismique : plus fort à l'est (Alpes) ---
    if lon > 7.0:
        zone_sismique = "4"      # Nice, Alpes-Maritimes
    elif lon > 6.5:
        zone_sismique = "3"      # Var est
    elif lon > 5.5:
        zone_sismique = "2"      # Bouches-du-Rhône
    else:
        zone_sismique = "1"      # Gard, Vaucluse

    return {
        "risques_commune": {
            "gazella": {"alerte": _niveau_alerte(inondation_score)},
            "argiles": {"alerte": _niveau_alerte(rga_score)},
            "feu_foret": {"alerte": _niveau_alerte(incendie_score)},
        },
        "catnat": {"data": catnat_data},
        "zonage_sismique": {"zone_sismique": zone_sismique},
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

            scores = score_address(building_data, land_only=land_only)
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
                scores_peril.append(getattr(p.score, nom).score)

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

    scores_globaux = [p.score.score_global for p in points_valides]
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


def _point_to_dict(p: PointEchantillon) -> dict:
    return {
        "index": p.index,
        "lat": p.lat,
        "lon": p.lon,
        "adresse_approx": p.adresse_approx,
        "score": p.score.to_dict() if p.score else None,
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
