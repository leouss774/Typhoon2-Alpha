from __future__ import annotations

from typing import Any


def _catnat_list(geo_data: dict[str, Any]) -> list[dict]:
    catnat_data = geo_data.get("catnat") or {}
    if isinstance(catnat_data, dict):
        data = catnat_data.get("data")
        if isinstance(data, list):
            return data
    if isinstance(catnat_data, list):
        return catnat_data
    return []


def _classify_arrete(libelle: str) -> str | None:
    low = libelle.lower()
    if "inondation" in low or "crue" in low:
        return "inondation"
    if "sécheresse" in low or "secheresse" in low:
        return "secheresse"
    if any(k in low for k in ("mouvement", "éboulement", "eboulement", "glissement", "affaissement", "tassement")):
        return "mouvement_terrain"
    return None


def parse_catnat_from_georisques(geo_data: dict[str, Any]) -> dict[str, int]:
    counts = {"inondation": 0, "secheresse": 0, "mouvement_terrain": 0}
    for arrete in _catnat_list(geo_data):
        libelle = (arrete.get("libelle_risque_jo") or arrete.get("libelle") or "").strip()
        if not libelle:
            continue
        bucket = _classify_arrete(libelle)
        if bucket:
            counts[bucket] += 1
    counts["total"] = counts["inondation"] + counts["secheresse"] + counts["mouvement_terrain"]
    return counts


def merge_catnat(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    out = {
        "inondation": a.get("inondation", 0) + b.get("inondation", 0),
        "secheresse": a.get("secheresse", 0) + b.get("secheresse", 0),
        "mouvement_terrain": a.get("mouvement_terrain", 0) + b.get("mouvement_terrain", 0),
    }
    out["total"] = out["inondation"] + out["secheresse"] + out["mouvement_terrain"]
    return out
