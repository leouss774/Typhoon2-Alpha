"""
Lookup local DVF (Demandes de Valeurs Foncieres) : transactions immobilieres,
utilise pour donner du contexte de marche sur le bien (pas pour le scoring
de risque).

Contrairement aux connecteurs precedents, DVF n'est pas une API : c'est un
fichier a telecharger une bonne fois pour toutes puis a interroger en local
(voir docs/GUIDE_ORCHESTRATEUR_API.md pour la procedure de telechargement,
limitee aux 6 departements PACA pour ce sprint).

Format attendu ici : un CSV par departement, nomme "{departement}.csv",
place dans DVF_LOOKUP_DIR (ex. data/lookup/dvf/06.csv pour les
Alpes-Maritimes), issu du projet geo-dvf :
https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dept}.csv.gz
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.paca import department_code_from_citycode

_cache: dict[str, pd.DataFrame] = {}


class DvfLookupUnavailable(RuntimeError):
    pass


def _load_department_file(department_code: str) -> pd.DataFrame:
    if department_code in _cache:
        return _cache[department_code]

    path = Path(settings.dvf_lookup_dir) / f"{department_code}.csv"
    if not path.exists():
        raise DvfLookupUnavailable(
            f"Fichier DVF introuvable pour le departement {department_code} : {path}. "
            "Voir docs/GUIDE_ORCHESTRATEUR_API.md pour le telecharger."
        )

    df = pd.read_csv(path, low_memory=False)
    _cache[department_code] = df
    return df


def lookup_dvf(citycode: str, max_rows: int = 20) -> list[dict]:
    """Retourne les dernieres transactions DVF connues pour la commune."""
    department_code = department_code_from_citycode(citycode)
    df = _load_department_file(department_code)

    # Le nom de colonne commune varie selon les millesimes du fichier
    # geo-dvf ("code_commune" est le plus frequent).
    commune_col = next((c for c in ("code_commune", "codecommune", "insee") if c in df.columns), None)
    if commune_col is None:
        raise DvfLookupUnavailable(
            "Colonne de code commune introuvable dans le fichier DVF local. "
            f"Colonnes disponibles : {list(df.columns)[:15]}..."
        )

    subset = df[df[commune_col].astype(str) == str(citycode)]
    return subset.head(max_rows).to_dict(orient="records")
