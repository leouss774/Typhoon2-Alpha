"""Tests unitaires pour le legacy_chat enrichi.

Teste la route POST /api/chat/{session_id} de legacy.py :
- Réponses contextualisées selon le type de question
- Gestion des sessions absentes
- Format de réponse attendu
- Utilisation des données réelles d'analyse
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ajouter backend/ au sys.path pour que l'import interne dans main.py
# (from app.api.routes import ...) puisse résoudre le package 'app'
_backend_path = os.path.join(os.path.dirname(__file__), "..", "..")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from backend.app.main import app

client = TestClient(app)


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_analysis_completed() -> dict:
    """Analyse complète simulée, stockée dans analyses_store."""
    return {
        "session_id": "test-session-legacy-001",
        "adresse": "15 Rue des Lilas, 33140 Villenave-d'Ornon",
        "status": "completed",
        "date_analyse": "2026-07-29T12:00:00+00:00",
        "resume": {
            "score_global": 68,
            "niveau_risque": "eleve",
            "nb_recommandations": 4,
        },
        "analyse_risques": {
            "scores_par_alea": {
                "rga": {"score": 82, "niveau": "critique", "label": "Retrait-gonflement des argiles"},
                "inondation": {"score": 45, "niveau": "modere", "label": "Inondation"},
                "tempete": {"score": 30, "niveau": "modere", "label": "Tempête"},
                "incendie": {"score": 10, "niveau": "faible", "label": "Incendie"},
            }
        },
        "recommandations": {
            "zones": {
                "fondations": {
                    "risque": 82,
                    "niveau": "critique",
                    "alea_principal": "RGA",
                    "recommandations": [
                        {"travaux": "Reprise des fondations par micropieux", "cout_estime": "15000 €/an", "gain_resilience": 70, "priorite": 1, "aide_financiere": "Anah"},
                        {"travaux": "Drainage périphérique", "cout_estime": "5000 €/an", "gain_resilience": 50, "priorite": 2, "aide_financiere": ""},
                    ],
                },
                "toiture": {
                    "risque": 55,
                    "niveau": "eleve",
                    "alea_principal": "Tempête",
                    "recommandations": [
                        {"travaux": "Renforcement de la charpente", "cout_estime": "8000 €/an", "gain_resilience": 60, "priorite": 3, "aide_financiere": "MaPrimeRénov'"},
                    ],
                },
            },
            "projection_2050": {
                "score_global": 82,
                "scenario_climatique": "RCP 8.5",
                "zones": {"fondations": {"risque_projete": 88}},
            },
        },
        "decision_bancaire": {
            "taux_propose": 4.15,
            "valeur_marche": 350000,
            "valeur_ajustee": 315000,
            "score_risque_bancaire": 65,
            "niveau_risque_bancaire": "Élevé",
            "majoration_taux": 0.45,
            "decote_pct": 10,
        },
        "formulaire_client": {
            "adresse": "15 Rue des Lilas, 33140 Villenave-d'Ornon",
            "type_bien": "Maison",
            "surface": 120,
        },
    }


# ── Tests : format des réponses ─────────────────────────────────────────

class TestLegacyChatHeaders:
    """Teste le format et la validité des réponses."""

    def test_chat_returns_200(self):
        response = client.post(
            "/api/chat/test-session-999",
            json={"question": "Quel est le score de risque ?"},
        )
        assert response.status_code == 200

    def test_chat_returns_json_with_reponse(self):
        response = client.post(
            "/api/chat/test-session-999",
            json={"question": "Bonjour"},
        )
        data = response.json()
        assert "reponse" in data
        assert "session_id" in data
        assert isinstance(data["reponse"], str)
        assert len(data["reponse"]) > 10

    def test_chat_without_question_returns_422(self):
        response = client.post(
            "/api/chat/test-session-999",
            json={"question": ""},
        )
        assert response.status_code == 422


# ── Tests : sans analyse stockée (get_analysis retourne None) ───────────

class TestLegacyChatNoAnalysis:
    """Teste les réponses quand aucune analyse n'est stockée."""

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_chat_without_analysis_defaults_to_generic(self, mock_diag, mock_get):
        mock_diag.clear()
        response = client.post(
            "/api/chat/unknown-session-123",
            json={"question": "Quels sont les risques ?"},
        )
        data = response.json()
        assert data["session_id"] == "unknown-session-123"
        assert "score" in data["reponse"] or "risque" in data["reponse"] or "bienvenue" in data["reponse"].lower()

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_chat_with_empty_historique(self, mock_diag, mock_get):
        mock_diag.clear()
        response = client.post(
            "/api/chat/session-vide",
            json={"question": "Bonjour", "historique": []},
        )
        assert response.status_code == 200
        assert "reponse" in response.json()


