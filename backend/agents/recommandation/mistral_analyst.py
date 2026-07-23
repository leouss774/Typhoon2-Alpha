"""Mistral structured-output wrapper for the Crack AI analyst step.

The model is only allowed to choose from referential rule_ids already defined
in the scoring manifest. It never invents scores; it only returns a structured
selection and a declarative consistency status.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from profil_bien_schema import ProfilBien
from risk_scoring_engine import RULES_FILE, load_scoring_rules
from schema_profil_risque import ProfilRisqueCondense

DEFAULT_MISTRAL_MODEL = "mistral-large-latest"
CONSISTENCY_STATUS_ENUM = ["ok", "warning", "fail", "unknown"]
CONSISTENCY_FLAG_ENUM = [
    "roof_age_aligned",
    "roof_age_mismatch",
    "insulation_aligned",
    "insulation_mismatch",
    "electricity_age_aligned",
    "electricity_age_mismatch",
    "solar_exposure_aligned",
    "solar_exposure_mismatch",
    "basement_humidity_aligned",
    "basement_humidity_mismatch",
]


def build_mistral_system_prompt(rules_manifest: dict[str, Any]) -> str:
    """Build the system prompt that constrains the model to referential rule_ids."""
    composed_rules = [rule for rule in rules_manifest.get("rules", []) if bool(rule.get("activated_by_llm"))]
    allowed_rule_ids = [str(rule.get("rule_id")) for rule in composed_rules]

    lines = [
        "Tu es l'Agent Analyste de Crack AI.",
        "Tu dois répondre uniquement avec un JSON strict conforme au schéma fourni.",
        "Tu n'as pas le droit d'inventer de score, de seuil ou de justification libre.",
        "Tu dois sélectionner uniquement des rule_id présents dans le référentiel fourni ci-dessous.",
        "Si aucune règle composée ne s'applique, retourne une liste vide.",
        "Tu dois aussi évaluer la cohérence du déclaratif avec des statuts contraints, sans texte libre.",
        "",
        "Rule IDs autorisés pour activation composée:",
    ]
    lines.extend(f"- {rule_id}" for rule_id in allowed_rule_ids)
    lines.extend(
        [
            "",
            "Rappel: les rule_id non composées du moteur sont appliquées de façon déterministe en aval;",
            "ta tâche est uniquement de sélectionner les rule_id composées qui doivent être activées.",
        ]
    )
    return "\n".join(lines)


def build_mistral_response_schema(rules_manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON Schema payload accepted by Mistral structured outputs."""
    composed_rules = [rule for rule in rules_manifest.get("rules", []) if bool(rule.get("activated_by_llm"))]
    allowed_rule_ids = [str(rule.get("rule_id")) for rule in composed_rules]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "activated_rule_ids": {
                "type": "array",
                "items": {"type": "string", "enum": allowed_rule_ids},
                "uniqueItems": True,
                "description": "Liste des rule_id composées à activer dans le moteur déterministe.",
            },
            "declarative_consistency_status": {
                "type": "string",
                "enum": CONSISTENCY_STATUS_ENUM,
                "description": "Statut global de cohérence du déclaratif.",
            },
            "declarative_consistency_flags": {
                "type": "array",
                "items": {"type": "string", "enum": CONSISTENCY_FLAG_ENUM},
                "uniqueItems": True,
                "description": "Indicateurs de cohérence strictement contraints.",
            },
        },
        "required": [
            "activated_rule_ids",
            "declarative_consistency_status",
            "declarative_consistency_flags",
        ],
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "crack_ai_mistral_analyst_selection_v1",
            "schema": schema,
            "strict": True,
        },
    }


def build_mistral_messages(
    profile: ProfilRisqueCondense,
    profil_bien: ProfilBien | dict[str, Any] | None,
    rules_manifest: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build the messages sent to Mistral for composed-rule selection."""
    rules_manifest = rules_manifest or load_scoring_rules(RULES_FILE)
    system_prompt = build_mistral_system_prompt(rules_manifest)
    payload = {
        "adresse": profile.adresse,
        "code_insee": profile.code_insee,
        "proxy_climatique": {
            "code": profile.proxy_climatique.code,
            "source": profile.proxy_climatique.source,
            "latitude": profile.proxy_climatique.latitude,
            "seuils": profile.proxy_climatique.seuils,
            "disponible": profile.proxy_climatique.disponible,
        },
        "risques_naturels": {
            code: {
                "present": risk.present,
                "statut_adresse": risk.statut_adresse,
                "statut_commune": risk.statut_commune,
                "disponible": risk.disponible,
            }
            for code, risk in profile.risques_naturels.items()
        },
        "historique_catnat": {
            "total_evts": profile.historique_evts.total_evts,
            "evts_par_type": profile.historique_evts.evts_par_type,
            "nb_evt_10ans": profile.historique_evts.nb_evt_10ans,
            "most_recent_event_days": profile.historique_evts.evt_le_plus_recent.jours_depuis_evt
            if profile.historique_evts.evt_le_plus_recent
            else None,
        },
        "profil_bien": _profil_bien_payload(profil_bien),
        "rule_ids_composed_autorises": [
            str(rule.get("rule_id"))
            for rule in rules_manifest.get("rules", [])
            if bool(rule.get("activated_by_llm"))
        ],
    }
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Sélectionne uniquement les rule_id composées pertinentes et retourne le statut de cohérence.\n"
                f"Contexte JSON:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]


def call_mistral_analyst_selection(
    profile: ProfilRisqueCondense,
    profil_bien: ProfilBien | dict[str, Any] | None,
    api_key: str | None = None,
    model: str = DEFAULT_MISTRAL_MODEL,
    client: Any | None = None,
    rules_path: str | Path = RULES_FILE,
) -> dict[str, Any]:
    """Call Mistral with native structured output and return the parsed selection."""
    rules_manifest = load_scoring_rules(rules_path)
    messages = build_mistral_messages(profile, profil_bien, rules_manifest)
    response_format = build_mistral_response_schema(rules_manifest)

    mistral_client = client
    if mistral_client is None:
        if api_key is None:
            raise ValueError("api_key is required when client is not provided")
        mistral_client = _build_client(api_key)

    response = mistral_client.chat.complete(
        model=model,
        messages=messages,
        response_format=response_format,
        temperature=0.0,
        top_p=1.0,
        safe_prompt=True,
        random_seed=42,
    )
    content = response.choices[0].message.content
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    if not isinstance(content, str):
        raise ValueError("Unexpected Mistral content type")

    parsed = json.loads(content)
    _validate_selection_payload(parsed, rules_manifest)
    return parsed


def _build_client(api_key: str) -> Any:
    try:
        from mistralai import Mistral
    except ImportError as exc:  # pragma: no cover - dependency issue is surfaced explicitly
        raise ImportError(
            "The official Mistral SDK is required. Install the `mistralai` package."
        ) from exc

    return Mistral(api_key=api_key)


def _profil_bien_payload(profil_bien: ProfilBien | dict[str, Any] | None) -> dict[str, Any]:
    if profil_bien is None:
        return {"disponible": False}
    if isinstance(profil_bien, dict):
        return dict(profil_bien)
    return {
        key: value
        for key, value in vars(profil_bien).items()
        if not key.startswith("_")
    }


def _validate_selection_payload(payload: dict[str, Any], rules_manifest: dict[str, Any]) -> None:
    composed_rule_ids = {
        str(rule.get("rule_id")) for rule in rules_manifest.get("rules", []) if bool(rule.get("activated_by_llm"))
    }
    activated_rule_ids = set(payload.get("activated_rule_ids", []))
    unknown = activated_rule_ids - composed_rule_ids
    if unknown:
        raise ValueError(f"Mistral returned unknown rule_ids: {sorted(unknown)}")

    status = payload.get("declarative_consistency_status")
    if status not in CONSISTENCY_STATUS_ENUM:
        raise ValueError(f"Unexpected declarative_consistency_status: {status!r}")

    flags = payload.get("declarative_consistency_flags", [])
    unknown_flags = set(flags) - set(CONSISTENCY_FLAG_ENUM)
    if unknown_flags:
        raise ValueError(f"Mistral returned unknown declarative flags: {sorted(unknown_flags)}")


if __name__ == "__main__":
    import json
    from pathlib import Path

    from risk_profile_extractor import extract_profil_risque_condense

    payload_path = Path(__file__).with_name("risques_adresse.json")
    profile = extract_profil_risque_condense(json.loads(payload_path.read_text(encoding="utf-8")))
    print(build_mistral_system_prompt(load_scoring_rules()))
    print(json.dumps(build_mistral_response_schema(load_scoring_rules()), ensure_ascii=False, indent=2))
