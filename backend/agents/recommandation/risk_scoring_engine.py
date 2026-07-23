"""Deterministic scoring engine for the Crack AI analyst step.

The engine loads the versioned YAML rules file, evaluates rule conditions
against a condensed risk profile plus an optional declarative building profile,
then returns an auditable, structured score breakdown.

Design principles:
- No score is invented by a model.
- Simple rules always apply when conditions match.
- Composed rules are only applied if explicitly selected by `activated_rule_ids`.
- Confidence notes are informational only; they never modify the score.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from profil_bien_schema import ProfilBien
from schema_profil_risque import ProfilRisqueCondense

RULES_FILE = Path(__file__).with_name("risk_scoring_rules_v1.yaml")
LOW_CONFIDENCE_LEVEL = "low"
MEDIUM_CONFIDENCE_LEVEL = "medium"
HIGH_CONFIDENCE_LEVEL = "high"


class DotDict(dict):
    """Dictionary wrapper that supports attribute access recursively."""

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def load_scoring_rules(path: str | Path = RULES_FILE) -> dict[str, Any]:
    """Load the YAML scoring rules manifest."""
    rules_path = Path(path)
    with rules_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected rules format in {rules_path}")
    return data


def score_profile(
    profile: ProfilRisqueCondense,
    profil_bien: ProfilBien | dict[str, Any] | None = None,
    activated_rule_ids: Iterable[str] | None = None,
    rules_path: str | Path = RULES_FILE,
) -> dict[str, Any]:
    """Score a condensed risk profile with the versioned rule manifest."""
    rules_manifest = load_scoring_rules(rules_path)
    rules = sorted(
        rules_manifest.get("rules", []),
        key=lambda rule: (-int(rule.get("priority", 0)), str(rule.get("rule_id", ""))),
    )
    confidence_rules = list(rules_manifest.get("confidence_rules", []))
    weights = rules_manifest.get("scoring_model", {}).get("global_weights", {})
    selected_rule_ids = set(activated_rule_ids or [])

    context = _build_context(profile, profil_bien)

    triggered_rules: list[dict[str, Any]] = []
    triggered_by_peril: dict[str, list[dict[str, Any]]] = {}
    per_peril_raw: dict[str, int] = {"infiltration": 0, "thermique": 0, "incendie_electrique": 0, "aléas_naturels": 0}

    for rule in rules:
        if bool(rule.get("activated_by_llm")) and rule.get("rule_id") not in selected_rule_ids:
            continue

        if not _rule_matches(rule.get("condition", ""), context):
            continue

        peril = str(rule.get("peril", "aléas_naturels"))
        points = int(rule.get("points", 0))
        applied_rule = {
            "rule_id": rule.get("rule_id"),
            "peril": peril,
            "priority": int(rule.get("priority", 0)),
            "points": points,
            "justification": rule.get("justification"),
            "source_fields": list(rule.get("source_fields", [])),
            "activated_by_llm": bool(rule.get("activated_by_llm", False)),
        }
        per_peril_raw[peril] = per_peril_raw.get(peril, 0) + points
        triggered_rules.append(applied_rule)
        triggered_by_peril.setdefault(peril, []).append(applied_rule)

    peril_scores: dict[str, dict[str, Any]] = {}
    for peril, raw_score in per_peril_raw.items():
        clamped_score = _clamp(raw_score, 0, 100)
        peril_scores[peril] = {
            "raw_score": raw_score,
            "score": clamped_score,
            "max_score": 100,
            "triggered_rules": triggered_by_peril.get(peril, []),
        }

    global_score_raw = sum(
        peril_scores[peril]["score"] * float(weights.get(peril, 0.0))
        for peril in peril_scores
    )
    global_score = _clamp(round(global_score_raw), 0, 100)

    confidence_notes = _evaluate_confidence_rules(confidence_rules, context)
    confidence_level = _confidence_level(confidence_notes)

    return {
        "rules_version": rules_manifest.get("version"),
        "rule_file": str(Path(rules_path)),
        "global_weights": weights,
        "global_score_raw": round(global_score_raw, 2),
        "global_score": global_score,
        "peril_scores": peril_scores,
        "triggered_rules": triggered_rules,
        "confidence": {
            "level": confidence_level,
            "notes": confidence_notes,
        },
        "selection": {
            "activated_rule_ids": sorted(selected_rule_ids),
        },
    }


def _build_context(profile: ProfilRisqueCondense, profil_bien: ProfilBien | dict[str, Any] | None) -> DotDict:
    profile_dict = _wrap(asdict(profile))
    profile_dict["catnat"] = _build_catnat_context(profile)
    profile_dict["profil_bien"] = _wrap(_profil_bien_to_dict(profil_bien))

    for block in profile.donnees_manquantes:
        profile_dict.setdefault(block, DotDict({"disponible": False}))

    # Ensure explicitly missing climate data blocks exist for confidence rules.
    profile_dict.setdefault("drias_meteofrance", DotDict({"disponible": False}))
    profile_dict.setdefault("copernicus", DotDict({"disponible": False}))

    return profile_dict


def _build_catnat_context(profile: ProfilRisqueCondense) -> DotDict:
    events = list(profile.historique_evts.evts)
    most_recent_event = events[0] if events else None
    return DotDict(
        {
            "count_by_type": _wrap(dict(profile.historique_evts.evts_par_type)),
            "total_unique_events": profile.historique_evts.total_evts,
            "most_recent_event_days": most_recent_event.jours_depuis_evt if most_recent_event else None,
            "most_recent_event": _wrap(asdict(most_recent_event)) if most_recent_event else None,
            "nb_evt_10ans": profile.historique_evts.nb_evt_10ans,
        }
    )


def _profil_bien_to_dict(profil_bien: ProfilBien | dict[str, Any] | None) -> dict[str, Any]:
    if profil_bien is None:
        return {"disponible": False}
    if isinstance(profil_bien, dict):
        return dict(profil_bien)
    if is_dataclass(profil_bien):
        return asdict(profil_bien)
    raise TypeError(f"Unsupported profil_bien type: {type(profil_bien)!r}")


def _evaluate_confidence_rules(confidence_rules: list[dict[str, Any]], context: DotDict) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for rule in confidence_rules:
        if _rule_matches(rule.get("condition", ""), context):
            notes.append(
                {
                    "confidence_id": rule.get("confidence_id"),
                    "impact": rule.get("impact"),
                    "note": rule.get("note"),
                }
            )
    return notes


def _confidence_level(notes: list[dict[str, Any]]) -> str:
    impacts = {str(note.get("impact", "")).lower() for note in notes}
    if "high" in impacts:
        return LOW_CONFIDENCE_LEVEL
    if "medium" in impacts:
        return MEDIUM_CONFIDENCE_LEVEL
    return HIGH_CONFIDENCE_LEVEL


def _rule_matches(condition: str, context: DotDict) -> bool:
    try:
        return bool(
            eval(
                condition,
                {"__builtins__": {}, "true": True, "false": False, "null": None},
                context,
            )
        )
    except Exception:
        return False


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return DotDict({key: _wrap(inner) for key, inner in value.items()})
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


def _clamp(value: int | float, minimum: int = 0, maximum: int = 100) -> int:
    return int(max(minimum, min(maximum, value)))


if __name__ == "__main__":
    import json

    from risk_profile_extractor import extract_profil_risque_condense

    payload_path = Path(__file__).with_name("risques_adresse.json")
    profile = extract_profil_risque_condense(json.loads(payload_path.read_text(encoding="utf-8")))
    result = score_profile(profile)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
