"""
Lookup local DRIAS : projections climatiques departementales (jours de
canicule, nuits tropicales, precipitations fortes, FWI — Fire Weather
Index...), correction de biais ADAMONT sur modeles CMIP6.

Meme logique que connectors/dvf_lookup.py : pas une API, un fichier local a
fournir une bonne fois pour toutes (voir settings.drias_lookup_path /
DRIAS_LOOKUP_PATH). Contrairement a DVF (un CSV par departement), DRIAS est
ici un seul fichier JSON cle par code departement :

    {
      "06": {"jours_canicule_2050": 42, "nuits_tropicales_2050": 18,
             "precip_fortes_jours_an": 6, "fwi_moyen": 12.4, ...},
      "83": {...}
    }

Utilise pour donner du CONTEXTE climatique departemental dans le rapport
zone_insurer (facteur pertinent pour la prime), pas pour le scoring de
risque batiment-par-batiment (qui reste sur climat_open_meteo, plus
localise). Desactive par defaut (settings.drias_enabled) tant que le
fichier n'est pas fourni sur un poste donne.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.core.paca import department_code_from_citycode

_cache: dict | None = None


class DriasLookupUnavailable(RuntimeError):
    pass


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    path = Path(settings.drias_lookup_path)
    if not path.exists():
        raise DriasLookupUnavailable(
            f"Fichier DRIAS introuvable : {path}. Voir le docstring de ce "
            "module pour le format attendu, ou desactive DRIAS_ENABLED."
        )
    with path.open(encoding="utf-8") as f:
        _cache = json.load(f)
    return _cache


def lookup_drias(citycode: str) -> dict | None:
    """Retourne les projections climatiques DRIAS pour le departement de la
    commune donnee, ou None si ce departement n'est pas dans le fichier."""
    department_code = department_code_from_citycode(citycode)
    data = _load()
    return data.get(department_code)
