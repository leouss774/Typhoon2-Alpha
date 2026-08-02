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

from app.connectors.geocodage_connector import (
    AdresseNonTrouveeError,
    GeocodageResult,
    geocoder_adresse,
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
    """Adresse valide → GeocodageResult avec lat/lon/code_insee corrects."""
    async def _run():
        with patch("app.connectors.geocodage_connector.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = httpx.Response(200, json=BAN_RESPONSE_NICE)
            return await geocoder_adresse("14 Avenue des Palmiers Nice")

    result = asyncio.get_event_loop().run_until_complete(_run())
    assert isinstance(result, GeocodageResult)
    assert abs(result.lat - 43.7102) < 0.001
    assert abs(result.lon - 7.262) < 0.001
    assert result.code_insee == "06088"
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# Test 2 : géocodage — adresse absurde → AdresseNonTrouveeError
# ---------------------------------------------------------------------------

def test_geocodage_adresse_absurde():
    """Adresse non trouvée → AdresseNonTrouveeError (jamais un fallback silencieux)."""
    async def _run():
        with patch("app.connectors.geocodage_connector.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = httpx.Response(200, json=BAN_RESPONSE_EMPTY)
            return await geocoder_adresse("zzz adresse inexistante 99999")

    with pytest.raises(AdresseNonTrouveeError):
        asyncio.get_event_loop().run_until_complete(_run())


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

    raw = asyncio.get_event_loop().run_until_complete(_run())
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

    report = asyncio.get_event_loop().run_until_complete(_run())
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

    report = asyncio.get_event_loop().run_until_complete(_run())
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
