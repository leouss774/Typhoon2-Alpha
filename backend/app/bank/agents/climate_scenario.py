"""Property value projections under climate stress."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.typhoon_bank import ClimateRiskResult, ClimateScenarioResult, PropertyValuationResult, ScenarioValue, TyphoonBankInput


class ClimateScenarioAgent:
    def run(
        self,
        payload: TyphoonBankInput,
        valuation: PropertyValuationResult,
        climate_risk: ClimateRiskResult,
    ) -> ClimateScenarioResult:
        current_year = datetime.now(timezone.utc).year
        projections = {}
        for horizon in (5, 10, 20, 30):
            future_discount = _future_discount(valuation.climate_discount, climate_risk.climate_score, horizon)
            value_without_climate = valuation.market_value * ((1 + payload.taux_croissance_annuel) ** horizon)
            future_value = value_without_climate * (1 - future_discount)
            key = f"{horizon}_years"
            projections[key] = ScenarioValue(
                horizon_years=horizon,
                year=current_year + horizon,
                growth_rate=payload.taux_croissance_annuel,
                future_discount=round(future_discount, 4),
                future_value=round(future_value, 2),
                future_value_without_climate=round(value_without_climate, 2),
            )
        return ClimateScenarioResult(projections=projections)


def _future_discount(current_discount: float, score: float, horizon: int) -> float:
    climate_drift = (score / 100) * 0.006 * horizon
    return min(0.45, current_discount + climate_drift)
