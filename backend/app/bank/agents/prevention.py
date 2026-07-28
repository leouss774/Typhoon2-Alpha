"""Prevention recommendations for climate risks."""

from __future__ import annotations

from app.schemas.typhoon_bank import ClimateRiskResult, PreventionRecommendation, PreventionResult


_CATALOG = {
    "flood": [
        ("drainage_peripherique", 8000, 15, "Limiter l'accumulation d'eau autour des fondations."),
        ("batardeaux_etanches", 4500, 12, "Reduire l'entree d'eau lors d'une crue rapide."),
        ("surelevation_equipements", 3500, 8, "Proteger les equipements sensibles en rez-de-chaussee ou sous-sol."),
    ],
    "drought": [
        ("diagnostic_argiles_fondations", 2500, 8, "Verifier la sensibilite RGA avant financement."),
        ("micropieux_ou_reprise_sous_oeuvre", 18000, 22, "Stabiliser les fondations exposees au retrait-gonflement."),
        ("gestion_eaux_pluviales", 6500, 10, "Maintenir une humidite plus reguliere autour du bati."),
    ],
    "heat": [
        ("isolation_toiture_ventilation", 12000, 14, "Reduire la surchauffe et proteger la valeur d'usage."),
        ("protections_solaires_exterieures", 5500, 9, "Limiter les pics de temperature interieurs."),
    ],
    "fire": [
        ("debroussaillement_reglementaire", 2500, 10, "Reduire la charge combustible autour du bien."),
        ("materiaux_exterieurs_resistants_feu", 14000, 16, "Limiter la vulnerabilite des facades et de la toiture."),
    ],
}


class PreventionAgent:
    def run(self, climate_risk: ClimateRiskResult) -> PreventionResult:
        recommendations: list[PreventionRecommendation] = []
        risk_scores = {
            "flood": climate_risk.flood_risk,
            "drought": climate_risk.drought_risk,
            "heat": climate_risk.heat_risk,
            "fire": climate_risk.fire_risk,
        }
        selected = climate_risk.main_risks or [max(risk_scores, key=risk_scores.get)]
        for risk in selected:
            for name, cost, reduction, rationale in _CATALOG.get(risk, [])[:2]:
                recommendations.append(
                    PreventionRecommendation(
                        name=name,
                        risk=risk,
                        cost=cost,
                        risk_reduction=reduction,
                        rationale=rationale,
                    )
                )
        return PreventionResult(recommendations=recommendations)
