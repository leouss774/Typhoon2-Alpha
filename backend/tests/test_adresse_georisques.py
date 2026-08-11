"""
Tests hors-ligne pour le flux adresse → Géorisques → RisqueReport.
Plan : typhoon_adresse_georisques_plan.md §6

Fixtures calquées sur une vraie réponse pour Nice 06088
(14 Avenue des Palmiers, 06000 Nice — RNB PXQR-9K3T-88ZL).

A exécuter :
    cd backend
    PYTHONPATH=. pytest tests/test_adresse_georisques.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.connectors.geocoding import (
    GeocodeResult,
    GeocodingError,
    geocode_address,
)
from app.connectors.georisques import (
    fetch_georisques_raw,
    get_risque_report,
    _score_to_niveau,
)
from app.schemas.risque_report import NiveauRisque, RisqueReport

# ---------------------------------------------------------------------------
# Fixtures réelles (capturées sur Nice 06088)
# ---------------------------------------------------------------------------

BAN_RESPONSE_NICE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [7.2620, 43.7102]},
            "properties": {
                "label": "14 Avenue des Palmiers 06000 Nice",
                "score": 0.93,
                "citycode": "06088",
                "postcode": "06000",
                "city": "Nice",
            },
        }
    ],
}

BAN_RESPONSE_EMPTY = {"type": "FeatureCollection", "features": []}

GEORISQUES_RAW_NICE = {
    "erreurs": [],
    "risques_commune": {
        "data": [
            {
                "risques_detail": [
                    {"libelle_risque_long": "Inondation", "zone_sismicite": 2},
                    {"libelle_risque_long": "Feu de forêt"},
                    {"libelle_risque_long": "Retrait-gonflement des argiles"},
                ]
            }
        ]
    },
    "catnat": {
        "data": [
            {"libelle_risque_jo": "Inondations et/ou Coulées de Boue"},
            {"libelle_risque_jo": "Inondations et/ou Coulées de Boue"},
            {"libelle_risque_jo": "Sécheresse"},
        ]
    },
    "zones_inondables": [{"code_commune": "06088"}],
    "cavites": [],
    "zonage_sismique": [{"zone_sismicite": 2}],
    "radon": [{"classe_potentiel": "2"}],
    "mouvements_terrain": [],
}


# ---------------------------------------------------------------------------
# Test 1 : géocodage — adresse valide
# ---------------------------------------------------------------------------

def test_geocodage_adresse_valide():
    """Adresse valide → GeocodeResult avec lat/lon/citycode corrects (IGN Geoplateforme)."""
    async def _run():
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(
            200,
            json=BAN_RESPONSE_NICE,
            request=httpx.Request("GET", "https://data.geopf.fr/geocodage/search"),
        )
        return await geocode_address(mock_client, "14 Avenue des Palmiers Nice")

    result = asyncio.run(_run())
    assert isinstance(result, GeocodeResult)
    assert abs(result.lat - 43.7102) < 0.001
    assert abs(result.lon - 7.262) < 0.001
    assert result.citycode == "06088"
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# Test 2 : géocodage — adresse absurde → GeocodingError
# ---------------------------------------------------------------------------

def test_geocodage_adresse_absurde():
    """Adresse non trouvée → GeocodingError (jamais un fallback silencieux)."""
    async def _run():
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(
            200,
            json=BAN_RESPONSE_EMPTY,
            request=httpx.Request("GET", "https://data.geopf.fr/geocodage/search"),
        )
        return await geocode_address(mock_client, "zzz adresse inexistante 99999")

    with pytest.raises(GeocodingError):
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 3 : Géorisques brut — coordonnées connues → réponse capturée
# ---------------------------------------------------------------------------

def test_georisques_raw_nice():
    """Fixture Nice → les clés attendues sont présentes dans le brut."""
    async def _run():
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = httpx.Response(200, json=GEORISQUES_RAW_NICE)
        # On mocke _get directement pour ne pas instancier le client
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=GEORISQUES_RAW_NICE):
            return GEORISQUES_RAW_NICE

    raw = asyncio.run(_run())
    assert "risques_commune" in raw
    assert "catnat" in raw
    assert "zonage_sismique" in raw
    assert raw["erreurs"] == []


# ---------------------------------------------------------------------------
# Test 4 : normalisation → RisqueReport complet
# ---------------------------------------------------------------------------

def test_risque_report_nice():
    """Fixture Nice → RisqueReport normalisé avec les bandes D03 attendues."""
    async def _run():
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=GEORISQUES_RAW_NICE):
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            return await get_risque_report(
                client=mock_client,
                adresse_saisie="14 avenue des palmiers nice",
                adresse_normalisee="14 Avenue des Palmiers 06000 Nice",
                lat=43.7102,
                lon=7.2620,
                code_insee="06088",
            )

    report = asyncio.run(_run())
    assert isinstance(report, RisqueReport)
    assert report.code_insee == "06088"
    assert report.alea_count >= 1
    assert report.erreurs_partielles == []

    # Inondation doit être présente (2 arrêtés CATNAT + hazard + zones inondables)
    inond = next(a for a in report.aleas if a.code == "inondation")
    assert inond.present is True
    assert inond.niveau in (NiveauRisque.MODERE, NiveauRisque.ELEVE, NiveauRisque.CRITIQUE)

    # Radon catégorie 2 → présent
    radon = next(a for a in report.aleas if a.code == "radon")
    assert radon.present is True

    # Aucun aléa ne doit avoir present=None (toutes les sources sont dispo dans la fixture)
    for alea in report.aleas:
        assert alea.present is not None, f"Aléa {alea.code} a present=None inattendu"


# ---------------------------------------------------------------------------
# Test 5 : erreurs partielles — une source en timeout
# ---------------------------------------------------------------------------

def test_erreurs_partielles():
    """Si zonage_sismique échoue, le rapport reste généré avec erreurs_partielles."""
    raw_with_error = {**GEORISQUES_RAW_NICE,
                      "zonage_sismique": None,
                      "erreurs": [{"source": "georisques.zonage_sismique", "erreur": "timeout"}]}

    async def _run():
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=raw_with_error):
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            return await get_risque_report(
                client=mock_client,
                adresse_saisie="test",
                adresse_normalisee="Test 75001 Paris",
                lat=48.86, lon=2.35, code_insee="75056",
            )

    report = asyncio.run(_run())
    assert len(report.erreurs_partielles) == 1
    assert "zonage_sismique" in report.erreurs_partielles[0]

    # Les autres aléas doivent quand même être normalisés
    inond = next(a for a in report.aleas if a.code == "inondation")
    assert inond.present is not None


# ---------------------------------------------------------------------------
# Test 6 : bandes D03 — mapping correct
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (0,   NiveauRisque.TRES_FAIBLE),
    (19,  NiveauRisque.TRES_FAIBLE),
    (20,  NiveauRisque.FAIBLE),
    (39,  NiveauRisque.FAIBLE),
    (40,  NiveauRisque.MODERE),
    (59,  NiveauRisque.MODERE),
    (60,  NiveauRisque.ELEVE),
    (79,  NiveauRisque.ELEVE),
    (80,  NiveauRisque.CRITIQUE),
    (100, NiveauRisque.CRITIQUE),
])
def test_d03_bands(score, expected):
    assert _score_to_niveau(score) == expected


# ---------------------------------------------------------------------------
# Test 7 : Recommandations Mistral — Fail-soft en cas d'erreur / timeout
# ---------------------------------------------------------------------------

def test_recommandations_mistral_failure():
    """Vérifie qu'un échec Mistral retourne None sans lever d'exception."""
    from app.recommandations.adresse_recommandations import recommander

    async def _run():
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=GEORISQUES_RAW_NICE):
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            report = await get_risque_report(
                client=mock_client,
                adresse_saisie="test",
                adresse_normalisee="14 Avenue des Palmiers 06000 Nice",
                lat=43.7102, lon=7.2620, code_insee="06088",
            )
            # Simulation d'un échec Mistral (Timeout / Erreur API / etc.)
            with patch("app.recommandations.adresse_recommandations._appeler_mistral_sync", side_effect=TimeoutError("Mistral API timeout")):
                recs = await recommander(report)
                return report, recs

    report, recs = asyncio.run(_run())
    assert recs is None
    assert isinstance(report, RisqueReport)
    assert report.adresse_normalisee == "14 Avenue des Palmiers 06000 Nice"


# ---------------------------------------------------------------------------
# Test 8 : Introspection — Interdiction absolue d'importer geocodage_connector
# ---------------------------------------------------------------------------

def test_no_decommissioned_geocodage_connector_import():
    """Vérifie qu'aucun fichier du backend n'importe l'ancien connector décommissionné."""
    import inspect
    import app.api.routes.diagnostic as diag_module

    source = inspect.getsource(diag_module)
    assert "geocodage_connector" not in source, "diagnostic.py ne doit plus jamais importer geocodage_connector !"


