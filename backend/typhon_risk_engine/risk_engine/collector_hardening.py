"""
Durcissement minimal du collector : correctifs et adaptateurs OPTIONNELS.

Aucune fonction de ce module ne fabrique de valeur. Les adaptateurs reseau sont
inertes par defaut et testables via fixtures, sans acces reseau.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .canonical import Status

# --- 1. Inventaire automatique des champs d'un JSON reel --------------------------


def inventory(payload: Any, prefix: str = "", out: Optional[dict] = None) -> dict:
    """Aplatit un JSON en {chemin: type} pour comparer promesse et realite."""
    out = {} if out is None else out
    if isinstance(payload, dict):
        for k, v in payload.items():
            inventory(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(payload, list):
        out[f"{prefix}[]"] = f"list[{len(payload)}]"
        if payload:
            inventory(payload[0], f"{prefix}[0]", out)
    else:
        out[prefix] = type(payload).__name__
    return out


def availability_report(payload: dict, expected: dict[str, list[str]]) -> dict:
    """Rapport de disponibilite par source et par variable.

    `expected` : {source: [chemins attendus]}. Ne suppose jamais qu'un champ est
    disponible parce qu'il figure au data dictionary.
    """
    inv = inventory(payload)
    report = {}
    for source, paths in sorted(expected.items()):
        present = [p for p in paths if p in inv]
        absent = [p for p in paths if p not in inv]
        report[source] = {
            "expected": len(paths),
            "present": sorted(present),
            "absent": sorted(absent),
            "coverage": round(len(present) / len(paths), 4) if paths else 0.0,
        }
    return report


#: Ce que le data dictionary annonce, a confronter au JSON reel.
DATA_DICTIONARY_PROMISES = {
    "open_meteo_daily": [
        "climat_open_meteo.daily.temperature_2m_min",
        "climat_open_meteo.daily.temperature_2m_max",
        "climat_open_meteo.daily.wind_speed_10m_max",
        "climat_open_meteo.daily.relative_humidity_2m_mean",
        "climat_open_meteo.daily.soil_moisture_0_to_10cm_mean",
        "climat_open_meteo.daily.precipitation_sum",
    ],
    "wfs_distances": [
        "distanceToWaterway", "distanceToForest", "distanceFireStation",
    ],
    "georisques": [
        "georisques.zonage_sismique.data[0].code_zone",
        "georisques.cavites.results",
        "georisques.mouvements_de_terrain.results",
        "georisques.zones_inondables",
    ],
    "bdnb": [
        "bdnb.batiment.alea_argile",
        "bdnb.batiment.annee_construction",
        "bdnb.batiment.materiaux_structure_mur_exterieur",
    ],
}


# --- 2. Semantique des variables Open-Meteo ----------------------------------------

#: Le collector observe ne demande que ces deux variables journalieres.
OBSERVED_DAILY_VARS = ("temperature_2m_max", "precipitation_sum")

#: Variables a ajouter au parametre `daily` pour debloquer P05, P09 et P11.
RECOMMENDED_DAILY_ADDITIONS = (
    "temperature_2m_min",            # jours de gel -> P11
    "wind_speed_10m_max",            # statistiques de vent -> P05
    "relative_humidity_2m_mean",     # FWI Van Wagner -> P09
    "soil_moisture_0_to_10cm_mean",  # secheresse -> P02, P09
)

VARIABLE_SEMANTICS = {
    "wind_speed_10m_max": {
        "meaning": "vitesse de vent maximale a 10 m",
        "is_gust": False,
        "warning": "NE PAS nommer 'rafale'. Une rafale est une pointe sur quelques "
                   "secondes ; cette variable est un maximum de vitesse moyenne.",
    },
    "temperature_2m_max": {"meaning": "temperature maximale a 2 m", "is_gust": False},
    "precipitation_sum": {"meaning": "cumul de precipitations", "is_gust": False},
}


def check_wind_semantics(var_name: str) -> dict:
    """Refuse d'etiqueter 'rafale' une variable qui n'en est pas une."""
    info = VARIABLE_SEMANTICS.get(var_name)
    if info is None:
        return {"known": False,
                "warning": f"semantique de `{var_name}` non verifiee ; ne pas "
                           f"l'utiliser avant documentation"}
    return {"known": True, **info}


# --- 3. FWI : conditions de calculabilite --------------------------------------------

FWI_REQUIRED_INPUTS = (
    "temperature", "relative_humidity", "wind_speed", "precipitation",
)


def fwi_computable(available_inputs: set[str]) -> dict:
    """Le FWI de Van Wagner n'est calcule QUE si toutes ses conditions sont reunies.

    Au-dela des variables, le modele est recursif et exige une convention horaire
    (observation de milieu d'apres-midi), l'initialisation de FFMC/DMC/DC et un
    traitement documente des jours manquants.
    """
    missing = sorted(set(FWI_REQUIRED_INPUTS) - set(available_inputs))
    conditions = {
        "all_inputs_present": not missing,
        "hourly_convention_documented": False,
        "ffmc_dmc_dc_initialised": False,
        "missing_days_policy_defined": False,
    }
    computable = all(conditions.values())
    return {
        "computable": computable,
        "missing_inputs": missing,
        "conditions": conditions,
        "decision": (
            "FWI calcule" if computable else
            "FWI NON calcule. Aucun `historical_fwi_proxy` n'entre dans F : un tel "
            "champ ne peut exister qu'en experimentation separee, explicitement "
            "non validee et de poids nul."
        ),
    }


# --- 4. Distinction erreur / absence / non-collecte -------------------------------------


def classify_source(payload_node: Any, error_message: Optional[str] = None,
                    configured: bool = True, requested: bool = True) -> Status:
    """Quatre situations distinctes, jamais confondues."""
    if not configured:
        return Status.NOT_CONFIGURED
    if error_message:
        return Status.SOURCE_ERROR
    if not requested:
        return Status.NOT_COLLECTED
    if payload_node is None:
        return Status.NOT_COLLECTED
    if isinstance(payload_node, dict) and payload_node.get("results") == 0:
        return Status.NO_FEATURE_FOUND
    return Status.AVAILABLE


# --- 5. Pagination CatNat -----------------------------------------------------------------


def paginate(fetch_page: Callable[[int], dict], max_pages: int = 50) -> dict:
    """Pagine integralement une ressource Georisques.

    `fetch_page(n)` doit renvoyer le corps JSON de la page n. Aucune requete
    reseau n'est faite ici : l'appelant fournit le callable, ce qui rend la
    fonction testable avec des fixtures.
    """
    first = fetch_page(1)
    data = list(first.get("data") or [])
    total_pages = int(first.get("total_pages") or 1)
    announced = first.get("results")
    for page in range(2, min(total_pages, max_pages) + 1):
        body = fetch_page(page)
        data.extend(body.get("data") or [])
    complete = (announced is None) or (len(data) >= announced)
    return {
        "data": data, "records": len(data), "announced": announced,
        "total_pages": total_pages, "pagination_complete": complete,
        "warning": None if complete else
        f"pagination incomplete : {len(data)}/{announced}",
    }


# --- 6. Politique de reprise pour Open-Meteo (429) -------------------------------------------


@dataclass
class RetryPolicy:
    """Backoff exponentiel avec jitter, respect explicite des reponses 429."""

    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.25
    seed: Optional[int] = None

    def delay_for(self, attempt: int, retry_after: Optional[float] = None) -> float:
        if retry_after is not None:
            return min(float(retry_after), self.max_delay)
        raw = min(self.base_delay * (2 ** max(0, attempt - 1)), self.max_delay)
        rng = random.Random(self.seed if self.seed is not None else attempt)
        return raw * (1.0 + rng.uniform(-self.jitter, self.jitter))


@dataclass
class ClimateCache:
    """Cache par maille climatique : une adresse n'est pas une maille.

    Arrondir les coordonnees a la resolution du modele evite de rappeler l'API
    pour chaque bien d'un meme quartier — cause directe du 429 observe.
    """

    resolution_deg: float = 0.25
    _store: dict = field(default_factory=dict)

    def cell(self, lat: float, lon: float) -> tuple[float, float]:
        r = self.resolution_deg
        return (round(lat / r) * r, round(lon / r) * r)

    def get(self, lat: float, lon: float):
        return self._store.get(self.cell(lat, lon))

    def set(self, lat: float, lon: float, value: Any) -> None:
        self._store[self.cell(lat, lon)] = value

    def __len__(self) -> int:
        return len(self._store)


@dataclass
class ConcurrencyLimiter:
    """Limitation de concurrence simple, deterministe et testable."""

    max_concurrent: int = 2
    _in_flight: int = 0

    def acquire(self) -> bool:
        if self._in_flight >= self.max_concurrent:
            return False
        self._in_flight += 1
        return True

    def release(self) -> None:
        self._in_flight = max(0, self._in_flight - 1)


# --- 7. Validation prealable de la configuration Copernicus ------------------------------------


def check_copernicus_config(cdsapirc_path: Optional[str], contents: Optional[str] = None) -> dict:
    """Valide la config CDS avant toute tentative d'appel."""
    if not cdsapirc_path:
        return {"status": Status.NOT_CONFIGURED.value,
                "reason": "chemin .cdsapirc non fourni"}
    if contents is None:
        return {"status": Status.NOT_CONFIGURED.value,
                "reason": f"fichier introuvable ou illisible : {cdsapirc_path}"}
    has_url = "url:" in contents
    has_key = "key:" in contents
    if not (has_url and has_key):
        return {"status": Status.NOT_CONFIGURED.value,
                "reason": "fichier incomplet : `url:` et `key:` sont requis"}
    return {"status": "CONFIGURED", "reason": None}


# --- 8. Endpoint AZI en 404 --------------------------------------------------------------------


AZI_POLICY = {
    "endpoint": "georisques.gouv.fr/api/v1/azi",
    "observed": "404 Not Found sur code_insee=06088",
    "status_to_emit": Status.SOURCE_ERROR.value,
    "forbidden_interpretation": "aucune zone inondable",
    "action": ("desactiver explicitement l'endpoint dans la config du collector "
               "ou le remplacer par une source de zonage PPRI geolocalisee ; dans "
               "les deux cas le statut reste SOURCE_ERROR, jamais NO_FEATURE_FOUND"),
}


#: Metadonnees de requete a enregistrer pour cavites et mouvements de terrain.
SPATIAL_QUERY_METADATA_TEMPLATE = {
    "radius_m": None,
    "filters": None,
    "database_coverage": None,
    "note": ("results=0 signifie 'aucun objet retourne dans ce rayon et selon la "
             "couverture de cette base', jamais 'risque nul'. Rayon et couverture "
             "doivent etre journalises avec la reponse."),
}
