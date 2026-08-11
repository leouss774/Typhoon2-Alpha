"""
Routes dediees au pipeline usine : analyse de plan par VLM et enrichissement.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, File, UploadFile
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.scoring.plan_usine import compute_usine_risk

logger = get_logger(__name__)
router = APIRouter()

# Mapping bande D03 (RisqueReport) -> score aléa utilisé comme F (aléa du site).
_BANDE_SCORE = {
    "tres_faible": 10,
    "faible": 30,
    "modere": 50,
    "eleve": 70,
    "critique": 90,
}


def _contexte_alea_site(report: dict) -> dict | None:
    """Réduit un RisqueReport Géorisques en contexte d'aléa du site pour
    l'usine : {score, libelle} où score est le max des aléas présents."""
    aleas = report.get("aleas") or []
    scores = []
    for alea in aleas:
        if alea.get("present") is not True:
            continue
        niveau = alea.get("niveau")
        if niveau in _BANDE_SCORE:
            scores.append(_BANDE_SCORE[niveau])
    if not scores:
        return None
    best = max(scores)
    libelle = next(
        (a.get("libelle") for a in aleas
         if a.get("present") is True and _BANDE_SCORE.get(a.get("niveau"), 0) == best),
        None,
    )
    return {"score": best, "libelle": libelle}


async def _rapport_site(adresse: str) -> dict | None:
    """Appelle le flux Géorisques (`/diagnostic/adresse`) pour obtenir le
    contexte d'aléa du site. Non bloquant : toute erreur renvoie None."""
    from app.api.routes.diagnostic import diagnostic_adresse

    try:
        return await diagnostic_adresse(q=adresse)
    except HTTPException:
        logger.warning("usine -- adresse site indisponible (%r), repli score neutre", adresse)
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("usine -- adresse site en erreur (%r): %s", adresse, exc)
        return None


class DiagnosticUsineRequest(BaseModel):
    adresse: str | None = Field(default=None, description="Adresse du site industriel")
    plan: dict = Field(..., description="Plan usine extrait par le VLM")


@router.post("/diagnostic/usine")
async def diagnostic_usine(payload: DiagnosticUsineRequest) -> dict:
    """Pipeline usine complet : enrichissement du score avec le plan.

    `adresse` (optionnelle) alimente le contexte d'aléa du site via Géorisques
    (même moteur que /zone) : le risque de chaque zone et équipement combine
    alors cet aléa F avec sa vulnérabilité V. Sans adresse, F = 50 (neutre).
    """
    logger.info("POST /diagnostic/usine  adresse=%r", payload.adresse)
    t0 = time.perf_counter()

    try:
        aleas_site = None
        if payload.adresse:
            report = await _rapport_site(payload.adresse)
            aleas_site = _contexte_alea_site(report) if report else None

        resultat = compute_usine_risk(payload.plan, aleas_site=aleas_site)
    except Exception as exc:
        logger.exception("diagnostic/usine -- echec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/usine OK en %.2fs", elapsed)
    return resultat


@router.post("/diagnostic/usine/analyze")
async def analyze_plan(
    file: UploadFile = File(..., description="Image du plan (JPG, PNG) ou fichier JSON/GeoJSON")
) -> dict:
    """
    Analyse un plan d'usine : image via Mistral Vision, fichier JSON/GeoJSON
    parsé directement.

    Retourne les zones et equipements detectes pour enrichir le score :
    {nom_usine, confiance_globale, zones: [...], equipements: [...]}.
    """
    logger.info(
        "POST /diagnostic/usine/analyze  filename=%r  content_type=%r",
        file.filename,
        file.content_type,
    )

    name = (file.filename or "").lower()
    is_image = bool(file.content_type and file.content_type.startswith("image/"))
    is_json = name.endswith(".json") or name.endswith(".geojson")

    if not is_image and not is_json:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_file_type",
                "detail": "Type de fichier non supporte. Utilisez une image (JPG, PNG), un fichier JSON (.json) ou GeoJSON (.geojson)",
            },
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=422,
                detail={"error": "empty_file", "detail": "Le fichier est vide"},
            )

        if is_json:
            return _analyser_fichier_struct(fname=file.filename or "plan.json", content=content)

        from app.connectors.mistral_vision import analyze_plan_image, _encode_image_bytes

        result = await asyncio.to_thread(
            analyze_plan_image, image_base64=_encode_image_bytes(content)
        )

        logger.info(
            "POST /diagnostic/usine/analyze OK: %d zones, %d equipements",
            len(result.get("zones", [])),
            len(result.get("equipements", [])),
        )

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("POST /diagnostic/usine/analyze -- echec")
        raise HTTPException(
            status_code=502,
            detail={"error": "plan_analysis_failed", "detail": str(exc)},
        ) from exc


def _analyser_fichier_struct(fname: str, content: bytes) -> dict:
    """Parse un JSON/GeoJSON de plan en zones/équipements normalisés."""
    try:
        raw = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_json", "detail": f"Fichier JSON illisible : {exc}"},
        ) from exc

    zones: list[dict] = []
    equipements: list[dict] = []
    nom_usine = "Usine"

    if isinstance(raw, dict) and raw.get("type") == "FeatureCollection" and isinstance(raw.get("features"), list):
        # GeoJSON : chaque Feature est une zone (footprint).
        for i, feat in enumerate(raw["features"]):
            props = feat.get("properties") or {}
            zone = {
                "id": props.get("id") or f"z_geo_{i}",
                "nom": props.get("nom") or props.get("name") or f"Zone {i + 1}",
                "type": props.get("type") or "production",
                "surface_m2": props.get("surface_m2"),
            }
            zones.append(zone)
    elif isinstance(raw, dict):
        zones = raw.get("zones") or []
        equipements = raw.get("equipements") or []
        nom_usine = raw.get("nom_usine") or "Usine"
    else:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_json", "detail": "Structure JSON non reconnue (FeatureCollection, ou {zones, equipements})"},
        )

    if not zones and not equipements:
        raise HTTPException(
            status_code=422,
            detail={"error": "empty_plan", "detail": "Aucune zone ni équipement détecté dans le fichier"},
        )

    # Normalisation minimale : ids + noms par défaut.
    normalized_zones = []
    for i, z in enumerate(zones):
        if not isinstance(z, dict):
            continue
        normalized_zones.append({
            "id": z.get("id") or f"z_{i}",
            "nom": z.get("nom") or f"Zone {i + 1}",
            "type": z.get("type") or "production",
            "surface_m2": z.get("surface_m2"),
            "confiance": z.get("confiance", 0.9),
        })
    normalized_eqs = []
    for i, e in enumerate(equipements):
        if not isinstance(e, dict):
            continue
        normalized_eqs.append({
            "id": e.get("id") or f"e_{i}",
            "nom": e.get("nom") or f"Équipement {i + 1}",
            "type": e.get("type") or "autre",
            "zone": e.get("zone"),
            "valeur_remplacement_eur": e.get("valeur_remplacement_eur"),
            "matieres_dangereuses": bool(e.get("matieres_dangereuses", False)),
            "critique_production": bool(e.get("critique_production", False)),
            "confiance": e.get("confiance", 0.9),
        })

    logger.info(
        "POST /diagnostic/usine/analyze (struct) OK: %d zones, %d equipements",
        len(normalized_zones), len(normalized_eqs),
    )
    return {
        "nom_usine": nom_usine,
        "confiance_globale": 1.0,
        "zones": normalized_zones,
        "equipements": normalized_eqs,
    }
