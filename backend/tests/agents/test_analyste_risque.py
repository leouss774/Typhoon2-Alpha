"""Tests pour l'Agent Analyste Risque."""

from __future__ import annotations

from backend.agents.analyste_risque.agent import analyser_risques, _convertir_en_analyse


class TestAnalysteRisque:
    """Teste l'analyse qualitative des risques."""

    def test_analyser_avec_scores_valides(self, client_form_example, scores_example):
        """Vérifie que l'analyse retourne une structure valide."""
        resultat = analyser_risques(
            client_form=client_form_example,
            scores_par_alea=scores_example,
            score_global=68.5,
        )

        assert resultat.scores_par_alea is not None
        assert len(resultat.scores_par_alea) > 0
        assert resultat.synthese != ""

    def test_risques_dominants_ordonnes(self, client_form_example, scores_example):
        """Vérifie que les risques dominants sont les plus scores."""
        resultat = analyser_risques(
            client_form=client_form_example,
            scores_par_alea=scores_example,
            score_global=68.5,
        )

        if resultat.risques_dominants:
            # Le premier risque dominant doit être rga (score le plus haut)
            assert "rga" in resultat.risques_dominants

    def test_conversion_json_valide(self):
        """Vérifie la conversion d'un JSON en objet AnalyseRisque."""
        parsed = {
            "scores_par_alea": [
                {"code": "rga", "label": "RGA", "score": 82.0, "niveau": "critique", "justification": "Test"}
            ],
            "risques_dominants": ["rga"],
            "synthese": "Synthèse de test",
        }
        analyse = _convertir_en_analyse(parsed)

        assert len(analyse.scores_par_alea) == 1
        assert analyse.scores_par_alea[0].code == "rga"
        assert analyse.scores_par_alea[0].score == 82.0
        assert len(analyse.risques_dominants) == 1
