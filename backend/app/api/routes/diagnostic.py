"""sx
Routes de diagnostic Typhoon.

Routes actives :
  POST /diagnostic             → diagnostic complet (graphe LangGraph)
  POST /diagnostic/fast        → rapide (collecte + scoring seulement)
  POST /diagnostic/recommandations → phase 2 (RAG + interprétation)
  GET  /diagnostic/adresse     → MVP géo-risque : adresse → Géorisques → RisqueReport
                                  (+ recommandations Mistral non bloquantes)
"""

from __future__ import annotations

import asyncio
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query, File, UploadFile
from pydantic import BaseModel, Field

from app.agents import digital_twin_agent, interpretation_agent, recommandations_agent, scoring_agent
from app.agents.collector_agent import collect
from app.agents.graph import diagnostic_graph
from app.connectors.geocoding import GeocodingError, geocode_address
from app.connectors.georisques import get_risque_report
from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.adresse_recommandations import recommander
from app.recommandations.rapport_narratif import generer_rapport_narratif
from app.schemas.risque_report import RisqueReport, TypeBatiment
from app.scoring.plan_usine import enrichir_avec_plan

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Diagnostic complet (jumeau numérique 3D)
# ---------------------------------------------------------------------------

class DiagnosticRequest(BaseModel):
    adresse: str = Field(..., min_length=3, description="Adresse postale complète du bien")
    formulaire: dict | None = Field(
        default=None,
        description="Champs geometry saisis explicitement (priorité sur l'inférence BDNB).",
    )
    copernicus: bool = Field(
        default=settings.copernicus_enabled,
        description="Activer/désactiver Copernicus (CDS) dans la collecte.",
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
        logger.exception("diagnostic -- échec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    elapsed = time.perf_counter() - t0
    digital_twin = final_state.get("digital_twin")
    if digital_twin is None:
        logger.error("diagnostic -- aucun contrat produit en %.2fs", elapsed)
        raise HTTPException(status_code=502, detail="Le graphe n'a pas produit de contrat digital_twin.")

    logger.info("diagnostic OK en %.2fs (thread_id=%s)", elapsed, thread_id)
    logger.info("=" * 70)
    return digital_twin


@router.post("/diagnostic/fast")
async def run_diagnostic_fast(payload: DiagnosticRequest) -> dict:
    """Variante rapide : collecte + scoring + assemblage. Sans RAG ni interprétation LLM."""
    logger.info("=" * 70)
    logger.info("POST /diagnostic/fast  adresse=%r", payload.adresse)
    t0 = time.perf_counter()

    try:
        building_data = await collect(payload.adresse, enable_copernicus=payload.copernicus)
        state: dict = {"building_data": building_data, "formulaire": payload.formulaire}
        state.update(scoring_agent.run(state))
        state.update(digital_twin_agent.run(state))
    except Exception as exc:
        logger.exception("diagnostic/fast -- échec pour %r", payload.adresse)
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu être assemblé.")

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
    building_data: dict = Field(..., description="Tel que renvoyé par /diagnostic/fast (_resume.building_data)")
    risk_scores: dict = Field(..., description="Tel que renvoyé par /diagnostic/fast (_resume.risk_scores)")
    formulaire: dict | None = Field(default=None)


@router.post("/diagnostic/recommandations")
async def run_diagnostic_recommandations(payload: DiagnosticRecommandationsRequest) -> dict:
    """Phase 2 lente : RAG (Mistral) + interprétation LLM. Ne relance PAS la collecte."""
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
        logger.exception("diagnostic/recommandations -- échec")
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc

    digital_twin = state.get("digital_twin")
    if digital_twin is None:
        raise HTTPException(status_code=502, detail="Le contrat digital_twin n'a pas pu être assemblé.")

    elapsed = time.perf_counter() - t0
    logger.info("diagnostic/recommandations OK en %.2fs", elapsed)
    logger.info("=" * 70)
    return digital_twin


# ---------------------------------------------------------------------------
# MVP Géo-risque : adresse → Géorisques → RisqueReport
# ---------------------------------------------------------------------------

@router.get("/diagnostic/adresse")
async def diagnostic_adresse(
    q: str = Query(..., min_length=3, description="Adresse française (texte libre)")
) -> dict:
    """
    Flux souverain : adresse saisie → géocodage IGN (Géoplateforme) → Géorisques → RisqueReport.

    Codes de retour :
      200 : rapport complet (peut contenir erreurs_partielles si une sous-API a échoué)
      422 : adresse non trouvée par l'IGN (score_geocodage < 0.4 ou zéro résultat)
      502 : Géorisques totalement indisponible
    """
    logger.info("GET /diagnostic/adresse  q=%r", q)
    t0 = time.perf_counter()

    # Timeout global de sécurité pour éviter les requêtes infinies
    try:
        result = await asyncio.wait_for(
            _diagnostic_adresse_impl(q),
            timeout=60.0  # 60 secondes max pour tout le diagnostic
        )
        return result
    except asyncio.TimeoutError:
        logger.error("diagnostic/adresse -- timeout global après 60s pour %r", q)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "timeout",
                "detail": "Le diagnostic a pris trop de temps. Réessayez ou utilisez une adresse plus précise."
            }
        )


