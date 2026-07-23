"""Tests pour les services de scoring."""

from __future__ import annotations

from backend.services.scoring.score_global import (
    compute_all_scores,
    _score_rga,
    _score_inondation,
    _score_tempete,
)
from backend.services.scoring.weights import get_niveau_risque, get_couleur_risque


class TestScoreGlobal:
    """Teste le calcul des scores déterministes."""

    def test_compute_all_scores_return_structure(self, client_form_example, raw_data_example):
        """Vérifie la structure de retour."""
        result = compute_all_scores(client_form_example, raw_data_example)

        assert "score_global" in result
        assert "scores_par_alea" in result
        assert isinstance(result["score_global"], float)
        assert 0 <= result["score_global"] <= 100

    def test_score_rga_avec_argile_eleve(self):
        """Vérifie que l'exposition argile augmente le score."""
        form = {"sous_sol": True, "annee_construction": 1985}
        raw = {"exposition_argile": 0.9}
        score = _score_rga(form, raw)
        assert score > 50

    def test_score_rga_sans_argile(self):
        """Vérifie que sans exposition argile le score est bas."""
        form = {"sous_sol": False, "annee_construction": 2010}
        raw = {"exposition_argile": 0.0}
        score = _score_rga(form, raw)
        assert score < 30

    def test_score_inondation_zone_forte(self):
        """Vérifie le score en zone inondable."""
        form = {"sous_sol": True}
        raw = {"zone_ppri": "fort"}
        score = _score_inondation(form, raw)
        assert score >= 85

    def test_score_tempete_zone_vent_fort(self):
        """Vérifie le score en zone venteuse."""
        form = {"materiau_principal": "bois"}
        raw = {"zone_vent": 4}
        score = _score_tempete(form, raw)
        assert score > 50


class TestNiveauxRisque:
    """Teste les niveaux et couleurs de risque."""

    def test_niveaux(self):
        assert get_niveau_risque(10) == "faible"
        assert get_niveau_risque(30) == "modéré"
        assert get_niveau_risque(60) == "élevé"
        assert get_niveau_risque(80) == "critique"

    def test_couleurs(self):
        assert get_couleur_risque("faible") == "#22c55e"
        assert get_couleur_risque("critique") == "#ef4444"
