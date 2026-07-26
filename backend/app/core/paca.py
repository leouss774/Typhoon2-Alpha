"""
Perimetre geographique du MVP : region Provence-Alpes-Cote d'Azur (PACA).

Cf. docs/ROADMAP_MVP_PACA.md : ce perimetre ne s'applique qu'aux jeux de
donnees telecharges en local (DVF, DRIAS). Les API live (BDNB, Georisques,
IGN Altitude, Open-Meteo) fonctionnent pour n'importe quelle adresse
francaise ; ce module sert donc a :
  - documenter/valider que l'adresse testee est bien en PACA (pour rester
    dans le perimetre de demo du sprint),
  - determiner quel fichier local charger pour DVF/DRIAS (un fichier par
    departement).
"""

from __future__ import annotations

PACA_DEPARTMENTS: dict[str, str] = {
    "04": "Alpes-de-Haute-Provence",
    "05": "Hautes-Alpes",
    "06": "Alpes-Maritimes",
    "13": "Bouches-du-Rhone",
    "83": "Var",
    "84": "Vaucluse",
}


def department_code_from_citycode(citycode: str) -> str:
    """Deduit le code departement (2 chiffres) a partir d'un code INSEE commune.

    Ne gere pas les cas particuliers d'outre-mer (3 chiffres) : hors
    perimetre PACA, ce n'est pas necessaire pour ce sprint.
    """
    return citycode[:2]


def is_in_paca(citycode: str) -> bool:
    return department_code_from_citycode(citycode) in PACA_DEPARTMENTS


def department_name(department_code: str) -> str | None:
    return PACA_DEPARTMENTS.get(department_code)
