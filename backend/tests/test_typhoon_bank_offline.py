"""Offline tests for the Typhoon Bank module.

Run from backend/:
    PYTHONPATH=. python tests/test_typhoon_bank_offline.py
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.bank.service import TyphoonBankService
from app.schemas.typhoon_bank import TyphoonBankInput


FAKE_BUILDING_DATA = {
    "adresse": {
        "label": "10 Promenade des Anglais 06000 Nice",
        "citycode": "06088",
        "postcode": "06000",
        "city": "Nice",
        "lat": 43.6959,
        "lon": 7.2661,
    },
    "departement": "06",
    "bdnb": {
        "batiment": {
            "alea_argile": "Moyen",
            "surface_emprise_sol": 150,
            "nb_niveau": 2,
        }
    },
    "georisques": {
        "risques_commune": {"data": [{"libelle_risque_long": "Inondation"}, {"libelle_risque_long": "Feu de foret"}]},
        "zones_inondables": {"data": [{"nom": "AZI"}]},
        "catnat": {"data": [{"libelle": "Inondations et coulees de boue"}, {"libelle": "Secheresse"}]},
        "erreurs": [],
    },
    "climat_open_meteo": {
        "reference_2015_2024": {"jours_chaleur_extreme_par_an": 4},
        "projection_2041_2050": {"jours_chaleur_extreme_par_an": 13},
    },
    "climat_copernicus": {"rcp8_5_yearly__magnitude_of_meteorological_droughts": 5},
    "dvf_local": [],
    "erreurs": [],
}


async def fake_collect(address: str) -> dict:
    assert "Nice" in address
    return FAKE_BUILDING_DATA


async def test_service_pipeline():
    payload = TyphoonBankInput(
        adresse="10 Promenade des Anglais, 06000 Nice",
        montant_credit=250000,
        duree=20,
        surface=150,
        type_bien="maison",
        prix_m2=5200,
    )
    service = TyphoonBankService()
    with patch("app.bank.agents.data_collector.collect", side_effect=fake_collect):
        result = await service.analyze(payload)

    assert result.module == "Typhoon Bank"
    assert result.climate_risk.climate_score > 50
    assert result.valuation.market_value == 780000
    assert result.valuation.adjusted_value < result.valuation.market_value
    assert "5_years" in result.scenarios.projections
    assert result.mortgage_risk.recommended_loan > payload.montant_credit
    assert result.bank_decision.decision in {"APPROVE", "APPROVE_WITH_CONDITIONS", "REVIEW_REQUIRED"}
    print("test_service_pipeline OK ->", result.bank_decision.model_dump())


def test_module_can_be_disabled_flag():
    from app.bank.config import typhoon_bank_enabled

    with patch.dict("os.environ", {"TYPHOON_BANK_ENABLED": "false"}):
        assert typhoon_bank_enabled() is False
    with patch.dict("os.environ", {"TYPHOON_BANK_ENABLED": "true"}):
        assert typhoon_bank_enabled() is True
    print("test_module_can_be_disabled_flag OK")


def test_climate_risk_handles_french_accents():
    from app.bank.agents.climate_risk import ClimateRiskAgent
    from app.schemas.typhoon_bank import BankDataBundle, LoanData

    data = BankDataBundle(
        building_data={"bdnb": {"batiment": {"alea_argile": "Modéré"}}},
        climate_data={
            "georisques": {
                "risques_commune": {"data": [{"libelle_risque_long": "Feu de forêt"}]},
                "catnat": {"data": [{"libelle_risque_jo": "Sécheresse"}]},
            }
        },
        market_data={},
        loan_data=LoanData(amount=100000, duration_years=20, max_ltv=0.8, base_rate=0.045),
    )

    result = ClimateRiskAgent().run(data)
    assert result.drought_risk == 60
    assert result.fire_risk == 85
    print("test_climate_risk_handles_french_accents OK ->", result.model_dump())


async def _run_all():
    await test_service_pipeline()
    test_module_can_be_disabled_flag()
    test_climate_risk_handles_french_accents()
    print("\nTOUS LES TESTS Typhoon Bank HORS-LIGNE PASSENT")


if __name__ == "__main__":
    asyncio.run(_run_all())
