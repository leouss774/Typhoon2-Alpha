"""Bank recommendation agent with optional Mistral generation."""

from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.schemas.typhoon_bank import (
    BankDecisionResult,
    ClimateRiskResult,
    MortgageRiskResult,
    PreventionResult,
    PropertyValuationResult,
    TyphoonBankInput,
)


class BankDecisionAgent:
    async def run(
        self,
        payload: TyphoonBankInput,
        climate_risk: ClimateRiskResult,
        valuation: PropertyValuationResult,
        mortgage_risk: MortgageRiskResult,
        prevention: PreventionResult,
    ) -> BankDecisionResult:
        decision = _decision_code(mortgage_risk.risk_level)
        conditions = _conditions(mortgage_risk, prevention)
        recommended_rate = payload.taux_base + (mortgage_risk.climate_margin_bps / 10000)

        fallback = BankDecisionResult(
            decision=decision,
            risk_level=mortgage_risk.risk_level,
            recommended_rate=f"{recommended_rate * 100:.2f}%",
            conditions=conditions,
            explanation=_fallback_explanation(climate_risk, valuation, mortgage_risk),
            llm_provider="deterministic_fallback",
        )

        api_key = settings.mistral_api_key
        if not api_key:
            return fallback

        try:
            explanation = await _ask_mistral(
                api_key=api_key,
                payload=payload,
                climate_risk=climate_risk,
                valuation=valuation,
                mortgage_risk=mortgage_risk,
                prevention=prevention,
                decision=decision,
                conditions=conditions,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return fallback

        return fallback.model_copy(update={"explanation": explanation, "llm_provider": "mistral"})


def _decision_code(risk_level: str) -> str:
    return {
        "LOW": "APPROVE",
        "MEDIUM": "APPROVE_WITH_CONDITIONS",
        "HIGH": "REVIEW_REQUIRED",
        "CRITICAL": "DECLINE_RECOMMENDED",
    }[risk_level]


def _conditions(mortgage_risk: MortgageRiskResult, prevention: PreventionResult) -> list[str]:
    conditions = []
    if mortgage_risk.recommended_loan > 0:
        conditions.append(f"Limiter le montant finance a {mortgage_risk.recommended_loan:,.0f} EUR maximum.")
    if mortgage_risk.cltv > 0.8:
        conditions.append("Reviser le LTV cible apres valeur ajustee climat.")
    for reco in prevention.recommendations[:3]:
        conditions.append(f"Condition travaux: {reco.name.replace('_', ' ')}.")
    return conditions


def _fallback_explanation(
    climate_risk: ClimateRiskResult,
    valuation: PropertyValuationResult,
    mortgage_risk: MortgageRiskResult,
) -> str:
    return (
        "Recommandation indicative: le dossier reste arbitrable par la banque. "
        f"Le score climatique est de {climate_risk.climate_score}/100, avec une valeur de marche "
        f"estimee a {valuation.market_value:,.0f} EUR et une valeur ajustee climat a "
        f"{valuation.adjusted_value:,.0f} EUR. Le CLTV ressort a {mortgage_risk.cltv:.2f}; "
        f"le pret recommande est donc limite a {mortgage_risk.recommended_loan:,.0f} EUR."
    )


async def _ask_mistral(
    api_key: str,
    payload: TyphoonBankInput,
    climate_risk: ClimateRiskResult,
    valuation: PropertyValuationResult,
    mortgage_risk: MortgageRiskResult,
    prevention: PreventionResult,
    decision: str,
    conditions: list[str],
) -> str:
    prompt = {
        "input": payload.model_dump(),
        "climate_risk": climate_risk.model_dump(),
        "valuation": valuation.model_dump(),
        "mortgage_risk": mortgage_risk.model_dump(),
        "prevention": prevention.model_dump(),
        "draft_decision": decision,
        "draft_conditions": conditions,
    }
    body = {
        "model": settings.mistral_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es un analyste credit bancaire. Tu fournis une recommandation argumentee, "
                    "jamais une decision finale. Reponds en francais, en 120 mots maximum."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"].strip()
