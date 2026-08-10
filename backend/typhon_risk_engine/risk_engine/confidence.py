"""
Score de confiance, 0 a 100, STRICTEMENT independant du score de risque.

Une confiance faible n'abaisse jamais le risque : elle signale qu'il ne faut pas
surinterpreter le resultat (decision 18).
"""
from __future__ import annotations

from typing import Optional

from .canonical import Status, VariableBag

EVIDENCE_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.3}

SCALE_SCORE = {
    "dwelling": 1.0,
    "building": 1.0,
    "parcel": 1.0,
    "building_group": 0.8,
    "neighbourhood": 0.8,
    "commune": 0.55,
    "department": 0.35,
    "climate_grid": 0.35,
}


def compute_confidence(spec: dict, common: dict, bag: VariableBag, meta: dict,
                       f_block: Optional[dict], v_block: Optional[dict],
                       warnings: list) -> dict:
    comps = common["confidence"]["components"]
    reasons: list[str] = []

    geo = _geocoding_component(bag, meta, reasons)
    completeness = _completeness_component(f_block, v_block, reasons)
    scale = _scale_component(f_block, v_block, reasons)
    evidence = _evidence_component(f_block, v_block, reasons)
    coherence = _coherence_component(bag, meta, reasons)

    score = (
        geo * float(comps["geocoding_entity"])
        + completeness * float(comps["completeness"])
        + scale * float(comps["spatial_scale"])
        + evidence * float(comps["evidence_level"])
        + coherence * float(comps["coherence"])
    ) * 100.0

    # Plafond : un score porte majoritairement par des donnees de rang 5.
    cap_applied = None
    if _mostly_rank5(f_block, v_block):
        cap = float(common["publication"]["rank5_confidence_cap"])
        if score > cap:
            score = cap
            cap_applied = (
                f"plafonnee a {cap:.0f} : score porte majoritairement par des "
                f"donnees de rang 5 (contexte communal ou proxy)"
            )
            reasons.append(cap_applied)

    for blk, tag in ((f_block, "F"), (v_block, "V")):
        if blk and not blk.get("determinate"):
            reasons.append(f"bloc {tag} indetermine : {blk.get('indeterminate_reason')}")
        for m in (blk or {}).get("missing_variables", []):
            if m["reason"].startswith("source en erreur"):
                reasons.append(f"erreur de source sur {m['key']}")

    return {
        "score": int(round(score)),
        "score_raw": round(score, 4),
        "components": {
            "geocoding_entity": round(geo, 4),
            "completeness": round(completeness, 4),
            "spatial_scale": round(scale, 4),
            "evidence_level": round(evidence, 4),
            "coherence": round(coherence, 4),
        },
        "weights": {k: float(v) for k, v in comps.items()},
        "cap_applied": cap_applied,
        "reasons": sorted(set(reasons)),
        "independent_of_risk": True,
    }


def _geocoding_component(bag: VariableBag, meta: dict, reasons: list) -> float:
    v = bag.get("meta.geocoding.score")
    ban = float(v.value) if v and v.usable and v.value is not None else 0.0
    if ban == 0.0:
        reasons.append("score de geocodage BAN indisponible")

    em = meta.get("entity_match") or {}
    level = em.get("level")
    if level == "building_group":
        entity = 0.75
        reasons.append(
            "correspondance au GROUPE de batiments, pas au logement : les attributs "
            "BDNB decrivent l'ensemble immobilier"
        )
    elif level == "uncertain":
        entity = 0.4
        reasons.append("correspondance d'entite incertaine")
    elif level == "none":
        entity = 0.2
        reasons.append("aucune correspondance BDNB")
    else:
        entity = 1.0

    parcel = 1.0 if (em.get("parcel_ids")) else 0.5
    if not em.get("parcel_ids"):
        reasons.append("parcelle cadastrale non identifiee")

    return 0.4 * ban + 0.4 * entity + 0.2 * parcel


def _completeness_component(f_block, v_block, reasons) -> float:
    covs = [b["coverage"] for b in (f_block, v_block) if b]
    if not covs:
        return 0.0
    val = sum(covs) / len(covs)
    if val < 0.5:
        reasons.append(f"completude ponderee faible ({val * 100:.0f} %)")
    return val


def _scale_component(f_block, v_block, reasons) -> float:
    used = []
    for b in (f_block, v_block):
        used.extend((b or {}).get("used_variables", []))
    if not used:
        return 0.0
    total_w = sum(u["weight"] for u in used)
    if total_w <= 0:
        return 0.0
    val = sum(u["weight"] * SCALE_SCORE.get(u["scope"], 0.3) for u in used) / total_w
    if val < 0.6:
        reasons.append("score porte par des donnees d'echelle grossiere")
    return val


def _evidence_component(f_block, v_block, reasons) -> float:
    used = []
    for b in (f_block, v_block):
        used.extend((b or {}).get("used_variables", []))
    if not used:
        return 0.0
    total_w = sum(u["weight"] for u in used)
    if total_w <= 0:
        return 0.0
    val = sum(u["weight"] * EVIDENCE_SCORE.get(u["evidence_level"], 0.3)
              for u in used) / total_w
    n_prov = sum(1 for u in used
                 if u["calibration_status"] == "provisional_modeling_weight")
    if n_prov:
        reasons.append(
            f"{n_prov} ponderation(s) provisoire(s) non calibree(s) dans ce score"
        )
    return val


def _coherence_component(bag: VariableBag, meta: dict, reasons: list) -> float:
    score = 1.0
    for c in bag.conflicts:
        score -= 0.15
        reasons.append(
            f"conflit sur {c['key']} : {c['kept']['source']} retenu "
            f"(rang {c['kept']['source_rank']}) contre {c['dropped']['source']} "
            f"(rang {c['dropped']['source_rank']})"
        )
    cat = meta.get("catnat") or {}
    if cat.get("warning"):
        score -= 0.10
        reasons.append(cat["warning"])
    for w in meta.get("warnings", []):
        if "erreur" in w.lower() or "non configure" in w.lower():
            score -= 0.05
    return max(0.0, score)


def _mostly_rank5(f_block, v_block) -> bool:
    used = []
    for b in (f_block, v_block):
        used.extend((b or {}).get("used_variables", []))
    if not used:
        return False
    total_w = sum(u["weight"] for u in used)
    if total_w <= 0:
        return False
    w5 = sum(u["weight"] for u in used if u["source_rank"] >= 5)
    return (w5 / total_w) > 0.5
