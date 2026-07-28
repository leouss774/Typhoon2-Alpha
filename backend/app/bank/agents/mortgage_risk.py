"""Mortgage risk calculations."""

from __future__ import annotations

from app.schemas.typhoon_bank import ClimateRiskResult, MortgageRiskResult, PropertyValuationResult, TyphoonBankInput


class MortgageRiskAgent:
    def run(
        self,
        payload: TyphoonBankInput,
        valuation: PropertyValuationResult,
        climate_risk: ClimateRiskResult,
    ) -> MortgageRiskResult:
        loan_amount = payload.montant_credit
        ltv = loan_amount / valuation.market_value if valuation.market_value else 1.0
        cltv = loan_amount / valuation.adjusted_value if valuation.adjusted_value else 1.0
        potential_loss = max(0.0, loan_amount - valuation.adjusted_value)
        recommended_loan = valuation.adjusted_value * payload.max_ltv
        risk_level = _risk_level(cltv, climate_risk.climate_score, potential_loss)
        margin_bps = _margin_bps(risk_level, climate_risk.climate_score)

        return MortgageRiskResult(
            ltv=round(ltv, 4),
            cltv=round(cltv, 4),
            potential_loss=round(potential_loss, 2),
            recommended_loan=round(recommended_loan, 2),
            risk_level=risk_level,
            climate_margin_bps=margin_bps,
        )


def _risk_level(cltv: float, climate_score: float, potential_loss: float) -> str:
    if cltv >= 1.08 or climate_score >= 85 or potential_loss > 50000:
        return "CRITICAL"
    if cltv >= 0.95 or climate_score >= 70 or potential_loss > 15000:
        return "HIGH"
    if cltv >= 0.80 or climate_score >= 45:
        return "MEDIUM"
    return "LOW"


def _margin_bps(risk_level: str, climate_score: float) -> int:
    base = {"LOW": 10, "MEDIUM": 35, "HIGH": 75, "CRITICAL": 125}[risk_level]
    return int(round(base + climate_score * 0.35))
