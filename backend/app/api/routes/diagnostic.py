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

from app.agents import digital_twin_agent, interpretation_agent, recommandations_agent, scoring_agent
from app.agents.collector_agent import collect
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


@router.post("/diagnostic/fast")
async def run_diagnostic_fast(payload: DiagnosticRequest) -> dict:
    """Variante rapide de /diagnostic pour l'affichage immediat du jumeau
    numerique 3D côté front.

    N'execute QUE collector_agent + scoring_agent (+ assemblage du contrat) :
    saute recommandations_agent (RAG) et interpretation_agent, qui sont a
    eux deux la quasi-totalite du temps de /diagnostic (plusieurs dizaines
    de secondes, appels Mistral zone par zone). Le contrat renvoye a donc
    les memes zones/scores/couleurs que /diagnostic, mais avec des
    "recommandations" vides et sans "conclusion"/"facteurs_aggravants"
    interpretes.

    Le front affiche la maison tout de suite avec ce contrat, puis appelle
    /diagnostic/recommandations en tache de fond avec le bloc "_resume"
    ci-dessous pour recuperer les recommandations des qu'elles sont pretes,
    SANS relancer la collecte (BDNB/Georisques/Open-Meteo... deja faite ici).
    """
    logger.info("=" * 70)
    logger.info("POST /diagnostic/fast  adresse=%r", payload.adresse)
    t0 = time.perf_counter()

    try:
        building_data = await collect(payload.adresse, enable_copernicus=payload.copernicus)
        state: dict = {"building_data": building_data, "formulaire": payload.formulaire}
        state.update(scoring_agent.run(state))
        state.update(digital_twin_agent.run(state))
    except Exception as exc:
        logger.exception("diagnostic/fast -- echec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu etre assemble.")

    # Repasse par le front tel quel a /diagnostic/recommandations : evite de
    # relancer la collecte reseau pour la phase 2.
    digital_twin["_resume"] = {
        "building_data": state["building_data"],
        "risk_scores": state["risk_scores"],
        "formulaire": payload.formulaire,
    }

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/fast OK en %.2fs", elapsed)
    logger.info("=" * 70)
    return digital_twin


class DiagnosticRecommandationsRequest(BaseModel):
    building_data: dict = Field(..., description="Tel que renvoye par /diagnostic/fast (digital_twin._resume.building_data)")
    risk_scores: dict = Field(..., description="Tel que renvoye par /diagnostic/fast (digital_twin._resume.risk_scores)")
    formulaire: dict | None = Field(default=None)


@router.post("/diagnostic/recommandations")
async def run_diagnostic_recommandations(payload: DiagnosticRecommandationsRequest) -> dict:
    """Deuxieme phase (lente) de /diagnostic/fast : recommandations RAG
    (Mistral, par zone) + interpretation LLM, puis reassemblage du contrat
    complet. Ne relance PAS la collecte : reutilise building_data/risk_scores
    tels que renvoyes dans digital_twin._resume par /diagnostic/fast.

    Le front appelle cette route juste apres avoir affiche la maison via
    /diagnostic/fast, et fusionne le contrat renvoye ici (recommandations,
    conclusion, facteurs_aggravants/attenuants par zone) dans l'etat deja
    affiche a l'ecran des qu'il est pret.
    """
    logger.info("=" * 70)
    logger.info("POST /diagnostic/recommandations")
    t0 = time.perf_counter()

    state: dict = {
        "building_data": payload.building_data,
        "risk_scores": payload.risk_scores,
        "formulaire": payload.formulaire,
    }

    try:
        state.update(await recommandations_agent.run(state))
        # L'interpretation_agent (LLM, ~2-3s par zone) est sautee quand les
        # recommandations viennent du fallback déterministe (Mistral down) :
        # elle ajoute ~20s au pipeline et le proxy Next.js (timeout 30s)
        # coupe la connexion avant la fin → le front passe au calcul
        # économique sans recommandations → coût des travaux = 0.
        # Le fallback produit déjà des recommandations chiffrées et sourcées.
        _a_fallback = any(
            (z.get("recommandations") or []) and
            (z.get("recommandations")[0].get("sources") or []) and
            str((z.get("recommandations")[0].get("sources") or [{}])[0].get("fiche_id", "")).startswith("REF-")
            for z in state.get("risk_scores", {}).get("zones", {}).values()
        )
        if not _a_fallback:
            state.update(await asyncio.to_thread(interpretation_agent.run, state))
        else:
            logger.info("diagnostic/recommandations -- fallback actif, interpretation_agent sautée (gain ~20s)")
        state.update(digital_twin_agent.run(state))
    except Exception as exc:
        logger.exception("diagnostic/recommandations -- echec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu etre assemble.")

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/recommandations OK en %.2fs", elapsed)
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

    Combine désormais DEUX sources réelles sur la même carte, sans les
    distinguer visuellement côté frontend (demande explicite : ne pas
    préciser que les points DVF sont des transactions déjà réalisées, ne
    pas afficher de lien de fiche pour ces points-là - ils n'en ont pas) :

      1. DVF (vraies transactions immobilières, géolocalisées à la demande -
         voir dvf_lookup.real_transactions_for_zone), quand citycode est
         fourni et DVF activé.
      2. La base CSV locale d'annonces réelles (annonces_lookup.py).

    Aucun mode démo, aucun appel API tiers : si aucune des deux sources
    n'est disponible, la réponse contient une liste vide.
    """
    department_code = department_code_from_citycode(payload.citycode) if payload.citycode else None
    prix_m2_base = None
    dvf_listings: list[dict] = []

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

    csv_result = await annonces_lookup.fetch_annonces_zone(
        bounds=payload.bounds,
        max_results=payload.max_results,
        prix_m2_base=prix_m2_base,
    )
    csv_listings = csv_result["listings"]

    combined = (dvf_listings + csv_listings)[: payload.max_results]
    if dvf_listings and csv_listings:
        source = "mixed"
    elif dvf_listings:
        source = "dvf"
    else:
        source = csv_result["source"]

    fallback_reason = None if combined else csv_result.get("fallback_reason")
    if fallback_reason:
        logger.warning(">>> POST /diagnostic/zone/annonces -- source=%s, RAISON : %s", source, fallback_reason)
    logger.info(
        ">>> POST /diagnostic/zone/annonces OK (%d DVF + %d CSV = %d annonces, source=%s)",
        len(dvf_listings), len(csv_listings), len(combined), source,
    )
    return {
        "disponible": True,
        "source": source,
        "count": len(combined),
        "listings": combined,
        "fallback_reason": fallback_reason,
    }
