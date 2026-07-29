"""
POST /diagnostic — route commune aux 3 cas d'usage (cf. README racine,
section "Backend — communication inter-agents").

Instancie une execution du StateGraph (`graph.ainvoke`), avec un
`thread_id` unique par requete (cle de checkpoint). Retourne directement
`state.digital_twin`, le contrat pret pour la scene Three.js du front.

Chaque etape est logguee cote serveur (voir `app.core.logging`) : c'est la
"trace des agents" demandee — collecte, scoring, assemblage — visible dans
la console au fil de l'execution, pas seulement dans la reponse finale.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.graph import diagnostic_graph
from app.connectors import annonces_lookup, dvf_lookup
from app.connectors.dvf_lookup import DvfLookupUnavailable
from app.core.config import settings
from app.core.logging import get_logger
from app.core.paca import department_code_from_citycode
from app.scoring.zone_scoring import run_zone_risk_assessment, rating_zone_to_dict

logger = get_logger(__name__)
router = APIRouter()


class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complete du bien")
    formulaire: dict | None = Field(
        default=None,
        description="Champs geometry saisis explicitement (priorite sur l'inference BDNB) : "
        "has_basement, has_garage, garage_position, has_garden, garden_surface_m2, roof_shape...",
    )
    # La valeur par defaut est pilotee par settings.copernicus_enabled
    # (backend/app/core/config.py). Changez-la la pour basculer le defaut.
    copernicus: bool = Field(
        default=settings.copernicus_enabled,
        description="Activer/desactiver Copernicus (CDS) dans la collecte. "
        "Si false, climat_copernicus sera null dans le building_data sans erreur.",
    )


@router.post("/diagnostic")
async def run_diagnostic(payload: DiagnosticRequest) -> dict:
    thread_id = str(uuid.uuid4())
    logger.info("=" * 70)
    logger.info("POST /diagnostic  adresse=%r  thread_id=%s", payload.adresse, thread_id)
    t0 = time.perf_counter()

    try:
        final_state = await diagnostic_graph.ainvoke(
            {
                "adresse": payload.adresse,
                "formulaire": payload.formulaire,
                "copernicus": payload.copernicus,
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        logger.exception("diagnostic -- echec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    digital_twin = final_state.get("digital_twin")
    if digital_twin is None:
        logger.error("diagnostic -- aucun contrat produit (etat final incomplet) en %.2fs", elapsed)
        raise HTTPException(status_code=502, detail="Le graphe n'a pas produit de contrat digital_twin.")

    logger.info("diagnostic OK en %.2fs (thread_id=%s)", elapsed, thread_id)
    logger.info("=" * 70)
    return digital_twin


class ZoneRequest(BaseModel):
    """Requête d'évaluation de zone (carte interactive promoteur).

    bounds : tuple[float, float, float, float]
        (lat_min, lon_min, lat_max, lon_max) — bounding box de la zone.
    spacing_km : float
        Espacement entre points de la grille d'échantillonnage (défaut 0.5 km).
    max_points : int
        Nombre maximum de points de la grille (défaut 50).
    land_only : bool
        Si True, ignore les données BDNB (mode terrain nu).
    """
    bounds: tuple[float, float, float, float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box (lat_min, lon_min, lat_max, lon_max)",
    )
    spacing_km: float = Field(default=0.5, ge=0.05, le=5.0)
    max_points: int = Field(default=50, ge=5, le=200)
    land_only: bool = Field(default=False)


@router.post("/diagnostic/zone")
async def run_zone_diagnostic(payload: ZoneRequest) -> dict:
    """Évalue les risques climatiques sur une zone géographique.

    Génère une grille d'échantillonnage régulière et score chaque point
    avec les VRAIES données (Géorisques, BDNB, IGN Altitude, Open-Meteo,
    DVF local si les CSV du département sont présents — voir
    app.agents.collector_agent.collect, appelé par run_zone_risk_assessment
    avec Copernicus désactivé pour ce mode grille). Retourne l'agrégation
    complète : score global, distribution par péril, worst-case, et la
    liste des points pour le rendu cartographique.

    Un point sans donnée exploitable (adresse non résolue par BDNB à cet
    endroit précis, service externe temporairement indisponible...) est
    consigné en erreur pour ce point et exclu des agrégats plutôt que de
    faire échouer toute la requête.
    """
    logger.info(">>> POST /diagnostic/zone  bounds=%s", payload.bounds)
    t0 = time.perf_counter()

    try:
        rating = await run_zone_risk_assessment(
            bounds=payload.bounds,
            spacing_km=payload.spacing_km,
            max_points=payload.max_points,
            land_only=payload.land_only,
        )
    except Exception as exc:
        logger.exception("zone_diagnostic -- echec bounds=%s", payload.bounds)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    result = rating_zone_to_dict(rating)
    logger.info(">>> POST /diagnostic/zone OK en %.2fs (%d points, score=%.1f)", elapsed, result["nb_points"], result["score_moyen"])
    return result


class ZonePrixRequest(BaseModel):
    """Requête de prix au m2 DVF sur la zone visible de la carte.

    bounds : mêmes conventions que ZoneRequest (lat_min, lon_min, lat_max, lon_max).
    citycode : code INSEE de la commune choisie dans la recherche (BAN), utilisé
        uniquement pour déduire le fichier CSV départemental à interroger
        (voir app/connectors/dvf_lookup.py). Pas besoin de reverse-geocoder les
        bounds : le front connaît déjà la commune sélectionnée.
    """
    bounds: tuple[float, float, float, float] = Field(..., min_length=4, max_length=4)
    citycode: str = Field(..., min_length=5, max_length=5)


@router.post("/diagnostic/zone/prix")
async def run_zone_prix(payload: ZonePrixRequest) -> dict:
    """Prix au m2 DVF (ventes réelles) sur la zone visible.

    Complémentaire à /diagnostic/zone (risque climatique) : renvoie
    médiane/moyenne du prix au m2 et le nombre de ventes, à partir du CSV
    DVF local du département (pas d'API DVF fiable disponible — voir
    settings.dvf_enabled et data/lookup/dvf/README.md). Si désactivé ou
    fichier absent, répond disponible=false plutôt que de faire échouer
    l'appel : la carte doit pouvoir s'afficher sans cette donnée.
    """
    if not settings.dvf_enabled:
        return {
            "disponible": False,
            "message": "DVF désactivé sur ce poste (settings.dvf_enabled=False). "
            "Voir data/lookup/dvf/README.md pour activer.",
        }

    department_code = department_code_from_citycode(payload.citycode)
    logger.info(">>> POST /diagnostic/zone/prix  bounds=%s  departement=%s", payload.bounds, department_code)

    try:
        # asyncio.to_thread : le premier appel charge/normalise le fichier DVF
        # local (potentiellement gros, cf. dvf_lookup.py) - ne doit pas
        # bloquer la boucle asyncio pendant ce temps.
        stats = await asyncio.to_thread(
            dvf_lookup.zone_price_stats, department_code, payload.bounds, payload.citycode
        )
    except DvfLookupUnavailable as exc:
        logger.warning("zone_prix -- DVF indisponible pour departement %s : %s", department_code, exc)
        return {"disponible": False, "message": str(exc)}

    return {"disponible": True, "departement": department_code, **stats}


class ZoneAnnoncesRequest(BaseModel):
    """Requête d'annonces "en vente" sur la zone visible (carte, marqueurs
    colorés par score climatique). Voir app/connectors/annonces_lookup.py :
    uniquement des données réelles (DVF, ou la base CSV locale
    backend/data/annonces_maisons_france.csv) — si aucune des deux n'est
    disponible, la réponse contient une liste vide plutôt qu'un échec dur
    ou des données fabriquées."""
    bounds: tuple[float, float, float, float] = Field(..., min_length=4, max_length=4)
    citycode: str | None = Field(default=None, min_length=5, max_length=5)
    max_results: int = Field(default=40, ge=1, le=200)


@router.post("/diagnostic/zone/annonces")
async def run_zone_annonces(payload: ZoneAnnoncesRequest) -> dict:
    """Annonces de la zone visible + score climatique par annonce.

    Priorité aux vraies ventes DVF (source="dvf") quand citycode est fourni
    et DVF activé : ce sont de vraies transactions immobilières (pas des
    biens actuellement en vente - DVF ne recense que des ventes déjà
    réalisées), géolocalisées à la demande si besoin (voir
    dvf_lookup.real_transactions_for_zone). Si indisponible (pas de citycode,
    DVF désactivé, géocodage en échec, aucune vente dans la zone), retombe
    sur annonces_lookup (base CSV locale d'annonces réelles). Aucun mode
    démo, aucun appel API tiers : si aucune source réelle n'est disponible,
    la réponse contient une liste vide.
    """
    department_code = department_code_from_citycode(payload.citycode) if payload.citycode else None
    prix_m2_base = None

    if payload.citycode and settings.dvf_enabled:
        try:
            stats = await asyncio.to_thread(
                dvf_lookup.zone_price_stats, department_code, payload.bounds, payload.citycode
            )
            prix_m2_base = stats.get("prix_m2_median")
        except DvfLookupUnavailable:
            pass  # pas de donnees DVF locales -> prix_m2_base reste None (non utilise par la source CSV)

        try:
            dvf_listings = await asyncio.to_thread(
                dvf_lookup.real_transactions_for_zone,
                department_code, payload.citycode, payload.bounds, payload.max_results,
            )
        except DvfLookupUnavailable as exc:
            logger.warning("zone_annonces -- DVF/geocodage indisponible : %s", exc)
            dvf_listings = []

        if dvf_listings:
            logger.info(">>> POST /diagnostic/zone/annonces OK (%d ventes DVF reelles)", len(dvf_listings))
            return {
                "disponible": True,
                "source": "dvf",
                "count": len(dvf_listings),
                "listings": dvf_listings,
                "fallback_reason": None,
            }

    logger.info(">>> POST /diagnostic/zone/annonces  bounds=%s  max_results=%d (fallback csv local)", payload.bounds, payload.max_results)
    result = await annonces_lookup.fetch_annonces_zone(
        bounds=payload.bounds,
        max_results=payload.max_results,
        prix_m2_base=prix_m2_base,
    )
    listings = result["listings"]
    if result.get("fallback_reason"):
        # Log explicite : c'est ici qu'on voit POURQUOI la base CSV n'a rien
        # renvoye (fichier absent/invalide - voir annonces_lookup.py).
        logger.warning(">>> POST /diagnostic/zone/annonces -- source=%s, RAISON : %s", result["source"], result["fallback_reason"])
    logger.info(">>> POST /diagnostic/zone/annonces OK (%d annonces, source=%s)", len(listings), result["source"])
    return {
        "disponible": True,
        "source": result["source"],
        "count": len(listings),
        "listings": listings,
        "fallback_reason": result.get("fallback_reason"),
    }
