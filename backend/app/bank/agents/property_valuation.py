"""Property valuation adjusted for climate risk."""

from __future__ import annotations

from app.schemas.typhoon_bank import BankDataBundle, ClimateRiskResult, PropertyValuationResult, TyphoonBankInput


class PropertyValuationAgent:
    def run(
        self,
        payload: TyphoonBankInput,
        data: BankDataBundle,
        climate_risk: ClimateRiskResult,
    ) -> PropertyValuationResult:
        price_per_m2 = float(data.market_data.get("price_per_m2") or payload.prix_m2 or 3200)
        market_value = payload.surface * price_per_m2
        climate_discount = _discount_from_score(climate_risk.climate_score)
        adjusted_value = market_value * (1 - climate_discount)
        return PropertyValuationResult(
            surface=payload.surface,
            price_per_m2=round(price_per_m2, 2),
            price_source=str(data.market_data.get("price_source") or "fallback"),
            market_value=round(market_value, 2),
            climate_discount=round(climate_discount, 4),
            adjusted_value=round(adjusted_value, 2),
        )


def _discount_from_score(score: float) -> float:
    if score < 25:
        return 0.02
    if score < 50:
        return 0.05 + ((score - 25) / 25) * 0.04
    if score < 75:
        return 0.09 + ((score - 50) / 25) * 0.08
    return min(0.30, 0.17 + ((score - 75) / 25) * 0.13)
