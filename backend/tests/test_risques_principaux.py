"""
Tests unitaires pour le scoring par aléa (compute_alea_risks) et la synthèse
des « risques principaux » (app.agents.risques_principaux).

Pas d'appels réseau : données synthétiques calquées sur les formats réels
(collector_agent), et appel Mistral mocké quand une clé est simulée.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.agents.risques_principaux import (
    TOP_N,
    _ZONES_VALIDES,
    generer_risques_principaux,
)
from app.core.config import settings
from app.scoring.risk_model import compute_alea_risks


# ---------------------------------------------------------------------------
#   Données mockées (mêmes formes que collector_agent / risk_model)
# ---------------------------------------------------------------------------

def _building_data_factice(
    annee_construction: int | None = 1945,
    alea_argile: str | None = "fort",
    nb_catnat_inondation: int = 9,
    nb_catnat_secheresse: int = 3,
    jours_chaleur: float | None = 4.5,
    zone_sismique: int | None = 2,
    classe_radon: int | None = None,
    feu_foret: bool = False,
) -> dict:
    catnat = [{"libelle_risque_jo": "Inondations et/ou Coulées de Boue"} for _ in range(nb_catnat_inondation)]
    catnat += [{"libelle_risque_jo": "Sécheresse"} for _ in range(nb_catnat_secheresse)]

    risques_detail = [{"libelle_risque_long": "Inondation", "zone_sismicite": zone_sismique}]
    if feu_foret:
        risques_detail.append({"libelle_risque_long": "Feu de forêt"})

    batiment = {}
    if annee_construction is not None:
        batiment["annee_construction"] = annee_construction
    if alea_argile:
        batiment["alea_argile"] = alea_argile

    return {
        "adresse": {"label": "10 Rue Test, 75000 Paris", "lat": 48.8566, "lon": 2.3522},
        "altitude_m": 25.0,
        "bdnb": {"batiment": batiment, "cle_interop_adr": "75056_001_00010"},
        "georisques": {
            "risques_commune": {"data": [{"risques_detail": risques_detail}]},
            "catnat": {"data": catnat},
            "zonage_sismique": {"data": []},
            "radon": {"data": [{"classe_potentiel": classe_radon}] if classe_radon else []},
            "cavites": {"data": []},
            "mouvements_de_terrain": {"data": []},
        },
        "climat_open_meteo": {
            "reference_2015_2024": {
                "temperature_max_moyenne_c": 18.5,
                "jours_chaleur_extreme_par_an": jours_chaleur,
                "precipitation_annuelle_moyenne_mm": 800.0,
            },
            "projection_2041_2050": {
                "temperature_max_moyenne_c": 22.1,
                "jours_chaleur_extreme_par_an": jours_chaleur * 1.5 if jours_chaleur else None,
                "precipitation_annuelle_moyenne_mm": 850.0,
            },
        },
    }


def _risk_scores_factices(building_data: dict) -> dict:
    """risk_scores minimal compatible avec _build_risk_context."""
    from app.scoring.risk_model import compute_risk_scores

    return compute_risk_scores(building_data)


# ---------------------------------------------------------------------------
#   Tests compute_alea_risks (déterministe)
# ---------------------------------------------------------------------------

def test_alea_risks_tries_decroissant_et_bornes():
    """Les risques par aléa sont triés par score décroissant, bornés 0-100,
    et portent les clés D03 du frontend."""
    data = _building_data_factice()
    risques = compute_alea_risks(data)
    assert risques, "aucun risque calculé pour un bien à RGA fort + 9 CATNAT inondation"
    scores = [r["score"] for r in risques]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= r["score"] <= 100 for r in risques)
    for r in risques:
        assert r["niveau"] in {"tres_faible", "faible", "modere", "eleve", "critique"}
        assert r["code"] and r["libelle"] and r["justification"]


def test_alea_risks_top3_reflete_les_donnees():
    """Avec aléa argile fort + vieux bâtiment, 9 CATNAT inondation et 3 CATNAT
    sécheresse, le top 3 est {rga, inondation, secheresse}."""
    data = _building_data_factice()
    risques = compute_alea_risks(data)
    top3 = {r["code"] for r in risques[:TOP_N]}
    assert "rga" in top3
    assert "inondation" in top3
    assert "secheresse" in top3
    # La sécheresse (3 arrêtés) reste derrière le RGA (aléa fort au bâtiment)
    codes = [r["code"] for r in risques]
    assert codes.index("rga") < codes.index("secheresse")


def test_alea_risks_filtre_les_aleas_sans_signal():
    """Un aléa absent (radon sans classe, feu de forêt non recensé, zone
    sismique faible) ne doit JAMAIS apparaître dans les risques."""
    data = _building_data_factice(zone_sismique=1)  # F sismique = 15 < 20
    risques = compute_alea_risks(data)
    codes = {r["code"] for r in risques}
    assert "radon" not in codes
    assert "feu_foret" not in codes
    assert "sismicite" not in codes
    assert "mouvement_terrain" not in codes  # aucune cavité / mvt


def test_secheresse_dedoublonnee_sans_alea_argile_bdnb():
    """Sans aléa argile BDNB, `rga` retombe déjà sur le repli CATNAT
    sécheresse : le candidat « secheresse » doit être dédoublonné (sinon deux
    lignes identiques dans le top 3)."""
    data = _building_data_factice(alea_argile=None, nb_catnat_secheresse=5)
    risques = compute_alea_risks(data)
    codes = [r["code"] for r in risques]
    assert "secheresse" not in codes
    assert "rga" in codes  # le repli CATNAT sécheresse alimente le RGA


def test_alea_risks_sans_georisques():
    """Données minimales (aucun CATNAT, aucun aléa) : liste courte, pas de
    crash, scores faibles."""
    data = _building_data_factice(
        annee_construction=None,
        alea_argile=None,
        nb_catnat_inondation=0,
        nb_catnat_secheresse=0,
        zone_sismique=None,
    )
    risques = compute_alea_risks(data)
    assert isinstance(risques, list)
    # Sans signal notable, soit rien, soit au plus la canicule (> 3 j/an)
    assert all(r["score"] < 60 for r in risques)


# ---------------------------------------------------------------------------
#   Tests generer_risques_principaux (fail-soft LLM)
# ---------------------------------------------------------------------------

def test_generer_sans_cle_api_repli_deterministe():
    """Sans MISTRAL_API_KEY : classement déterministe, aucun appel réseau,
    jamais d'exception. `explication` = première justification du moteur et
    `zone_la_plus_exposee` = repli par aléa."""
    real_key = settings.mistral_api_key
    settings.mistral_api_key = None
    try:
        data = _building_data_factice()
        result = generer_risques_principaux(data, _risk_scores_factices(data))
    finally:
        settings.mistral_api_key = real_key

    assert result["source"] == "moteur_deterministe"
    assert 0 < len(result["risques"]) <= TOP_N
    for r in result["risques"]:
        assert r["explication"], "explication de repli absente"
        assert r["zone_la_plus_exposee"] in _ZONES_VALIDES
        assert r["facteurs_aggravants"] == []


def test_generer_fusion_reponse_llm_avec_mock():
    """Réponse Mistral mockée : explication/facteurs/zone repris, score et
    niveau du moteur préservés (le LLM ne peut pas les modifier)."""
    real_key = settings.mistral_api_key
    settings.mistral_api_key = "test-key"
    try:
        data = _building_data_factice()
        risk_scores = _risk_scores_factices(data)
        top_moteur = compute_alea_risks(data)[:TOP_N]
        codes = [r["code"] for r in top_moteur]

        def fake_chat_json(system_prompt, user_prompt):
            assert "RISQUES PRINCIPAUX" in user_prompt
            return {
                "risques": [
                    {
                        "code": code,
                        "libelle": "libellé LLM (doit être ignoré)",
                        "score": 1,  # doit être ignoré
                        "niveau": "faible",  # doit être ignoré
                        "explication": f"Explication croisée pour {code}.",
                        "facteurs_aggravants": [f"Facteur A → conséquence", f"Facteur B"],
                        "zone_la_plus_exposee": "sous_sol" if code == "inondation" else "fondations",
                    }
                    for code in codes
                ]
            }

        with patch("app.agents.risques_principaux.chat_json", side_effect=fake_chat_json):
            result = generer_risques_principaux(data, risk_scores)
    finally:
        settings.mistral_api_key = real_key

    assert result["source"] == "moteur_deterministe_et_llm"
    assert len(result["risques"]) == len(codes)
    for r, r_moteur in zip(result["risques"], top_moteur):
        assert r["code"] == r_moteur["code"]
        assert r["score"] == r_moteur["score"], "le LLM a modifié le score !"
        assert r["niveau"] == r_moteur["niveau"], "le LLM a modifié le niveau !"
        assert r["explication"] == f"Explication croisée pour {r['code']}."
        assert r["facteurs_aggravants"] == ["Facteur A → conséquence", "Facteur B"]
        assert r["zone_la_plus_exposee"] in _ZONES_VALIDES


def test_generer_echec_mistral_repli_deterministe():
    """Un échec Mistral (timeout, rate limit…) ne fait JAMAIS échouer le
    diagnostic : repli déterministe avec source = moteur_deterministe."""
    real_key = settings.mistral_api_key
    settings.mistral_api_key = "test-key"
    try:
        data = _building_data_factice()
        risk_scores = _risk_scores_factices(data)
        with patch(
            "app.agents.risques_principaux.chat_json",
            side_effect=RuntimeError("429 rate limit exceeded"),
        ):
            result = generer_risques_principaux(data, risk_scores)
    finally:
        settings.mistral_api_key = real_key

    assert result["source"] == "moteur_deterministe"
    assert result["risques"], "le repli devrait produire au moins un risque"
    for r in result["risques"]:
        assert r["explication"]
        assert r["zone_la_plus_exposee"] in _ZONES_VALIDES


def test_generer_reponse_llm_invalide_ignoree():
    """Une réponse Mistral non structurée (pas de liste « risques », zones
    inconnues…) est ignorée sans crash — repli déterministe."""
    real_key = settings.mistral_api_key
    settings.mistral_api_key = "test-key"
    try:
        data = _building_data_factice()
        risk_scores = _risk_scores_factices(data)
        with patch(
            "app.agents.risques_principaux.chat_json",
            return_value={"risques": [{"code": "rga", "explication": "ok", "zone_la_plus_exposee": "inconnue"}]},
        ):
            result = generer_risques_principaux(data, risk_scores)
    finally:
        settings.mistral_api_key = real_key

    assert result["source"] == "moteur_deterministe_et_llm"
    rga = next(r for r in result["risques"] if r["code"] == "rga")
    assert rga["explication"] == "ok"
    assert rga["zone_la_plus_exposee"] in _ZONES_VALIDES  # zone invalide → repli


async def _run_all() -> None:
    test_alea_risks_tries_decroissant_et_bornes()
    test_alea_risks_top3_reflete_les_donnees()
    test_alea_risks_filtre_les_aleas_sans_signal()
    test_alea_risks_sans_georisques()
    test_generer_sans_cle_api_repli_deterministe()
    test_generer_fusion_reponse_llm_avec_mock()
    test_generer_echec_mistral_repli_deterministe()
    test_generer_reponse_llm_invalide_ignoree()
    print("\n=== TOUS LES TESTS RISQUES PRINCIPAUX PASSENT ===")


if __name__ == "__main__":
    asyncio.run(_run_all())
