from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_assess_zone_single_point():
    fake_point_res = {
        "address_label": "10 Rue de la Paix 75002 Paris",
        "lat": 48.8687,
        "lon": 2.3312,
        "hazards": [
            {"hazard": "inondation", "label": "Inondation", "level": "Present", "score": 60.0}
        ],
        "catnat_total": 2,
        "catnat_by_type": {"inondation": 2, "secheresse": 0, "mouvement_terrain": 0, "total": 2},
        "distance_cours_eau_m": 420.0,
        "distance_foret_m": 1250.0,
        "bdnb_cle_interop_adr": "75102_6845_00010",
        "bdnb_geom": None,
        "source": "live",
        "score_global": 60.0,
        "errors": [{"source": "georisques", "ok": True}],
    }

    with patch("app.api.routes.zone.collect_point", new_callable=AsyncMock) as mock_collect:
        mock_collect.return_value = fake_point_res

        payload = {
            "mode": "single",
            "points": [{"lat": 48.8687, "lon": 2.3312}],
            "address": "10 Rue de la Paix 75002 Paris",
        }
        response = client.post("/zone/assess", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["address"] == "10 Rue de la Paix 75002 Paris"
        assert data["nb_points"] == 1
        assert data["aggregate_score"] == 60.0
        assert data["aggregate_tier"] == "eleve"
        assert data["report_schema_version"] == "1.0"
        assert data["data_sources_ok"] == ["georisques"]
        assert data["catnat_totals"]["inondation"] == 2
        assert len(data["buildings"]) == 1
        assert data["buildings"][0]["data_quality"] == "ok"
