"""
Moteur de calcul deterministe.

Aucun appel LLM, aucun aleatoire, aucune constante metier : tout vient des regles
YAML. Pour un meme couple (donnees, version de regles), la sortie est identique
bit a bit.

Conventions imposees :
  - `F` est un INDICE ORDINAL d'alea / exposition, jamais une frequence annuelle.
  - Un bloc est INDETERMINE si sa variable dominante manque, ou si plus de
    `max_missing_weight` du poids theorique manque.
  - Une donnee manquante n'est jamais imputee (ni favorable, ni defavorable).
  - Les protections agissent uniquement sur V, et ne peuvent jamais l'augmenter.
  - Aucun score global multi-perils n'est produit.
"""
from __future__ import annotations

from typing import Any, Optional

from .canonical import Scope, Status, TimeHorizon, VariableBag
from .confidence import compute_confidence
from .normalizer import normalize
from .rules_loader import load_rules
from .transforms import TransformError, apply_transform

ENGINE_VERSION = "2.0.0"

FREQUENCY_LABEL = "indice ordinal d'alea / exposition (PAS une frequence annuelle)"
VULNERABILITY_ONLY_LABEL = (
    "Sensibilite du batiment hors exposition — ne constitue pas un score de risque"
)


class PerilStatus:
    CALCULATED = "CALCULATED"
    NEEDS_USER_INPUT = "NEEDS_USER_INPUT"
    INDETERMINATE = "INDETERMINATE"
    VULNERABILITY_ONLY = "VULNERABILITY_ONLY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"


def assess(collector: dict, answers: Optional[dict] = None,
           rules: Optional[dict] = None) -> dict:
    """Point d'entree principal. Renvoie un rapport par peril, sans score global."""
    rules = rules or load_rules()
    bag, meta = normalize(collector, answers)

    perils = {}
    for pid in sorted(rules["perils"]):
        perils[pid] = _assess_peril(rules["perils"][pid], rules["common"], bag, meta)

    return {
        "engine_version": ENGINE_VERSION,
        "rules_version": rules["rules_version"],
        "rules_digest": rules["rules_digest"],
        "address": meta.get("address"),
        "entity_match": meta.get("entity_match"),
        "building_typology": meta.get("building_typology"),
        "source_status": meta.get("source_status"),
        "commune_context": meta.get("commune_context"),
        "catnat_context": meta.get("catnat"),
        "prospective_context": meta.get("prospective_context"),
        "pii_dropped": meta.get("pii_dropped", []),
        "global_warnings": meta.get("warnings", []),
        "perils": perils,
        # Garde-fou explicite : ce moteur ne produit AUCUN agregat multi-perils
        # et AUCUNE valeur monetaire.
        "global_score": None,
        "monetary_output": None,
    }


# --- Evaluation d'un peril --------------------------------------------------------


