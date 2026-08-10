"""
Transformations valeur brute -> indice [0, 1].

Trois formes seulement sont admises (PHASE1_AUDIT §5.1) pour que toute
transformation reste lisible sans executer le code :

  - categorical : table de correspondance explicite
  - linear_ramp : rampe lineaire par morceaux entre points publies
  - boolean     : booleen

Toute autre forme est refusee a la lecture des regles.
"""
from __future__ import annotations

from typing import Any

ALLOWED_TRANSFORMS = ("categorical", "linear_ramp", "boolean")


class TransformError(ValueError):
    pass


def apply_transform(spec: dict, value: Any) -> float:
    kind = spec.get("type")
    if kind not in ALLOWED_TRANSFORMS:
        raise TransformError(
            f"transformation '{kind}' non autorisee ; admises : {ALLOWED_TRANSFORMS}"
        )
    if kind == "categorical":
        return _categorical(spec, value)
    if kind == "linear_ramp":
        return _ramp(spec, value)
    return _boolean(spec, value)


def _norm_key(v: Any) -> str:
    """Normalise une cle categorielle : casse et espaces ignores.

    Deliberement sans suppression d'accents : les libelles officiels
    (`Moyen`, `Fort`) sont recopies tels quels dans les regles YAML.
    """
    return str(v).strip().lower()


def _categorical(spec: dict, value: Any) -> float:
    mapping = spec.get("mapping") or {}
    table = {_norm_key(k): float(v) for k, v in mapping.items()}
    key = _norm_key(value)
    if key in table:
        return _clip(table[key])
    if "unmapped" in spec:
        # Le YAML doit dire explicitement quoi faire d'une modalite inconnue.
        # `null` signifie : traiter comme non renseigne (le moteur l'exclut).
        val = spec["unmapped"]
        if val is None:
            raise TransformError(f"modalite non mappee : {value!r}")
        return _clip(float(val))
    raise TransformError(
        f"modalite non mappee : {value!r} (connues : {sorted(table)})"
    )


def _ramp(spec: dict, value: Any) -> float:
    pts = spec.get("points") or []
    if len(pts) < 2:
        raise TransformError("linear_ramp exige au moins deux points")
    pts = sorted(((float(x), float(y)) for x, y in pts), key=lambda p: p[0])
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise TransformError(f"valeur non numerique pour linear_ramp : {value!r}") from exc

    if x <= pts[0][0]:
        return _clip(pts[0][1])
    if x >= pts[-1][0]:
        return _clip(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return _clip(y1)
            t = (x - x0) / (x1 - x0)
            return _clip(y0 + t * (y1 - y0))
    raise TransformError("point hors rampe")  # pragma: no cover


def _boolean(spec: dict, value: Any) -> float:
    true_v = float(spec.get("true", 1.0))
    false_v = float(spec.get("false", 0.0))
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "oui", "yes", "1"):
            value = True
        elif s in ("false", "non", "no", "0"):
            value = False
        else:
            raise TransformError(f"booleen non interpretable : {value!r}")
    return _clip(true_v if bool(value) else false_v)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
