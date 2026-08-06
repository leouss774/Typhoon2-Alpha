"""
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
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents import digital_twin_agent, interpretation_agent, recommandations_agent, scoring_agent
from app.digital_twin.gltf_builder import build_glb_from_bdnb
from app.agents.collector_agent import collect
from app.agents.graph import diagnostic_graph
from app.connectors.bdnb import BdnbAdresseIntrouvable, fetch_bdnb
from app.connectors.geocoding import GeocodingError, geocode_address
from app.connectors.georisques import get_risque_report
from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.adresse_recommandations import recommander
from app.recommandations.rapport_narratif import generer_rapport_narratif
from app.schemas.risque_report import RisqueReport

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
        state.update(await asyncio.to_thread(interpretation_agent.run, state))
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

async def _fetch_bdnb_avec_repli(
    client: httpx.AsyncClient, address: str, label_ban: str
) -> dict | None:
    """Interroge BDNB avec repli de géocodage (même stratégie que
    collector_agent) : le géocodeur BDNB préfère le libellé BAN normalisé
    (`geocode.label`), mais on retente avec l'adresse brute si la première
    tentative échoue (ex. code postal approximatif saisi par l'utilisateur).
    """
    try:
        return await fetch_bdnb(client, label_ban)
    except BdnbAdresseIntrouvable:
        if label_ban == address:
            raise
        logger.info(
            "  [bdnb] libellé BAN non trouvé (%r), nouvel essai avec l'adresse brute (%r)",
            label_ban, address,
        )
        return await fetch_bdnb(client, address)


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
            if geo.score < 0.4:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "adresse_ambigue",
                        "detail": f"Score de géocodage trop faible ({geo.score:.2f}) pour «{q}». Précisez la ville ou le code postal.",
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

            # BDNB — fiche bâtiment (alimente l'étape 3 « Analyse » du frontend).
            # Non bloquant : en cas d'échec, report.bdnb reste None et l'erreur
            # est consignée dans erreurs_partielles (jamais un 502).
            try:
                report.bdnb = await _fetch_bdnb_avec_repli(client, q, geo.label)
            except BdnbAdresseIntrouvable:
                report.erreurs_partielles.append(
                    "bdnb: adresse non reconnue par le géocodeur BDNB"
                )
            except Exception as exc:
                logger.warning("  [bdnb] ECHEC pour %r -> %s: %s", q, type(exc).__name__, exc)
                report.erreurs_partielles.append(f"bdnb: {type(exc).__name__}: {exc}")
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
        "diagnostic/adresse OK en %.2fs — %d aléas, %d erreurs partielles, recommandations=%s, bdnb=%s",
        elapsed, report.alea_count, len(report.erreurs_partielles),
        "ok" if report.recommandations else "none",
        "ok" if report.bdnb else "none",
    )

    return report.model_dump()


@router.post("/diagnostic/adresse/rapport")
async def generer_rapport_narratif_adresse(report: RisqueReport) -> dict:
    """
    Génère un rapport narratif complet structuré par IA (Mistral) à partir d'un RisqueReport.

    Découplé de GET /diagnostic/adresse pour éviter tout impact sur la latence du rapport factuel.
    Fail-soft : retourne 502 si Mistral est indisponible, 503 si la clé API manque.

    Contrat d'erreur (detail JSON) :
      { "error": <code>, "detail": <message utilisateur>, "cause": <cause technique courte> }
    """
    narratif, cause = await generer_rapport_narratif(report)
    if narratif is not None:
        return narratif.model_dump()

    if cause == "api_key_manquante" or not settings.mistral_api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "mistral_api_key_manquante",
                "detail": (
                    "Le rapport IA nécessite une clé Mistral. Configurez MISTRAL_API_KEY "
                    "dans le .env du backend puis redémarrez l'API."
                ),
                "cause": "MISTRAL_API_KEY absente de la configuration backend",
            },
        )

    raise HTTPException(
        status_code=502,
        detail={
            "error": "mistral_indisponible",
            "detail": "Le service Mistral n'a pas pu générer le rapport. Réessayez dans quelques instants.",
            "cause": cause or "inconnue",
        },
    )


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


@router.get("/diagnostic/adresse/gltf")
async def diagnostic_adresse_gltf(
    q: str = Query(..., min_length=3, description="Adresse française (texte libre)"),
) -> "FastAPIResponse":
    """
    Renvoie un modèle 3D .glb du bâtiment correspondant à l'adresse donnée.

    Flux : géocodage IGN → BDNB (emprise sol + hauteur) → glTF 2.0 Binary.
    Repli automatique : si BDNB indisponible, renvoie un parallélépipède
    générique de 10×10×6 m.

    Content-Type : model/gltf-binary
    Content-Disposition : attachment; filename="batiment_<lat>_<lon>.glb"
    """
    from fastapi import Response as FastAPIResponse  # noqa: F811

    logger.info("GET /diagnostic/adresse/gltf  q=%r", q)

    # Step 1 — geocode
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                geo = await geocode_address(client, q)
            except GeocodingError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "adresse_non_trouvee", "detail": str(exc)},
                ) from exc

            if geo.score < 0.4:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "adresse_ambigue",
                        "detail": f"Score de géocodage trop faible ({geo.score:.2f}) — précisez la ville.",
                    },
                )

            # Step 2 — BDNB fetch (non-blocking failure)
            batiment: dict = {}
            try:
                bdnb = await _fetch_bdnb_avec_repli(client, q, geo.label)
                batiment = ((bdnb or {}).get("batiment") or {}) if isinstance(bdnb, dict) else {}
            except Exception as exc:
                logger.warning("  [gltf] BDNB indisponible pour %r -> %s: %s", q, type(exc).__name__, exc)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "gltf_geocodage_erreur", "detail": str(exc)},
        ) from exc

    # Step 3 — Build .glb (fallback to box if needed). Le point d'adresse
    # geocode (lat/lon) sert a poser la porte d'entree sur la facade rue.
    glb_bytes = build_glb_from_bdnb(
        batiment, adresse_label=geo.label, adresse_lat=geo.lat, adresse_lon=geo.lon
    )

    if glb_bytes is None:
        # Ultimate fallback: flat 10×10×6 m box
        from app.digital_twin.gltf_builder import build_glb
        ring = [(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)]
        glb_bytes = build_glb(ring, height_m=6.0, label=geo.label)

    lat_s = f"{geo.lat:.4f}".replace(".", "_")
    lon_s = f"{geo.lon:.4f}".replace(".", "_")

    return FastAPIResponse(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": f'attachment; filename="batiment_{lat_s}_{lon_s}.glb"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )
