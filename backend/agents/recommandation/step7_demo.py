"""Step 7 demo script for Crack AI.

This script runs two cases end to end:
- the real Nantes Collecteur payload with no declarative profile
- the same real payload combined with a synthetic declarative profile that
  activates the composed rules

It prints a single JSON document so the output is easy to inspect, diff, or
pipe into other tooling.
"""

from __future__ import annotations

import json
from pathlib import Path

from final_output_assembler import assemble_final_analysis_output
from profil_bien_schema import ProfilBien
from risk_profile_extractor import extract_profil_risque_condense
from risk_scoring_engine import score_profile

OUTPUT_FILE = Path(__file__).with_name("step7_demo_output.json")


def load_real_payload() -> dict:
    """Load the real Collecteur output bundled with the project."""
    payload_path = Path(__file__).with_name("risques_adresse.json")
    return json.loads(payload_path.read_text(encoding="utf-8"))


def build_synthetic_profil_bien() -> ProfilBien:
    """Build a fictive declarative profile that exercises composed rules."""
    return ProfilBien(
        disponible=True,
        source="synthetic_demo_case",
        annee_construction=1965,
        type_bien="maison",
        usage="habitation",
        type_toiture="tuiles",
        isolation_toiture="faible",
        isolation_murs="moyenne",
        isolation_sol="absente",
        presence_sous_sol=True,
        presence_cave=True,
        climatisation=False,
        installation_electrique_annee=1988,
        presence_detecteurs_fumee=True,
        exposition_solaire="forte",
        observations={
            "case": "synthetic_declarative_cross_check",
            "goal": "activate_composed_rules",
        },
    )


def run_demo_cases() -> dict:
    """Execute the two demo cases and return a serializable payload."""
    payload = load_real_payload()
    profile = extract_profil_risque_condense(payload)

    case_real = assemble_final_analysis_output(
        profile,
        score_profile(profile),
        mistral_selection=None,
        profil_bien=None,
        analysis_id="step7-real-nantes-no-declarative",
    )

    profil_bien = build_synthetic_profil_bien()
    scoring_synthetic = score_profile(
        profile,
        profil_bien=profil_bien,
        activated_rule_ids={
            "COMPOSE_TOITURE_AGEE_ET_HUMIDITE",
            "COMPOSE_ISOLATION_FAIBLE_ET_HUMIDITE",
            "COMPOSE_PRESENCE_CLIMATISATION_ET_STRESS_THERMIQUE",
            "COMPOSE_INSTALLATION_ELECTRIQUE_ANCIENNE",
            "COMPOSE_TOITURE_AGEE_ET_CHALEUR",
            "COMPOSE_INSTALLATION_ELECTRIQUE_AGEE_ET_CHALEUR",
        },
    )
    mistral_stub = {
        "activated_rule_ids": [
            "COMPOSE_TOITURE_AGEE_ET_HUMIDITE",
            "COMPOSE_ISOLATION_FAIBLE_ET_HUMIDITE",
            "COMPOSE_PRESENCE_CLIMATISATION_ET_STRESS_THERMIQUE",
            "COMPOSE_INSTALLATION_ELECTRIQUE_ANCIENNE",
            "COMPOSE_TOITURE_AGEE_ET_CHALEUR",
            "COMPOSE_INSTALLATION_ELECTRIQUE_AGEE_ET_CHALEUR",
        ],
        "declarative_consistency_status": "warning",
        "declarative_consistency_flags": [
            "roof_age_aligned",
            "insulation_aligned",
            "electricity_age_aligned",
            "solar_exposure_aligned",
        ],
    }
    case_synthetic = assemble_final_analysis_output(
        profile,
        scoring_synthetic,
        mistral_selection=mistral_stub,
        profil_bien=profil_bien,
        analysis_id="step7-synthetic-declarative-cross-check",
    )

    return {
        "demo_cases": [
            case_real,
            case_synthetic,
        ]
    }


def main() -> None:
    output = run_demo_cases()
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Saved demo output to: {OUTPUT_FILE}")
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()