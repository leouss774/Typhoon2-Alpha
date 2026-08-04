import csv
import os
from typing import Dict


def load_registry(path: str) -> Dict[str, dict]:
    """
    Charge le registre des sources (CSV) et retourne {fichier: row}.
    Retourne un dict vide si le fichier n'existe pas.
    """
    registry = {}
    if not os.path.exists(path):
        return registry
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            registry[row["fichier"]] = row
    return registry
