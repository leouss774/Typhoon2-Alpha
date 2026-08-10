"""
Chargement et validation stricte des regles YAML.

Aucune constante metier ne vit dans le code Python : seuils, poids, bornes et
libelles sont tous dans `rules/`. Ce module refuse de charger un jeu de regles
incoherent plutot que de le corriger silencieusement.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .transforms import ALLOWED_TRANSFORMS

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

#: Champs obligatoires pour toute variable de regle (PROMPT §8).
REQUIRED_VAR_FIELDS = (
    "key",
    "raw_paths",
    "role",
    "weight",
    "transform",
    "direction",
    "physical_mechanism",
    "min_source_rank",
    "allowed_scopes",
    "allowed_time_horizons",
    "on_missing",
    "on_conflict",
    "evidence_level",
    "references",
    "calibration_status",
)

VALID_ROLES = ("F", "V", "protection", "context")
VALID_EVIDENCE = ("high", "medium", "low")
VALID_CALIBRATION = ("calibrated", "provisional_modeling_weight", "published_threshold")
WEIGHT_TOLERANCE = 1e-6


class RulesError(ValueError):
    pass


def load_rules(rules_dir: Path | str | None = None) -> dict:
    """Charge `_common.yaml` + tous les `P*.yaml`, valide, renvoie un dict fige."""
    d = Path(rules_dir) if rules_dir else RULES_DIR
    if not d.is_dir():
        raise RulesError(f"repertoire de regles introuvable : {d}")

    common_path = d / "_common.yaml"
    if not common_path.exists():
        raise RulesError("_common.yaml manquant")
    common = _read_yaml(common_path)

    perils: dict[str, dict] = {}
    for path in sorted(d.glob("P*.yaml")):
        spec = _read_yaml(path)
        pid = spec.get("peril_id")
        if not pid:
            raise RulesError(f"{path.name}: peril_id manquant")
        if pid in perils:
            raise RulesError(f"peril_id duplique : {pid}")
        _validate_peril(spec, path.name)
        perils[pid] = spec

    _validate_common(common)

    bundle = {
        "common": common,
        "perils": perils,
        "rules_version": common.get("rules_version", "unversioned"),
        "rules_digest": _digest(d),
    }
    return bundle


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RulesError(f"{path.name}: le fichier doit contenir un mapping")
    return data


def _validate_common(common: dict) -> None:
    comb = common.get("combination") or {}
    for k in ("exponent_f", "exponent_v", "v_min", "protection_cap"):
        if k not in comb:
            raise RulesError(f"_common.yaml: combination.{k} manquant")
    if not 0 <= float(comb["protection_cap"]) <= 1:
        raise RulesError("protection_cap doit etre dans [0, 1]")
    if not 0 <= float(comb["v_min"]) <= 100:
        raise RulesError("v_min doit etre dans [0, 100]")

    pub = common.get("publication") or {}
    for k in ("max_missing_weight", "rank5_confidence_cap"):
        if k not in pub:
            raise RulesError(f"_common.yaml: publication.{k} manquant")

    conf = common.get("confidence") or {}
    comps = conf.get("components") or {}
    total = sum(float(v) for v in comps.values())
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise RulesError(
            f"_common.yaml: les composantes de confiance somment a {total}, attendu 1.0"
        )


def _validate_peril(spec: dict, fname: str) -> None:
    pid = spec["peril_id"]
    if "hazard_available" not in spec:
        raise RulesError(f"{fname}: hazard_available manquant (bool explicite requis)")

    for block_name in ("frequency", "vulnerability"):
        block = spec.get(block_name)
        if block is None:
            continue
        variables = block.get("variables") or []
        _validate_block(pid, block_name, variables, fname)

    # Un peril sans alea disponible ne doit declarer aucune variable de frequence.
    if not spec.get("hazard_available"):
        freq = spec.get("frequency") or {}
        if freq.get("variables"):
            raise RulesError(
                f"{fname}: hazard_available=false mais des variables de frequence "
                f"sont declarees ; ce peril ne doit produire ni F ni R"
            )


def _validate_block(pid: str, block_name: str, variables: list, fname: str) -> None:
    scored = [v for v in variables if v.get("role") in ("F", "V")]
    protections = [v for v in variables if v.get("role") == "protection"]

    for var in variables:
        missing = [f for f in REQUIRED_VAR_FIELDS if f not in var]
        if missing:
            raise RulesError(
                f"{fname} [{pid}/{block_name}/{var.get('key')}]: champs manquants {missing}"
            )
        if var["role"] not in VALID_ROLES:
            raise RulesError(f"{fname}: role invalide {var['role']!r}")
        if var["evidence_level"] not in VALID_EVIDENCE:
            raise RulesError(f"{fname}: evidence_level invalide {var['evidence_level']!r}")
        if var["calibration_status"] not in VALID_CALIBRATION:
            raise RulesError(
                f"{fname}: calibration_status invalide {var['calibration_status']!r}"
            )
        t = (var.get("transform") or {}).get("type")
        if t not in ALLOWED_TRANSFORMS:
            raise RulesError(f"{fname}: transformation non autorisee {t!r}")
        if not var.get("references"):
            raise RulesError(f"{fname} [{var['key']}]: references obligatoires")

    # Les poids du bloc score doivent sommer a 1 (PROMPT §8).
    if scored:
        total = sum(float(v["weight"]) for v in scored)
        if abs(total - 1.0) > 1e-6:
            raise RulesError(
                f"{fname} [{pid}/{block_name}]: somme des poids = {total:.6f}, attendu 1.0"
            )
        dominants = [v for v in scored if v.get("dominant")]
        if len(dominants) != 1:
            raise RulesError(
                f"{fname} [{pid}/{block_name}]: exactement une variable dominante "
                f"est requise, {len(dominants)} trouvee(s)"
            )

    # Une protection ne peut jamais augmenter V.
    for p in protections:
        red = float(p.get("max_reduction", 0.0))
        if red < 0 or red > 1:
            raise RulesError(
                f"{fname} [{p['key']}]: max_reduction doit etre dans [0, 1]"
            )


def _digest(d: Path) -> str:
    """Empreinte de l'ensemble des regles : garantit la reproductibilite bit a bit."""
    h = hashlib.sha256()
    for path in sorted(d.glob("*.yaml")):
        h.update(path.name.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()[:16]
