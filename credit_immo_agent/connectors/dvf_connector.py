"""
Connecteur DVF (Demandes de Valeurs Foncières).

Utilise l'API communautaire maintenue par Christian Quest (Etalab) :
    http://api.cquest.org/dvf

ATTENTION - à savoir avant d'utiliser ce connecteur en production :
- C'est une API communautaire, pas un service officiel garanti par l'État.
  Sa disponibilité n'est pas contractuelle (voir README du projet cquest/dvf_as_api
  sur GitHub). Pour un usage bancaire réel, envisagez d'héberger votre propre
  instance à partir des données brutes DVF (data.gouv.fr) plutôt que de
  dépendre de l'instance publique de démonstration.
- Aucune authentification n'est requise, mais aucun SLA n'est garanti non plus.
- Résultats limités à ~1000 entrées par requête, sans pagination officielle.

Endpoints réels utilisés :
    http://api.cquest.org/dvf?lat={lat}&lon={lon}&dist={dist_metres}
    http://api.cquest.org/dvf?code_commune={code_insee}
"""

import json
import statistics
import urllib.request
import urllib.parse
from typing import Optional, List, Dict

BASE_URL = "http://api.cquest.org/dvf"
TIMEOUT_SECONDES = 10


class DVFIndisponible(Exception):
    """Levée quand l'API DVF ne répond pas ou renvoie une erreur."""


def _appeler_api(params: Dict[str, str]) -> List[dict]:
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDES) as reponse:
            data = json.loads(reponse.read().decode("utf-8"))
    except Exception as e:
        raise DVFIndisponible(f"Échec de l'appel à l'API DVF ({url}) : {e}") from e

    # L'API renvoie soit une liste brute, soit un GeoJSON avec "features"
    if isinstance(data, dict) and "features" in data:
        return [f["properties"] for f in data["features"]]
    if isinstance(data, list):
        return data
    raise DVFIndisponible(f"Format de réponse DVF inattendu : {type(data)}")


def prix_m2_median(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    dist_metres: int = 500,
    code_commune: Optional[str] = None,
    type_local: str = "Appartement",
) -> Optional[float]:
    """
    Retourne le prix médian au m² constaté sur les transactions DVF disponibles,
    filtrées par rayon géographique (lat/lon/dist) ou par commune (code_commune).

    Retourne None si aucune transaction exploitable n'est trouvée (à distinguer
    d'une erreur d'API, qui lève DVFIndisponible).
    """
    if code_commune:
        params = {"code_commune": code_commune}
    elif lat is not None and lon is not None:
        params = {"lat": str(lat), "lon": str(lon), "dist": str(dist_metres)}
    else:
        raise ValueError("Fournir soit (lat, lon), soit code_commune.")

    transactions = _appeler_api(params)

    prix_m2 = []
    for t in transactions:
        try:
            if t.get("type_local") != type_local:
                continue
            surface = float(t.get("surface_relle_bati") or t.get("surface_reelle_bati") or 0)
            valeur = float(t.get("valeur_fonciere") or 0)
            if surface > 0 and valeur > 0:
                prix_m2.append(valeur / surface)
        except (TypeError, ValueError):
            continue

    if not prix_m2:
        return None

    return round(statistics.median(prix_m2), 2)


def indice_evolution(
    prix_m2_reference: float,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    dist_metres: int = 500,
    code_commune: Optional[str] = None,
) -> Optional[float]:
    """
    Compare le prix médian actuel au prix de référence fourni (par exemple
    celui utilisé lors de l'octroi du crédit) et retourne un ratio :
    > 1.0 = le marché a monté, < 1.0 = le marché a baissé.

    Retourne None si aucune donnée actuelle n'est disponible.
    """
    prix_actuel = prix_m2_median(lat=lat, lon=lon, dist_metres=dist_metres, code_commune=code_commune)
    if prix_actuel is None or prix_m2_reference <= 0:
        return None
    return round(prix_actuel / prix_m2_reference, 4)
