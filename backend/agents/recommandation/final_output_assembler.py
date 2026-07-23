"""Final output assembler for the Crack AI analyst step.

This layer merges the deterministic score output with the optional Mistral
selection into a single JSON-serializable payload. The assembler does not
change the score; it only packages already computed, traceable data.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from schema_profil_risque import ProfilRisqueCondense

FINAL_OUTPUT_VERSION = "1.0"


def assemble_final_analysis_output(
    profile: ProfilRisqueCondense,
    scoring_result: dict[str, Any],
    mistral_selection: dict[str, Any] | None = None,
    profil_bien: Any | None = None,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    """Merge deterministic scoring and optional Mistral selection into final output."""
    final_output: dict[str, Any] = {
        "version": FINAL_OUTPUT_VERSION,
        "analysis_id": analysis_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "address": {
            "adresse": profile.adresse,
            "code_insee": profile.code_insee,
            "coordonnees": {
                "latitude": profile.coordonnees_lat,
                "longitude": profile.coordonnees_lon,
            },
            "geocodage_score": profile.geocodage_score,
        },
        "risk_context": {
            "proxy_climatique": _serialize_dataclass(profile.proxy_climatique),
            "rga": _serialize_dataclass(profile.rga),
            "zone_sismique": _serialize_dataclass(profile.zone_sismique),
            "radon": _serialize_dataclass(profile.radon),
            "cavites": _serialize_dataclass(profile.cavites),
            "historique_catnat": _serialize_historique(profile),
            "facilites_proches": _serialize_dataclass(profile.facilites_proches),
            "donnees_topo": _serialize_dataclass(profile.donnees_topo),
            "eaux_souterraines": _serialize_dataclass(profile.eaux_souterraines),
            "donnees_manquantes": list(profile.donnees_manquantes),
        },
        "profil_bien": _serialize_profil_bien(profil_bien),
        "score": {
            "global": scoring_result.get("global_score"),
            "global_raw": scoring_result.get("global_score_raw"),
            "weights": scoring_result.get("global_weights", {}),
            "perils": scoring_result.get("peril_scores", {}),
        },
        "rules": {
            "version": scoring_result.get("rules_version"),
            "file": scoring_result.get("rule_file"),
            "triggered": scoring_result.get("triggered_rules", []),
        },
        "confidence": scoring_result.get("confidence", {}),
        "traceability": {
            "selected_composed_rule_ids": scoring_result.get("selection", {}).get("activated_rule_ids", []),
            "score_engine": "deterministic_yaml_v1",
            "mistral_used": mistral_selection is not None,
        },
    }

    if mistral_selection is not None:
        final_output["mistral"] = {
            "activated_rule_ids": list(mistral_selection.get("activated_rule_ids", [])),
            "declarative_consistency_status": mistral_selection.get("declarative_consistency_status"),
            "declarative_consistency_flags": list(mistral_selection.get("declarative_consistency_flags", [])),
        }
    else:
        final_output["mistral"] = {
            "activated_rule_ids": [],
            "declarative_consistency_status": "unknown",
            "declarative_consistency_flags": [],
        }

    final_output["score"]["perils"] = _normalize_peril_breakdown(final_output["score"]["perils"])
    return final_output


def _serialize_profil_bien(profil_bien: Any | None) -> dict[str, Any]:
    if profil_bien is None:
        return {"disponible": False}
    if isinstance(profil_bien, dict):
        return dict(profil_bien)
    if is_dataclass(profil_bien):
        return asdict(profil_bien)
    return {"disponible": False, "source": "unknown"}


def _serialize_historique(profile: ProfilRisqueCondense) -> dict[str, Any]:
    most_recent = profile.historique_evts.evt_le_plus_recent
    return {
        "total_evts": profile.historique_evts.total_evts,
        "evts_par_type": dict(profile.historique_evts.evts_par_type),
        "nb_evt_10ans": profile.historique_evts.nb_evt_10ans,
        "evt_le_plus_recent": _serialize_event(most_recent),
        "disponible": profile.historique_evts.disponible,
    }


def _serialize_event(event: Any | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "code_national": event.code_national,
        "type_risque": event.type_risque,
        "date_debut": event.date_debut.isoformat(),
        "date_fin": event.date_fin.isoformat(),
        "date_publication_jo": event.date_publication_jo.isoformat(),
        "jours_depuis_evt": event.jours_depuis_evt,
        "jours_depuis_publi": event.jours_depuis_publi,
    }


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {"disponible": False}


def _normalize_peril_breakdown(perils: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for peril, payload in perils.items():
        normalized[peril] = {
            "raw_score": payload.get("raw_score"),
            "score": payload.get("score"),
            "max_score": payload.get("max_score"),
            "triggered_rules": list(payload.get("triggered_rules", [])),
        }
    return normalized


if __name__ == "__main__":
    import json
    from pathlib import Path

    from mistral_analyst import build_mistral_messages
    from risk_profile_extractor import extract_profil_risque_condense
    from risk_scoring_engine import load_scoring_rules, score_profile

    payload_path = Path(__file__).with_name("risques_adresse.json")
    profile = extract_profil_risque_condense(json.loads(payload_path.read_text(encoding="utf-8")))
    scoring = score_profile(profile)
    print(json.dumps(assemble_final_analysis_output(profile, scoring), ensure_ascii=False, indent=2, default=str))