def _assess_peril(spec: dict, common: dict, bag: VariableBag, meta: dict) -> dict:
    pid = spec["peril_id"]
    warnings: list[str] = []
    out: dict[str, Any] = {
        "peril_id": pid,
        "peril_name": spec.get("name"),
        "status": PerilStatus.INDETERMINATE,
        "frequency": None,
        "vulnerability": None,
        "risk": None,
        "confidence": None,
        "current_context": {},
        "prospective_context": {},
        "dominant_factors": [],
        "protective_factors": [],
        "warnings": warnings,
        "evidence": [],
        "required_user_questions": [],
    }

    # --- Applicabilite selon la typologie du bien.
    na = _check_applicability(spec, meta)
    if na is not None:
        out["status"] = PerilStatus.NOT_APPLICABLE
        out["warnings"].append(na)
        return out

    typo = meta.get("building_typology") or {}
    for caveat in spec.get("typology_caveats", []):
        if typo.get("kind") in caveat.get("applies_to", []):
            warnings.append(caveat["message"])

    # --- Bloc vulnerabilite (toujours tente).
    v_block = _score_block(spec.get("vulnerability"), common, bag, "V")
    prot = _apply_protections(spec.get("vulnerability"), common, bag,
                              v_block["score_raw"])
    if v_block["determinate"]:
        v_final = prot["v_after"]
        v_min = float(common["combination"]["v_min"])
        v_final = max(v_min, v_final)
        v_block["score_raw"] = v_final
        v_block["score"] = int(round(v_final))
        v_block["protection_reduction"] = prot["reduction"]
        out["protective_factors"] = prot["factors"]
    else:
        v_block["protection_reduction"] = 0.0

    out["vulnerability"] = _public_block(v_block)
    out["required_user_questions"] = v_block["missing_user_keys"]
    out["evidence"] = v_block["evidence"] 

    # --- Peril sans alea disponible : V seul, jamais F ni R (D06).
    if not spec.get("hazard_available"):
        reason = spec.get("hazard_absence_reason", "donnee d'alea indisponible")
        out["frequency"] = None
        out["risk"] = None
        out["vulnerability"]["label"] = VULNERABILITY_ONLY_LABEL
        warnings.append(f"Aucun score d'alea : {reason}")
        out["status"] = (
            PerilStatus.VULNERABILITY_ONLY if v_block["determinate"]
            else PerilStatus.NEEDS_USER_INPUT
        )
        out["confidence"] = compute_confidence(spec, common, bag, meta,
                                               None, v_block, warnings)
        out["current_context"] = _context(spec, meta)
        return out

    # --- Bloc frequence.
    f_block = _score_block(spec.get("frequency"), common, bag, "F")
    f_block["label"] = FREQUENCY_LABEL
    out["frequency"] = _public_block(f_block)
    out["evidence"] = f_block["evidence"] + v_block["evidence"]

    if not f_block["determinate"]:
        # Si le blocage vient de questions non repondues, l'utilisateur peut le lever.
        out["required_user_questions"] = sorted(
            set(out["required_user_questions"]) | set(f_block["missing_user_keys"])
        )
        out["status"] = (
            PerilStatus.NEEDS_USER_INPUT if f_block["missing_user_keys"]
            else PerilStatus.INDETERMINATE
        )
        warnings.append(
            f"F indetermine : {f_block['indeterminate_reason']}. "
            f"Aucun score de risque n'est publie."
        )
    elif not v_block["determinate"]:
        out["status"] = (
            PerilStatus.NEEDS_USER_INPUT if v_block["missing_user_keys"]
            else PerilStatus.INDETERMINATE
        )
        warnings.append(f"V indetermine : {v_block['indeterminate_reason']}.")
    else:
        out["status"] = PerilStatus.CALCULATED
        r = _combine(f_block["score_raw"], v_block["score_raw"], common)
        out["risk"] = {
            "score": int(round(r)),
            "score_raw": round(r, 4),
            "class": _risk_class(r, common),
            "formula": common["combination"]["formula_label"],
            "calibration_status": "provisional_uncalibrated",
        }

    out["dominant_factors"] = _dominant_factors(f_block, v_block)
    out["confidence"] = compute_confidence(spec, common, bag, meta,
                                           f_block, v_block, warnings)
    out["current_context"] = _context(spec, meta)
    out["prospective_context"] = {
        "note": "Vide par construction : les projections climatiques n'entrent "
                "jamais dans F, V ou R (decision D05)."
    }
    return out


# --- Calcul d'un bloc ---------------------------------------------------------------