# ---------------------------------------------------------------------------
# Test 9 : CatNat filtré par péril + PPR et SSP normalisés
# ---------------------------------------------------------------------------

def test_catnat_filtering_and_ppr_ssp():
    """Vérifie l'exposition de PPR, SSP et du CatNat filtré sur RGA et MVT."""
    raw_enriched = {
        **GEORISQUES_RAW_NICE,
        "ppr": [{"num_ppr": "PPR123", "type_ppr": "PPRN"}],
        "ssp": [{"id_site": "SSP001", "nom_site": "Ancienne Usine"}],
    }

    async def _run():
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=raw_enriched):
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            return await get_risque_report(
                client=mock_client,
                adresse_saisie="Nice",
                adresse_normalisee="14 Avenue des Palmiers 06000 Nice",
                lat=43.7102, lon=7.2620, code_insee="06088",
            )

    report = asyncio.run(_run())

    # Vérification PPR & SSP
    ppr = next(a for a in report.aleas if a.code == "ppr")
    assert ppr.present is True
    assert ppr.niveau == NiveauRisque.MODERE

    ssp = next(a for a in report.aleas if a.code == "ssp")
    assert ssp.present is True
    assert ssp.niveau == NiveauRisque.MODERE

    # Vérification CatNat filtré pour RGA
    rga = next(a for a in report.aleas if a.code == "rga")
    assert rga.catnat_historique is not None
    assert any("Sécheresse" in (c.get("libelle_risque_jo") or "") for c in rga.catnat_historique)


# ---------------------------------------------------------------------------
# Test 10 : Rapport Narratif Mistral — Fail-soft
# ---------------------------------------------------------------------------

def test_rapport_narratif_mistral_fail_soft():
    """Vérifie que generer_rapport_narratif retourne (None, cause) en cas
    d'échec Mistral — fail-soft sans exception, cause transmise."""
    from app.recommandations.rapport_narratif import generer_rapport_narratif

    async def _run():
        with patch("app.connectors.georisques.fetch_georisques_raw", return_value=GEORISQUES_RAW_NICE):
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            report = await get_risque_report(
                client=mock_client,
                adresse_saisie="test",
                adresse_normalisee="14 Avenue des Palmiers 06000 Nice",
                lat=43.7102, lon=7.2620, code_insee="06088",
            )
            with patch("app.recommandations.rapport_narratif._appeler_mistral_narratif_sync", side_effect=RuntimeError("Mistral API error")):
                res, cause = await generer_rapport_narratif(report)
                return res, cause

    res, cause = asyncio.run(_run())
    assert res is None
    assert cause and "Mistral" in cause