async def _diagnostic_adresse_impl(q: str) -> dict:
    """Implémentation du diagnostic avec timeout global."""
    logger.info("=" * 70)
    logger.info("GET /diagnostic/adresse  q=%r", q)
    t0 = time.perf_counter()

    # Étape 1 & 2 & 3 — Géocodage IGN + Géorisques → RisqueReport normalisé
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                geo = await geocode_address(client, q)
            except GeocodingError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "adresse_non_trouvee", "detail": str(exc)},
                ) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail={"error": "geocodage_indisponible", "detail": str(exc)},
                ) from exc

            # Rejeter si score de géocodage trop bas (adresse ambiguë)
            if geo.score < 0.3:  # Seuil abaissé à 0.3 pour plus de tolérance
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "adresse_ambigue",
                        "detail": f"Score de géocodage trop faible ({geo.score:.2f}) pour «{q}». Essayez avec une adresse plus précise (ex: numéro de rue).",
                        "label_propose": geo.label,
                    },
                )

            report = await get_risque_report(
                client=client,
                adresse_saisie=q,
                adresse_normalisee=geo.label,
                lat=geo.lat,
                lon=geo.lon,
                code_insee=geo.citycode,
            )

            # Détection du type de bâtiment via Overpass (OSM) — non bloquant :
            # si Overpass échoue, type_batiment reste None (analyse niveau 1 intacte).
            try:
                from app.connectors.overpass import detecter_type_batiment_osm
                type_bat = await detecter_type_batiment_osm(client, geo.lat, geo.lon)
                report.type_batiment = TypeBatiment(**type_bat)
                logger.info(
                    "diagnostic/adresse -- type_batiment=%s confiance=%.2f",
                    type_bat.get("type"), type_bat.get("confiance", 0),
                )
            except Exception as exc:
                logger.warning("diagnostic/adresse -- Overpass échec : %s", exc)
                report.type_batiment = None
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("diagnostic/adresse -- Échec du diagnostic pour %r", q)
        raise HTTPException(
            status_code=502,
            detail={"error": "source_indisponible", "source": "georisques", "detail": str(exc)},
        ) from exc

    # Étape 4 — Recommandations Mistral (non bloquant : fail-soft, toujours après le rapport factuel)
    report.recommandations = await recommander(report)

    elapsed = time.perf_counter() - t0
    logger.info(
        "diagnostic/adresse OK en %.2fs — %d aléas, %d erreurs partielles, recommandations=%s",
        elapsed, report.alea_count, len(report.erreurs_partielles),
        "ok" if report.recommandations else "none",
    )

    return report.model_dump()


# ---------------------------------------------------------------------------
# Endpoint de test rapide (sans recommandations) pour vérifier que le
# diagnostic fonctionne avant de lancer le pipeline complet.
# ---------------------------------------------------------------------------

