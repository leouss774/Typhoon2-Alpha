"""
Test hors-ligne de la route POST /chat (assistant IA conversationnel).

MISTRAL_API_KEY est absente en CI/sandbox : on mocke `chat_text` (le vrai
appel Mistral est hors de portée de ce test — voir
test_api_diagnostic_offline.py pour la même philosophie). On vérifie :

1. Le contrat : messages + contexte acceptés, réponse `{"reponse": ...}`.
2. Le contexte du bien est bien transmis à Mistral dans le system prompt.
3. Sans clé API -> 503 avec un message d'erreur clair.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

MESSAGE = [
    {"role": "user", "content": "Quels travaux sont recommandés pour ma toiture ?"},
]
CONTEXTE = {
    "adresse": "12 rue des Lilas, 33000 Bordeaux",
    "bien": {"type": "maison individuelle", "annee_construction": 1975},
    "score_global": 58,
    "zones": {
        "toiture": {
            "risque": 55,
            "niveau": "modere",
            "alea_principal": "Canicule / stress thermique",
            "justification": "Isolation actuelle insuffisante.",
            "recommandations": [
                {"mesure": "Isolation thermique renforcée", "cout_estime": "6000-11000€", "gain_resilience": 22}
            ],
        }
    },
}


def test_chat_appelle_mistral_avec_le_contexte():
    with TestClient(app) as client:
        # Patch au point d'usage (app.api.routes.chat.chat_text) : la route fait
        # `from app.recommandations.mistral_client import chat_text`, donc la
        # reference vit dans le module route, pas dans mistral_client (meme
        # convention que test_api_diagnostic_offline.py, qui patche
        # app.recommandations.service.chat_json).
        with patch(
            "app.api.routes.chat.chat_text",
            return_value="Je vous recommande l'isolation thermique renforcée de la toiture.",
        ) as mock_chat:
            resp = client.post("/chat", json={"messages": MESSAGE, "contexte": CONTEXTE})

    assert resp.status_code == 200, resp.text
    assert resp.json()["reponse"] == "Je vous recommande l'isolation thermique renforcée de la toiture."

    # Le system prompt doit embarquer le contexte du bien (adresse, zone, reco)
    assert mock_chat.call_count == 1
    system_prompt, messages = mock_chat.call_args.args
    assert "12 rue des Lilas, 33000 Bordeaux" in system_prompt
    assert "Toiture" in system_prompt  # label capitalisé via _label_zone
    assert "Isolation thermique renforcée" in system_prompt
    assert messages == [{"role": "user", "content": "Quels travaux sont recommandés pour ma toiture ?"}]


def test_chat_sans_cle_api_renvoie_503():
    from app.core.config import settings

    with TestClient(app) as client:
        with patch.object(settings, "mistral_api_key", None):
            resp = client.post("/chat", json={"messages": MESSAGE, "contexte": CONTEXTE})

    assert resp.status_code == 503
    assert "MISTRAL_API_KEY" in resp.json()["detail"]


def test_chat_erreur_mistral_renvoie_502():
    with TestClient(app) as client:
        with patch(
            "app.api.routes.chat.chat_text",
            side_effect=RuntimeError("timeout"),
        ):
            resp = client.post("/chat", json={"messages": MESSAGE, "contexte": CONTEXTE})

    assert resp.status_code == 502
    assert "indisponible" in resp.json()["detail"]


if __name__ == "__main__":
    test_chat_appelle_mistral_avec_le_contexte()
    test_chat_sans_cle_api_renvoie_503()
    test_chat_erreur_mistral_renvoie_502()
    print("\nTOUS LES TESTS test_chat PASSENT")
