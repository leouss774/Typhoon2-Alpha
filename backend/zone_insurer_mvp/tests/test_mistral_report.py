from __future__ import annotations

from unittest.mock import patch
import pytest

from app.services.mistral_report import generate, _build_user_prompt


def test_build_user_prompt():
    agg = {
        "nb_ok": 2,
        "nb_errors": 0,
        "aggregate_score": 55.0,
        "aggregate_tier": "modere",
        "hazard_breakdown": [
            {
                "label": "Inondation",
                "pct_present": 100.0,
                "levels": ["Present"],
                "mean_score": 60.0,
            }
        ],
        "catnat_totals": {"inondation": 2, "secheresse": 0, "mouvement_terrain": 0},
        "buildings": [
            {
                "address_label": "Test Address",
                "score_global": 60.0,
                "hazards": [{"hazard": "inondation", "level": "Present", "score": 60.0}],
            }
        ],
    }
    prompt = _build_user_prompt(agg)
    assert "Points OK: 2" in prompt
    assert "Score zone: 55.0/100, tier modere" in prompt
    assert "Inondation" in prompt


@pytest.mark.asyncio
async def test_generate_mistral_disabled():
    with patch("app.services.mistral_report.settings") as mock_settings:
        mock_settings.mistral_enabled = False
        mock_settings.mistral_api_key = None
        agg = {"narrative": "Fallback narrative", "recommendations": ["Rec 1"]}
        res, source = await generate(agg)
        assert source == "template"
        assert res["narrative"] == "Fallback narrative"


@pytest.mark.asyncio
async def test_generate_mistral_success():
    with patch("app.services.mistral_report.settings") as mock_settings, patch(
        "app.services.mistral_report.chat_json"
    ) as mock_chat:
        mock_settings.mistral_enabled = True
        mock_settings.mistral_api_key = "fake_key"
        mock_chat.return_value = {
            "narrative": "AI generated narrative.",
            "recommendations": ["AI Rec 1", "AI Rec 2"],
        }
        agg = {"narrative": "Fallback narrative", "recommendations": []}
        res, source = await generate(agg)
        assert source == "mistral"
        assert res["narrative"] == "AI generated narrative."
        assert len(res["recommendations"]) == 2