@router.get("/diagnostic/adresse/test")
async def diagnostic_adresse_test(
    q: str = Query(..., min_length=3, description="Adresse française (texte libre)")
) -> dict:
    """
    Version de test du diagnostic : géocodage + Géorisques uniquement.
    Plus rapide (pas de recommandations Mistral) pour vérifier que le
    diagnostic fonctionne.
    """
    logger.info("GET /diagnostic/adresse/test  q=%r", q)

    try:
        result = await asyncio.wait_for(
            _diagnostic_adresse_test_impl(q),
            timeout=45.0  # 45 secondes max
        )
        return result
    except asyncio.TimeoutError:
        logger.error("diagnostic/adresse/test -- timeout global après 45s pour %r", q)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "timeout",
                "detail": "Le test de diagnostic a pris trop de temps. Vérifiez votre connexion internet."
            }
        )


async def _diagnostic_adresse_test_impl(q: str) -> dict:
    """Implémentation du test de diagnostic."""
    from app.connectors.geocoding import geocode_address
    from app.connectors.georisques import get_risque_report

    logger.info("=" * 70)
    logger.info("GET /diagnostic/adresse/test  q=%r", q)
    t0 = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            try:
                geo = await geocode_address(client, q)
            except Exception as exc:
                logger.error("test -- géocodage échoué: %s", exc)
                raise HTTPException(
                    status_code=422,
                    detail={"error": "geocodage_echoue", "detail": str(exc)},
                )

            logger.info("test -- géocodage OK: %s (%.2fs)", geo.label, time.perf_counter() - t0)

            try:
                report = await get_risque_report(
                    client=client,
                    adresse_saisie=q,
                    adresse_normalisee=geo.label,
                    lat=geo.lat,
                    lon=geo.lon,
                    code_insee=geo.citycode,
                )
            except Exception as exc:
                logger.error("test -- Géorisques échoué: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail={"error": "georisques_echoue", "detail": str(exc)},
                )

            elapsed = time.perf_counter() - t0
            logger.info(
                "test OK en %.2fs — %d aléas, %d erreurs partielles",
                elapsed, report.alea_count, len(report.erreurs_partielles),
            )

            return {
                "adresse": report.adresse_normalisee,
                "lat": report.lat,
                "lon": report.lon,
                "code_insee": report.code_insee,
                "alea_count": report.alea_count,
                "aleas": [
                    {
                        "code": a.code,
                        "libelle": a.libelle,
                        "present": a.present,
                        "niveau": a.niveau.value if a.niveau else None,
                    }
                    for a in report.aleas
                ],
                "erreurs_partielles": report.erreurs_partielles,
                "temps_diagnostic": round(elapsed, 2),
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("test -- échec inattendu")
        raise HTTPException(
            status_code=502,
            detail={"error": "test_echoue", "detail": str(exc)},
        ) from exc


@router.post("/diagnostic/adresse/rapport")
async def generer_rapport_narratif_adresse(report: RisqueReport) -> dict:
    """
    Génère un rapport narratif complet structuré par IA (Mistral) à partir d'un RisqueReport.

    Découplé de GET /diagnostic/adresse pour éviter tout impact sur la latence du rapport factuel.
    Fail-soft : retourne 502 si Mistral est indisponible.
    """
    narratif = await generer_rapport_narratif(report)
    if narratif is None:
        if not settings.mistral_api_key:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "mistral_api_key_manquante",
                    "detail": (
                        "Impossible de générer le rapport narratif IA tant que MISTRAL_API_KEY "
                        "n'est pas configurée côté backend."
                    ),
                },
            )
        raise HTTPException(
            status_code=502,
            detail={"error": "mistral_indisponible", "detail": "Impossible de générer le rapport narratif IA."},
        )
    return narratif.model_dump()


@router.get("/diagnostic/adresse/rapport-pdf")
async def rapport_pdf_officiel(
    lat: float = Query(..., description="Latitude WGS84"),
    lon: float = Query(..., description="Longitude WGS84"),
):
    """
    Proxy vers l'endpoint officiel Géorisques /api/v1/rapport_pdf.

    Renvoie le PDF binaire tel quel (Content-Type: application/pdf).
    Paramètre latlon = lon,lat (longitude d'abord — conforme à l'API Géorisques v1).

    Codes de retour :
      200 : PDF binaire
      404 : Géorisques ne peut pas générer de rapport pour ces coordonnées
            (adresse non reconnue côté BRGM — comportement connu, à gérer côté UI)
      502 : Géorisques indisponible ou timeout
    """
    from fastapi import Response as FastAPIResponse

    georisques_pdf_url = "https://www.georisques.gouv.fr/api/v1/rapport_pdf"
    params = {"latlon": f"{lon},{lat}"}

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(georisques_pdf_url, params=params)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "rapport_pdf_timeout", "detail": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "rapport_pdf_indisponible", "detail": str(exc)},
        ) from exc

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail={"error": "rapport_pdf_indisponible", "detail": "Géorisques ne peut pas générer de rapport PDF pour ces coordonnées."},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={"error": "rapport_pdf_erreur", "detail": f"Géorisques a retourné HTTP {resp.status_code}"},
        )

    return FastAPIResponse(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"georisques_rapport_{lat:.4f}_{lon:.4f}.pdf\""},
    )


