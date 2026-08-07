# -*- coding: utf-8 -*-
"""
POST /api/v1/artisans/matching — Recherche d'artisans RGE et non-RGE
pour des recommandations de travaux.

Accepte soit :
  - Une adresse + des recommandations structurées (avec 'cle')
  - Un fichier JSON complet (format resultat_enrichi.json) avec zones

Réutilise le code de app/matching/generate_rapport_artisans.py et
app/matching/match_artisans_rge.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.artisans.service import matcher
from app.connectors.geocoding import geocode_address
from app.core.config import settings
from app.core.logging import get_logger
from app.matching.generate_rapport_artisans import (
    CATEGORIES_NON_RGE,
    _classifier_recommandation,
    _extraire_code_postal,
)
from app.matching.match_artisans_rge import RECOMMANDATION_VERS_DOMAINE_ADEME

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/artisans", tags=["artisans"])
legacy_router = APIRouter(prefix="/artisans", tags=["artisans"])
RESULTAT_ENRICHI_PATH = Path(__file__).resolve().parents[2] / "matching" / "resultat_enrichi.json"


class ArtisanMatchRequest(BaseModel):
    adresse: str = Field(..., min_length=5)
    zones: list[dict[str, Any]]
    limite: int = Field(default=5, ge=1, le=20)


@legacy_router.post("/match")
async def match_artisans(payload: ArtisanMatchRequest) -> dict[str, Any]:
    """Compatibilité avec le premier client du projet."""
    try:
        return await matcher(payload.adresse, payload.zones, payload.limite)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class RecommandationInput(BaseModel):
    id: str | None = Field(default=None, description="Identifiant stable de la recommandation du diagnostic")
    """Une recommandation de travaux, au format structuré ou texte libre."""

    cle: str | None = Field(
        default=None,
        description="Clé de recommandation connue (ex: isolation_combles, rga_geotechnique)",
    )
    mesure: str | None = Field(default=None, description="Texte libre de la mesure de travaux")
    zone: str | None = Field(default=None, description="Zone du bâtiment (toiture, facade, sous_sol...)")
    risques: list[str] | None = Field(default=None, description="Risques associés (inondation, argile, radon...)")
    priorite: str | None = Field(default=None, description="Priorité de la recommandation")


class ArtisanMatchingRequest(BaseModel):
    """Requête de matching artisans."""

    adresse: str = Field(..., min_length=3, description="Adresse complète ou code postal")
    code_postal: str | None = Field(
        default=None,
        description="Code postal (optionnel, sinon extrait de l'adresse ou du géocodage)",
    )
    recommandations: list[RecommandationInput] | None = Field(
        default=None,
        description="Liste des recommandations à traiter. Si non fourni, renvoie les domaines disponibles.",
    )
    limite_entreprises: int = Field(default=10, ge=1, le=50, description="Nombre max d'entreprises par catégorie")
    lat: float | None = Field(default=None, description="Latitude (optionnelle, pour scoring géographique précis)")
    lon: float | None = Field(default=None, description="Longitude (optionnelle, pour scoring géographique précis)")


class ArtisanMatchingResponse(BaseModel):
    """Réponse du matching artisans."""

    adresse: str
    code_postal: str
    recommandations_traitees: list[dict[str, Any]]
    resume: dict[str, Any]
    geocoding: dict[str, Any] | None = None


@router.get("/diagnostic-data")
async def diagnostic_data() -> dict[str, Any]:
    """Prépare les données de matching depuis resultat_enrichi.json."""
    try:
        data = json.loads(RESULTAT_ENRICHI_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(404, "Le fichier resultat_enrichi.json est introuvable.") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "Le fichier resultat_enrichi.json contient un JSON invalide.") from exc

    adresse = str(data.get("adresse") or "").strip()
    try:
        code_postal = _extraire_code_postal(data)
    except KeyError:
        code_postal = ""

    recommandations: list[dict[str, Any]] = []
    for zone_bloc in data.get("zones") or []:
        zone = str(zone_bloc.get("zone") or "")
        risques = [str(risque) for risque in zone_bloc.get("risques") or []]
        for recommandation in zone_bloc.get("recommandations") or []:
            mesure = str(
                recommandation.get("mesure")
                or recommandation.get("travaux")
                or ""
            ).strip()
            cle = recommandation.get("cle")
            if mesure or cle:
                recommandations.append({
                    "cle": cle,
                    "mesure": mesure or None,
                    "zone": zone,
                    "risques": risques,
                    "priorite": (
                        recommandation.get("priorite")
                        or recommandation.get("priority")
                        or recommandation.get("priorité")
                    ),
                })

    if not adresse:
        raise HTTPException(422, "Aucune adresse n'est présente dans resultat_enrichi.json.")
    if not recommandations:
        raise HTTPException(422, "Aucune recommandation n'est présente dans resultat_enrichi.json.")

    return {
        "adresse": adresse,
        "code_postal": code_postal,
        "recommandations": recommandations,
    }


@router.post("/matching", response_model=ArtisanMatchingResponse)
async def matching_artisans(payload: ArtisanMatchingRequest) -> ArtisanMatchingResponse:
    """Recherche optimisée avec cache + parallélisation des recommandations."""
    logger.info("POST /api/v1/artisans/matching  adresse=%r  recommandations=%d",
                payload.adresse, len(payload.recommandations) if payload.recommandations else 0)

    # Extraire code postal : priorité au champ dédié, puis adresse, puis géocodage
    code_postal: str | None = payload.code_postal or None

    if not code_postal:
        try:
            code_postal = _extraire_code_postal({"adresse": payload.adresse})
        except KeyError:
            match_cp = re.search(r"\b(\d{5})\b", payload.adresse)
            if match_cp:
                code_postal = match_cp.group(0)

    # Géocoder pour les coordonnées (seulement si code_postal ou coordonnées manquantes)
    lat, lon = payload.lat, payload.lon
    geocoding_info = None
    if not code_postal or lat is None or lon is None:
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                g = await geocode_address(client, payload.adresse)
                if lat is None or lon is None:
                    lat, lon = g.lat, g.lon
                if not code_postal:
                    code_postal = g.postcode
                geocoding_info = {"label": g.label, "city": g.city, "citycode": g.citycode,
                                  "postcode": g.postcode, "lat": g.lat, "lon": g.lon, "score": g.score}
        except Exception as exc:
            logger.warning("  géocodage échoué: %s", exc)

    # Si toujours pas de code postal, erreur
    if not code_postal:
        raise HTTPException(400,
            "Impossible d'extraire le code postal. Spécifiez un code postal dans l'adresse "
            "(ex: '10 Promenade des Anglais, 06000 Nice') ou via le champ dédié.")

    logger.info("  code_postal=%s  lat=%s  lon=%s", code_postal, lat, lon)

    # Parser les recommandations
    recos: list[dict[str, Any]] = []
    non_class = 0
    if payload.recommandations:
        for r in payload.recommandations:
            if r.cle:
                recos.append({"recommendation_id": r.id, "cle": r.cle, "priorite": r.priorite, "zone_origine": r.zone,
                             "risques_origine": r.risques or [], "mesure_originale": r.mesure or ""})
            elif r.mesure:
                c = _classifier_recommandation(r.zone or "", r.risques or [], r.mesure)
                if c:
                    recos.append({"recommendation_id": r.id, "cle": c, "priorite": r.priorite, "zone_origine": r.zone or "",
                                 "risques_origine": r.risques or [], "mesure_originale": r.mesure})
                else:
                    non_class += 1
            else:
                non_class += 1

    if not recos:
        raise HTTPException(400, f"Aucune recommandation valide. Clés: {list(RECOMMANDATION_VERS_DOMAINE_ADEME)} (RGE) et {list(CATEGORIES_NON_RGE)} (non-RGE)")

    # Exécution parallélisée via le service optimisé
    from app.matching.service import run_matching
    rapport = await run_matching(recos, code_postal, lat, lon, payload.limite_entreprises)

    return ArtisanMatchingResponse(
        adresse=payload.adresse,
        code_postal=code_postal,
        recommandations_traitees=rapport["recommandations_traitees"],
        resume=rapport["resume"],
        geocoding=geocoding_info,
    )


@router.post("/search")
async def smart_search(payload: ArtisanMatchingRequest) -> ArtisanMatchingResponse:
    """Recherche intelligente : prend une adresse et des recommandations
    (clés ou texte libre), géocode automatiquement l'adresse pour un
    scoring par distance réelle.

    C'est le même endpoint que /matching mais avec géocodage automatique
    activé par défaut — utilisez-le depuis le frontend.
    """
    return await matching_artisans(payload)


@router.get("/domaines")
async def lister_domaines() -> dict:
    """Liste tous les domaines RGE et non-RGE disponibles pour le matching."""
    domaines_rge = {
        cle: {"libelle": libelle, "categorie": "rge"}
        for cle, libelle in RECOMMANDATION_VERS_DOMAINE_ADEME.items()
    }
    domaines_non_rge = {
        cle: {
            "libelle": config["libelle"],
            "categorie": "non_rge",
            "code_naf": config["code_naf"],
            "annuaire": config["annuaire_reference"]["organisme"],
        }
        for cle, config in CATEGORIES_NON_RGE.items()
    }
    return {
        "domaines": {**domaines_rge, **domaines_non_rge},
        "total": len(domaines_rge) + len(domaines_non_rge),
    }
