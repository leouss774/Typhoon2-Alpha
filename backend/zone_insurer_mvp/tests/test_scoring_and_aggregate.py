import pytest

from app.scoring.zone_hazard_scores import apply_hazard_scores, score_hazard, score_to_tier
from app.services.catnat_parse import parse_catnat_from_georisques
from app.services.zone_aggregator import aggregate


def test_score_to_tier():
    assert score_to_tier(10) == "faible"
    assert score_to_tier(45) == "modere"
    assert score_to_tier(70) == "eleve"
    assert score_to_tier(90) == "critique"


def test_inondation_proximity():
    base = score_hazard("inondation", "Moyen", distance_cours_eau_m=50)
    assert base >= 63


def test_apply_hazard_scores_sets_global():
    point = {
        "hazards": [
            {"hazard": "inondation", "label": "Inondation", "level": "Moyen"},
            {"hazard": "radon", "label": "Radon", "level": "Faible"},
        ],
        "distance_cours_eau_m": 200,
        "distance_foret_m": None,
    }
    apply_hazard_scores(point)
    assert point["score_global"] > 0
    assert all(h.get("score") is not None for h in point["hazards"])


def test_parse_catnat_by_type():
    geo = {
        "catnat": {
            "data": [
                {"libelle_risque_jo": "Inondation et crue"},
                {"libelle_risque_jo": "Secheresse"},
            ]
        }
    }
    counts = parse_catnat_from_georisques(geo)
    assert counts["inondation"] == 1
    assert counts["secheresse"] == 1
    assert counts["total"] == 2


def test_aggregate_catnat_sums_buildings():
    results = [
        {
            "source": "live",
            "hazards": [{"hazard": "inondation", "label": "x", "level": "Present", "score": 50}],
            "catnat_by_type": {"inondation": 2, "secheresse": 0, "mouvement_terrain": 0, "total": 2},
            "score_global": 50,
            "errors": [{"source": "georisques", "ok": True}],
        },
        {
            "source": "live",
            "hazards": [],
            "catnat_by_type": {"inondation": 1, "secheresse": 1, "mouvement_terrain": 0, "total": 2},
            "score_global": 0,
            "errors": [{"source": "georisques", "ok": True}],
        },
    ]
    agg = aggregate(results)
    assert agg["catnat_totals"]["inondation"] == 3
    assert agg["catnat_totals"]["secheresse"] == 1
    assert agg["aggregate_score"] == 50.0