# ── Tests : questions par catégorie (sans analyse) ──────────────────────

class TestLegacyChatCategories:
    """Teste que les catégories de questions retournent des réponses cohérentes."""

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_question_score(self, mock_diag, mock_get):
        mock_diag.clear()
        response = client.post(
            "/api/chat/test-session-score",
            json={"question": "Quel est le niveau de risque ?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert any(w in data["reponse"] for w in ["score", "risque"])

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_question_taux(self, mock_diag, mock_get):
        mock_diag.clear()
        response = client.post(
            "/api/chat/test-session-taux",
            json={"question": "Quel est le taux proposé ?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert any(w in data["reponse"].lower() for w in ["taux", "financier", "analyse", "banque"])

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_question_2050(self, mock_diag, mock_get):
        mock_diag.clear()
        # Utiliser une question qui ne contient PAS "risque" ou "score"
        # pour eviter de declencher la branche score/risque avant la 2050
        response = client.post(
            "/api/chat/test-session-2050",
            json={"question": "Voyons la projection climatique 2050"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "2050" in data["reponse"] or "projection" in data["reponse"].lower() or "futur" in data["reponse"].lower()

    @patch("backend.app.api.routes.legacy.get_analysis", return_value=None)
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_question_zones(self, mock_diag, mock_get):
        mock_diag.clear()
        response = client.post(
            "/api/chat/test-session-zones",
            json={"question": "Quel est l'état des fondations ?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "zone" in data["reponse"].lower() or "données" in data["reponse"].lower() or "disponible" in data["reponse"].lower()


# ── Tests : avec analyse stockée (get_analysis retourne des données) ────

class TestLegacyChatWithAnalysis:
    """Teste les réponses avec une analyse stockée complète."""

    def test_score_reponse_with_analysis(self, sample_analysis_completed):
        """Injecte les donnees dans le vrai store puis interroge le chat."""
        from backend.app.api.routes.legacy import analyses_store
        sid = sample_analysis_completed["session_id"]
        analyses_store[sid] = sample_analysis_completed
        response = client.post(
            f"/api/chat/{sid}",
            json={"question": "Quel est mon score de risque ?"},
        )
        data = response.json()
        assert any(str(v) in data["reponse"] for v in [68, "68/100", "15 Rue des Lilas"])

    def test_taux_reponse_with_analysis(self, sample_analysis_completed):
        """Injecte les donnees dans le vrai store puis interroge le chat."""
        from backend.app.api.routes.legacy import analyses_store
        sid = sample_analysis_completed["session_id"]
        analyses_store[sid] = sample_analysis_completed
        response = client.post(
            f"/api/chat/{sid}",
            json={"question": "Quel taux de credit puis-je obtenir ?"},
        )
        data = response.json()
        reponse = data["reponse"]
        assert any(w in reponse.lower() for w in ["taux", "credit", "financier", "valeur", "banque"])

    @patch("backend.app.api.routes.legacy.get_analysis")
    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_travaux_reponse_with_analysis(self, mock_diag, mock_get, sample_analysis_completed):
        mock_diag.clear()
        mock_get.return_value = sample_analysis_completed
        sid = sample_analysis_completed["session_id"]
        response = client.post(
            f"/api/chat/{sid}",
            json={"question": "Combien coutent les travaux ?"},
        )
        data = response.json()
        reponse = data["reponse"]
        assert any(w in reponse.lower() for w in ["cout", "travaux", "euro", "recommandation", "disponible"])

    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_projection_reponse_with_analysis(self, mock_diag, sample_analysis_completed):
        mock_diag.clear()
        with patch("backend.app.api.routes.legacy.get_analysis", return_value=sample_analysis_completed):
            sid = sample_analysis_completed["session_id"]
            response = client.post(
                f"/api/chat/{sid}",
                json={"question": "Projection 2050 ?"},
            )
            data = response.json()
        reponse = data["reponse"]
        assert "82" in reponse or "2050" in reponse or "projection" in reponse.lower() or "futur" in reponse.lower()

    @patch("backend.app.api.routes.legacy.diagnostic_store", new_callable=dict)
    def test_priorite_reponse_with_analysis(self, mock_diag, sample_analysis_completed):
        mock_diag.clear()
        with patch("backend.app.api.routes.legacy.get_analysis", return_value=sample_analysis_completed):
            sid = sample_analysis_completed["session_id"]
            response = client.post(
                f"/api/chat/{sid}",
                json={"question": "Quelles sont les priorités ?"},
            )
            data = response.json()
        reponse = data["reponse"]
        assert "fondations" in reponse.lower() or "toiture" in reponse.lower() or "priorit" in reponse.lower()


# ── Tests : cas d'erreur ─────────────────────────────────────────────

class TestLegacyChatErrors:
    """Teste les cas d'erreur du chat."""

    def test_chat_with_long_question(self):
        response = client.post(
            "/api/chat/test-session-long",
            json={"question": "Question " * 100},
        )
        assert response.status_code == 200
        assert "reponse" in response.json()

    def test_chat_with_special_chars(self):
        response = client.post(
            "/api/chat/test-session-special",
            json={"question": "Coût des travaux ? {test} [ok] (suite) €€€"},
        )
        assert response.status_code == 200

    def test_chat_with_historique_malformed(self):
        response = client.post(
            "/api/chat/test-session-hist",
            json={"question": "Bonjour", "historique": [{"role": "user"}]},
        )
        assert response.status_code == 200


# ── Tests du store SQLite ──────────────────────────────────────────────

class TestAnalysesStore:
    """Teste le store persistant SQLite."""

    def test_store_save_and_load(self):
        from services.analyses_store import store
        store.save("test-sqlite-001", {"score": 50, "data": "test"})
        loaded = store.load("test-sqlite-001")
        assert loaded is not None
        assert loaded["score"] == 50
        assert loaded["data"] == "test"
        store.delete("test-sqlite-001")

    def test_store_load_nonexistent(self):
        from services.analyses_store import store
        loaded = store.load("nonexistent-session-xyz")
        assert loaded is None

    def test_store_overwrite(self):
        from services.analyses_store import store
        store.save("test-sqlite-002", {"version": 1})
        store.save("test-sqlite-002", {"version": 2})
        loaded = store.load("test-sqlite-002")
        assert loaded["version"] == 2
        store.delete("test-sqlite-002")

    def test_store_delete(self):
        from services.analyses_store import store
        store.save("test-sqlite-003", {"data": "to-delete"})
        assert store.delete("test-sqlite-003") is True
        assert store.load("test-sqlite-003") is None

    def test_store_delete_nonexistent(self):
        from services.analyses_store import store
        assert store.delete("nonexistent-delete") is False

    def test_store_list_sessions(self):
        from services.analyses_store import store
        store.save("test-sqlite-list-1", {"a": 1})
        store.save("test-sqlite-list-2", {"b": 2})
        sessions = store.list_sessions()
        ids = [s["session_id"] for s in sessions]
        assert "test-sqlite-list-1" in ids
        assert "test-sqlite-list-2" in ids
        store.delete("test-sqlite-list-1")
        store.delete("test-sqlite-list-2")

    def test_store_count(self):
        from services.analyses_store import store
        before = store.count()
        store.save("test-sqlite-count", {"x": 1})
        assert store.count() == before + 1
        store.delete("test-sqlite-count")

    def test_get_set_analysis_compat(self):
        from services.analyses_store import get_analysis, set_analysis
        set_analysis("test-compat-001", {"compat": True})
        loaded = get_analysis("test-compat-001")
        assert loaded is not None
        assert loaded["compat"] is True
        from services.analyses_store import analyses_store
        assert "test-compat-001" in analyses_store
        from services.analyses_store import store
        store.delete("test-compat-001")
