from app.recommandations.mapping import _infer_risques
from app.recommandations.service import _search


def test_low_but_real_supported_risk_is_kept():
    zone = {"risque": 31, "niveau": "faible", "alea_principal": "Feu de forêt", "justification": "Risque calculé."}
    assert _infer_risques("toiture", zone) == ["feu_vegetation"]


def test_score_below_twenty_has_no_recommendation():
    zone = {"risque": 19, "niveau": "tres_faible", "alea_principal": "Feu de forêt", "justification": "Risque calculé."}
    assert _infer_risques("toiture", zone) == []


def test_unknown_risk_has_no_invented_zone_fallback():
    zone = {"risque": 70, "niveau": "eleve", "alea_principal": "Séisme", "justification": "Zone 4."}
    assert _infer_risques("fondations", zone) == []


def test_rag_search_never_returns_another_hazard():
    index = [{"fiche": {"alea": "tempete", "zone_maison": "toiture"}, "vector": [1.0, 0.0]}]
    assert _search(index, [1.0, 0.0], 5, alea="inondation") == []


def test_combined_reference_matches_exact_hazard_token():
    fiche = {"alea": "canicule|secheresse", "zone_maison": "toiture"}
    index = [{"fiche": fiche, "vector": [1.0, 0.0]}]
    assert _search(index, [1.0, 0.0], 5, alea="canicule") == [fiche]
