from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.artisans.classification import (
    CONFIDENCE_MIN,
    classer_avec_mistral,
    decision_regle,
    valider_reponse_mistral,
)
from app.artisans.service import matcher


def test_decision_regle_est_acceptee_sans_llm():
    decision = decision_regle("travaux_toiture")
    assert decision.categorie == "travaux_toiture"
    assert decision.source == "regles_metier"
    assert decision.confiance == 1.0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"categorie": "metier_invente", "confiance": 0.99, "justification": "Texte assez long."},
        {"categorie": "travaux_toiture", "confiance": "forte", "justification": "Texte assez long."},
        {"categorie": "travaux_toiture", "confiance": 1.5, "justification": "Texte assez long."},
        {"categorie": "travaux_toiture", "confiance": 0.99, "justification": "court"},
    ],
)
def test_reponses_invalides_sont_non_classees(payload):
    decision = valider_reponse_mistral(payload)
    assert decision.categorie is None
    assert decision.statut == "non_classee"


def test_faible_confiance_est_rejetee():
    decision = valider_reponse_mistral({
        "categorie": "ruissellement_drainage",
        "confiance": CONFIDENCE_MIN - 0.01,
        "justification": "La formulation reste trop ambiguë pour choisir ce métier.",
    })
    assert decision.categorie is None
    assert decision.source == "mistral"


def test_reponse_valide_est_acceptee():
    decision = valider_reponse_mistral({
        "categorie": "ruissellement_drainage",
        "confiance": 0.93,
        "justification": "La mesure concerne explicitement la gestion des eaux pluviales.",
    })
    assert decision.categorie == "ruissellement_drainage"
    assert decision.confiance == 0.93


async def test_indisponibilite_mistral_ne_fait_pas_echouer(monkeypatch):
    monkeypatch.setattr("app.artisans.classification.settings.mistral_api_key", "test")
    with patch(
        "app.artisans.classification.asyncio.to_thread",
        new=AsyncMock(side_effect=RuntimeError("offline")),
    ):
        decision = await classer_avec_mistral("jardin", [], "Mesure atypique")
    assert decision.categorie is None
    assert decision.statut == "non_classee"


async def test_matcher_utilise_mistral_uniquement_en_repli():
    decision = valider_reponse_mistral({
        "categorie": "travaux_facade",
        "confiance": 0.95,
        "justification": "La mesure nécessite une intervention spécialisée sur l'enveloppe.",
    })
    response = MagicMock()
    response.json.return_value = {"results": []}
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=response)

    with patch(
        "app.artisans.service.classer_avec_mistral",
        new=AsyncMock(return_value=decision),
    ) as llm:
        result = await matcher(
            "33000 Bordeaux",
            [{
                "zone": "element_special",
                "risques": [],
                "recommandations": [{"mesure": "Traitement technique atypique"}],
            }],
            client=fake_client,
        )

    llm.assert_awaited_once()
    assert result["journal_classification"][0]["source"] == "mistral"
    assert result["recommandations_traitees"][0]["cle"] == "travaux_facade"
