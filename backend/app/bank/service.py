"""Orchestrates the independent Typhoon Bank agent chain."""

from __future__ import annotations

from app.bank.agents.climate_risk import ClimateRiskAgent
from app.bank.agents.climate_scenario import ClimateScenarioAgent
from app.bank.agents.data_collector import BankDataCollectorAgent
from app.bank.agents.decision import BankDecisionAgent
from app.bank.agents.mortgage_risk import MortgageRiskAgent
from app.bank.agents.prevention import PreventionAgent
from app.bank.agents.property_valuation import PropertyValuationAgent
from app.schemas.typhoon_bank import TyphoonBankInput, TyphoonBankOutput


class TyphoonBankService:
    def __init__(self) -> None:
        self.data_collector = BankDataCollectorAgent()
        self.climate_risk = ClimateRiskAgent()
        self.valuation = PropertyValuationAgent()
        self.scenario = ClimateScenarioAgent()
        self.mortgage = MortgageRiskAgent()
        self.prevention = PreventionAgent()
        self.decision = BankDecisionAgent()

    async def analyze(self, payload: TyphoonBankInput) -> TyphoonBankOutput:
        data = await self.data_collector.run(payload)
        climate_risk = self.climate_risk.run(data)
        valuation = self.valuation.run(payload, data, climate_risk)
        scenarios = self.scenario.run(payload, valuation, climate_risk)
        mortgage_risk = self.mortgage.run(payload, valuation, climate_risk)
        prevention = self.prevention.run(climate_risk)
        bank_decision = await self.decision.run(payload, climate_risk, valuation, mortgage_risk, prevention)
        return TyphoonBankOutput(
            input=payload,
            data=data,
            climate_risk=climate_risk,
            valuation=valuation,
            scenarios=scenarios,
            mortgage_risk=mortgage_risk,
            prevention=prevention,
            bank_decision=bank_decision,
        )