# ---------------------------------------------------------------------------
# Plan d'usine (niveau 2 — enrichissement du score avec équipements/zones)
# ---------------------------------------------------------------------------

class PlanUsineRequest(BaseModel):
    """Plan d'usine optionnel — enrichit le score de risque niveau 1."""
    risk_scores: dict = Field(..., description="Résultat de compute_risk_scores() (niveau 1)")
    plan: dict = Field(..., description="{nom_usine, equipements: [...], zones: [...]}")
    adresse: str | None = Field(default=None, description="Adresse du site (optionnel)")


@router.post("/diagnostic/plan-usine")
async def enrichir_plan_usine(payload: PlanUsineRequest) -> dict:
    """Enrichit les risk_scores avec le plan d'usine (niveau 2).

    Body :
      - risk_scores : résultat de compute_risk_scores() (niveau 1)
      - plan : {nom_usine, equipements: [{nom, type, zone, valeur_remplacement_eur,
               matieres_dangereuses, critique_production}], zones: [{id, nom, type, surface_m2}]}

    Retourne les risk_scores enrichis avec :
      - plan_usine.zones_plan : vulnérabilité par zone
      - plan_usine.score_plan_global : score global du plan
      - plan_usine.confiance_plan : confiance augmentée
    """
    try:
        resultat = enrichir_avec_plan(payload.risk_scores, payload.plan)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"error": "plan_usine_calcul", "detail": str(exc)})

    logger.info(
        "POST /diagnostic/plan-usine  adresse=%r  zones=%d  equipements=%d",
        payload.adresse, len(payload.plan.get("zones", []) or []), len(payload.plan.get("equipements", []) or []),
    )
    return resultat


@router.post("/diagnostic/plan-usine/analyze")
async def analyze_plan_image(
    file: UploadFile = File(..., description="Image du plan (JPG, PNG, etc.)")
) -> dict:
    """
    Analyse un plan d'usine à partir d'une image via Mistral Vision.

    Accepte tous les formats d'image (JPG, PNG, etc.) et retourne :
      - zones détectées avec types et surfaces estimées
      - équipements détectés avec types et valeurs estimées
      - nom de l'usine si détecté
      - score de confiance global

    Le résultat peut être utilisé dans /diagnostic/plan-usine pour enrichir le score de risque.
    """
    logger.info("POST /diagnostic/plan-usine/analyze  filename=%r  content_type=%r", file.filename, file.content_type)

    # Vérifier le type de fichier
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_file_type", "detail": f"Type de fichier non supporté: {file.content_type}. Utilisez une image (JPG, PNG, etc.)"}
        )

    try:
        from app.connectors.mistral_vision import analyze_plan_image, _encode_image_bytes
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "mistral_vision_import", "detail": f"Impossible de charger le module de vision: {exc}"}
        )

    try:
        # Lire l'image
        image_bytes = await file.read()

        if len(image_bytes) == 0:
            raise HTTPException(
                status_code=422,
                detail={"error": "empty_file", "detail": "Le fichier image est vide"}
            )

        # Analyser avec Mistral Vision (appel asynchrone)
        result = await asyncio.to_thread(analyze_plan_image, image_base64=_encode_image_bytes(image_bytes))

        logger.info(
            "POST /diagnostic/plan-usine/analyze OK: %d zones, %d équipements",
            len(result.get("zones", [])),
            len(result.get("equipements", [])),
        )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("POST /diagnostic/plan-usine/analyze -- échec")
        raise HTTPException(
            status_code=502,
            detail={"error": "plan_analysis_failed", "detail": str(exc)}
        ) from exc