def _score_block(block: Optional[dict], common: dict, bag: VariableBag,
                 role: str) -> dict:
    result = {
        "score": None,
        "score_raw": 0.0,
        "coverage": 0.0,
        "determinate": False,
        "indeterminate_reason": None,
        "used_variables": [],
        "missing_variables": [],
        "missing_user_keys": [],
        "contributions": [],
        "evidence": [],
    }
    if not block or not block.get("variables"):
        result["indeterminate_reason"] = "aucune variable de score declaree"
        return result

    scored = [v for v in block["variables"] if v.get("role") == role]
    if not scored:
        result["indeterminate_reason"] = f"aucune variable de role {role}"
        return result

    dominant_key = next((v["key"] for v in scored if v.get("dominant")), None)
    available, missing = [], []

    for rule in scored:
        var = bag.get(rule["key"])
        ok, reason = _variable_admissible(rule, var)
        if not ok:
            missing.append({
                "key": rule["key"],
                "weight": float(rule["weight"]),
                "status": (var.status.value if var else Status.NOT_COLLECTED.value),
                "reason": reason,
                "source_hint": rule.get("raw_paths", []),
            })
            continue
        try:
            index = apply_transform(rule["transform"], var.value)
        except TransformError as exc:
            missing.append({
                "key": rule["key"], "weight": float(rule["weight"]),
                "status": var.status.value, "reason": f"transformation impossible : {exc}",
                "source_hint": rule.get("raw_paths", []),
            })
            continue
        available.append({
            "key": rule["key"], "weight": float(rule["weight"]),
            "index": round(index, 6), "value": var.value,
            "source": var.source, "source_rank": var.source_rank,
            "scope": var.scope.value, "evidence_level": rule["evidence_level"],
            "calibration_status": rule["calibration_status"],
        })
        result["evidence"].append({
            "key": rule["key"], "mechanism": rule["physical_mechanism"],
            "references": rule["references"], "evidence_level": rule["evidence_level"],
        })

    coverage = sum(a["weight"] for a in available)
    result["coverage"] = round(coverage, 4)
    result["used_variables"] = available
    result["missing_variables"] = missing
    result["missing_user_keys"] = sorted(
        m["key"] for m in missing
        if any(str(p).startswith("questionnaire.") for p in (m.get("source_hint") or []))
    )

    # Regle 16 : dominante absente -> INDETERMINE, meme si < 50 % manque.
    if dominant_key and dominant_key not in {a["key"] for a in available}:
        result["indeterminate_reason"] = (
            f"variable dominante absente ({dominant_key})"
        )
        return result

    max_missing = float(common["publication"]["max_missing_weight"])
    if (1.0 - coverage) > max_missing + 1e-9:
        result["indeterminate_reason"] = (
            f"{(1.0 - coverage) * 100:.0f} % du poids theorique manquant "
            f"(seuil {max_missing * 100:.0f} %)"
        )
        return result

    # Renormalisation autorisee : dominante presente ET seuil respecte (regle 17).
    score = 100.0 * sum(a["weight"] * a["index"] for a in available) / coverage
    result["score_raw"] = score
    result["score"] = int(round(score))
    result["determinate"] = True
    result["contributions"] = sorted(
        (
            {
                "key": a["key"],
                "contribution": round(a["weight"] * a["index"] / coverage, 6),
                "index": a["index"],
                "weight_renormalized": round(a["weight"] / coverage, 6),
            }
            for a in available
        ),
        key=lambda c: (-c["contribution"], c["key"]),
    )
    return result


def _variable_admissible(rule: dict, var) -> tuple[bool, str]:
    if var is None:
        return False, "variable absente du bag (NOT_COLLECTED)"
    if var.is_default:
        return False, "valeur par defaut exclue du calcul (decision D04)"
    if var.status is Status.SOURCE_ERROR:
        return False, "source en erreur (SOURCE_ERROR) — pas une absence de phenomene"
    if var.status is Status.NOT_CONFIGURED:
        return False, "source non configuree (NOT_CONFIGURED)"
    if var.status is Status.NOT_COLLECTED:
        return False, "champ non collecte par le pipeline"
    if var.status is Status.USER_UNKNOWN:
        return False, "l'habitant a repondu 'Je ne sais pas'"
    if var.status is Status.UNKNOWN:
        return False, "valeur presente mais indeterminee"
    if var.status is Status.NOT_APPLICABLE:
        return False, "sans objet pour ce bien"
    if not var.usable:
        return False, f"statut non exploitable ({var.status.value})"
    if var.time_horizon.value not in rule["allowed_time_horizons"]:
        return False, (
            f"horizon temporel {var.time_horizon.value} non admis "
            f"(admis : {rule['allowed_time_horizons']})"
        )
    if var.scope.value not in rule["allowed_scopes"]:
        return False, (
            f"echelle {var.scope.value} non admise "
            f"(admises : {rule['allowed_scopes']})"
        )
    if var.source_rank > int(rule["min_source_rank"]):
        return False, (
            f"rang de source {var.source_rank} insuffisant "
            f"(exige <= {rule['min_source_rank']})"
        )
    if var.status is Status.NO_FEATURE_FOUND and not rule.get("accept_no_feature", False):
        return False, (
            "NO_FEATURE_FOUND : absence d'objet non interpretable comme une valeur "
            "pour cette regle"
        )
    return True, ""


