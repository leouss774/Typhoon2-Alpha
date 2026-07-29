"""Périmètre géographique : région Provence-Alpes-Côte d'Azur (PACA)."""

from __future__ import annotations

PACA_DEPARTMENTS: dict[str, str] = {
    "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes",
    "06": "Alpes-Maritimes",
    "13": "Bouches-du-Rhône",
    "83": "Var",
    "84": "Vaucluse",
}


def department_code_from_citycode(citycode: str) -> str:
    return citycode[:2]


def is_in_paca(citycode: str) -> bool:
    return department_code_from_citycode(citycode) in PACA_DEPARTMENTS


def department_name(department_code: str) -> str | None:
    return PACA_DEPARTMENTS.get(department_code)
