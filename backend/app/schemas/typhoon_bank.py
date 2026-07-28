"""Pydantic contracts for the independent Typhoon Bank module."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PropertyType = Literal["maison", "appartement", "immeuble", "terrain", "autre"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DecisionCode = Literal["APPROVE", "APPROVE_WITH_CONDITIONS", "REVIEW_REQUIRED", "DECLINE_RECOMMENDED"]


class TyphoonBankInput(BaseModel):
    adresse: str = Field(min_length=5)
    montant_credit: float = Field(gt=0)
    duree: int = Field(gt=0, le=35, description="Loan duration in years.")
    surface: float = Field(gt=0, description="Property surface in square meters.")
    type_bien: PropertyType = "maison"

    prix_m2: float | None = Field(default=None, gt=0, description="Optional bank override for local price per m2.")
    taux_croissance_annuel: float = Field(default=0.012, ge=-0.05, le=0.08)
    max_ltv: float = Field(default=0.8, gt=0, le=1)
    taux_base: float = Field(default=0.045, ge=0, le=0.2)


class LoanData(BaseModel):
    amount: float
    duration_years: int
    max_ltv: float
    base_rate: float


class BankDataBundle(BaseModel):
    building_data: dict[str, Any] = Field(default_factory=dict)
    climate_data: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    loan_data: LoanData


class ClimateRiskResult(BaseModel):
    flood_risk: float = Field(ge=0, le=100)
    drought_risk: float = Field(ge=0, le=100)
    heat_risk: float = Field(ge=0, le=100)
    fire_risk: float = Field(ge=0, le=100)
    climate_score: float = Field(ge=0, le=100)
    main_risks: list[str] = Field(default_factory=list)


class PropertyValuationResult(BaseModel):
    surface: float
    price_per_m2: float
    price_source: str
    market_value: float
    climate_discount: float
    adjusted_value: float


class ScenarioValue(BaseModel):
    horizon_years: int
    year: int
    growth_rate: float
    future_discount: float
    future_value: float
    future_value_without_climate: float


class ClimateScenarioResult(BaseModel):
    projections: dict[str, ScenarioValue]


class MortgageRiskResult(BaseModel):
    ltv: float
    cltv: float
    potential_loss: float
    recommended_loan: float
    risk_level: RiskLevel
    climate_margin_bps: int


class PreventionRecommendation(BaseModel):
    name: str
    risk: str
    cost: float
    risk_reduction: float
    rationale: str


class PreventionResult(BaseModel):
    recommendations: list[PreventionRecommendation] = Field(default_factory=list)


class BankDecisionResult(BaseModel):
    decision: DecisionCode
    risk_level: RiskLevel
    recommended_rate: str
    conditions: list[str] = Field(default_factory=list)
    explanation: str
    llm_provider: str


class TyphoonBankOutput(BaseModel):
    module: Literal["Typhoon Bank"] = "Typhoon Bank"
    enabled: bool = True
    input: TyphoonBankInput
    data: BankDataBundle
    climate_risk: ClimateRiskResult
    valuation: PropertyValuationResult
    scenarios: ClimateScenarioResult
    mortgage_risk: MortgageRiskResult
    prevention: PreventionResult
    bank_decision: BankDecisionResult


EXAMPLE_INPUT = {
    "adresse": "10 Promenade des Anglais, 06000 Nice",
    "montant_credit": 250000,
    "duree": 20,
    "surface": 150,
    "type_bien": "maison",
    "prix_m2": 5200,
}