# --- Protections ---------------------------------------------------------------------


def _apply_protections(block: Optional[dict], common: dict, bag: VariableBag,
                       v_base: float) -> dict:
    out = {"v_after": v_base, "reduction": 0.0, "factors": []}
    if not block:
        return out
    protections = [v for v in block.get("variables", []) if v.get("role") == "protection"]
    if not protections:
        return out

    factor = 1.0
    for rule in sorted(protections, key=lambda r: r["key"]):
        var = bag.get(rule["key"])
        ok, _ = _variable_admissible(rule, var)
        if not ok:
            continue
        try:
            index = apply_transform(rule["transform"], var.value)
        except TransformError:
            continue
        r = float(rule["max_reduction"]) * index
        r = max(0.0, min(1.0, r))   # une protection ne peut jamais augmenter V
        if r <= 0:
            continue
        factor *= (1.0 - r)
        out["factors"].append({
            "key": rule["key"], "reduction": round(r, 6),
            "mechanism": rule["physical_mechanism"],
            "evidence_level": rule["evidence_level"],
        })

    reduction = 1.0 - factor
    cap = float(common["combination"]["protection_cap"])
    reduction = min(reduction, cap)
    out["reduction"] = round(reduction, 6)
    out["v_after"] = v_base * (1.0 - reduction)
    return out


# --- Combinaison ------------------------------------------------------------------------


def _combine(f: float, v: float, common: dict) -> float:
    a = float(common["combination"]["exponent_f"])
    b = float(common["combination"]["exponent_v"])
    if f <= 0:
        return 0.0          # pas d'alea -> pas de risque, quelle que soit V
    return 100.0 * ((f / 100.0) ** a) * ((v / 100.0) ** b)


def _risk_class(score: float, common: dict) -> str:
    """Classe de lecture, determinee sur le score ARRONDI affiche.

    Les bandes du YAML sont des entiers contigus (0-19, 20-39, ...). Classer sur
    le flottant brut laisserait des trous entre 79 et 80 : un score de 79,4
    n'appartiendrait a aucune bande. On classe donc sur l'entier publie, ce qui
    garantit qu'une classe existe toujours et qu'elle correspond au nombre lu.
    """
    s = int(round(score))
    for band in common["risk_classes"]:
        if int(band["min"]) <= s <= int(band["max"]):
            return band["label"]
    raise ValueError(f"score {s} hors de toutes les bandes de risque")


# --- Divers -------------------------------------------------------------------------------


def _public_block(block: dict) -> dict:
    return {
        "score": block["score"],
        "score_raw": round(block["score_raw"], 4) if block["determinate"] else None,
        "label": block.get("label"),
        "determinate": block["determinate"],
        "indeterminate_reason": block["indeterminate_reason"],
        "coverage": block["coverage"],
        "used_variables": [a["key"] for a in block["used_variables"]],
        "missing_variables": block["missing_variables"],
        "protection_reduction": block.get("protection_reduction", 0.0),
        "detail": block["used_variables"],
    }


def _dominant_factors(f_block: dict, v_block: dict) -> list:
    out = []
    for tag, blk in (("F", f_block), ("V", v_block)):
        for c in blk.get("contributions", [])[:3]:
            out.append({"block": tag, **c})
    return sorted(out, key=lambda c: (-c["contribution"], c["block"], c["key"]))


def _check_applicability(spec: dict, meta: dict) -> Optional[str]:
    rules = spec.get("applicability", {}).get("not_applicable_if", [])
    typo = (meta.get("building_typology") or {}).get("kind")
    for r in rules:
        if typo in r.get("typology_in", []):
            return r["reason"]
    return None


def _context(spec: dict, meta: dict) -> dict:
    codes = spec.get("commune_context_codes", [])
    ctx = meta.get("commune_context") or {}
    matched = [r for r in ctx.get("risks", []) if r.get("code") in codes]
    return {
        "commune_risk_codes_matched": matched,
        "weight_in_F": 0.0,
        "note": ctx.get("note"),
    }
