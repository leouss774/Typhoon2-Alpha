"""
Contrat canonique des variables du Risk Engine Typhon.

Toute donnee consommee par le moteur passe par CanonicalVariable. Un `null` brut
n'existe pas dans le moteur : il est toujours traduit vers un Status explicite.

Reference : PROMPT Phase 2 §5, PHASE1_AUDIT §2 (hierarchie des sources).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


SCHEMA_VERSION = "1.0.0"


class Status(str, Enum):
    """Statut d'une variable. Ces sept cas ne sont PAS interchangeables.

    En particulier SOURCE_ERROR ne doit jamais devenir NO_FEATURE_FOUND :
    une API en erreur ne prouve pas l'absence du phenomene.
    """

    AVAILABLE = "AVAILABLE"
    NO_FEATURE_FOUND = "NO_FEATURE_FOUND"   # requete OK, zero objet retourne
    SOURCE_ERROR = "SOURCE_ERROR"           # API en erreur (404, 429, 5xx...)
    NOT_CONFIGURED = "NOT_CONFIGURED"       # source non parametree (ex: .cdsapirc)
    NOT_COLLECTED = "NOT_COLLECTED"         # le collector ne demande pas ce champ
    NOT_APPLICABLE = "NOT_APPLICABLE"       # sans objet pour ce bien
    DEFAULT_VALUE = "DEFAULT_VALUE"         # fallback arbitraire -> EXCLU du calcul
    UNKNOWN = "UNKNOWN"                     # present mais valeur indeterminee
    USER_UNKNOWN = "USER_UNKNOWN"           # l'habitant a repondu "Je ne sais pas"


#: Seuls ces statuts autorisent l'usage de la valeur dans un score.
USABLE_STATUSES = frozenset({Status.AVAILABLE, Status.NO_FEATURE_FOUND})

#: Statuts qui signalent explicitement une defaillance technique (pas une absence).
ERROR_STATUSES = frozenset({Status.SOURCE_ERROR, Status.NOT_CONFIGURED})


class Scope(str, Enum):
    """Entite physique reellement decrite par la variable."""

    DWELLING = "dwelling"
    BUILDING = "building"
    BUILDING_GROUP = "building_group"
    PARCEL = "parcel"
    NEIGHBOURHOOD = "neighbourhood"
    COMMUNE = "commune"
    DEPARTMENT = "department"
    CLIMATE_GRID = "climate_grid"


class TimeHorizon(str, Enum):
    """Les donnees prospectives ne doivent JAMAIS entrer dans F, V ou R courants."""

    CURRENT = "current"
    HISTORICAL = "historical"
    PROSPECTIVE = "prospective"


#: Horizons admis dans le calcul du score courant.
CURRENT_HORIZONS = frozenset({TimeHorizon.CURRENT, TimeHorizon.HISTORICAL})


class Domain(str, Enum):
    HAZARD = "hazard"
    BUILDING = "building"


# --- Hierarchies de rang de source (1 = meilleur) -------------------------------

HAZARD_RANKS = {
    1: "mesure ou zonage officiel a la parcelle",
    2: "donnee locale reglementaire ou modele local detaille",
    3: "zonage officiel communal (ex. zonage sismique)",
    4: "maille climatique ou donnee departementale",
    5: "contexte communal ou proxy",
    6: "valeur par defaut (exclue du calcul)",
}

BUILDING_RANKS = {
    1: "document verifie, etude geotechnique, plans, diagnostic date",
    2: "observation directe fiable et recente de l'habitant",
    3: "declaration ou estimation de l'habitant",
    4: "BDNB ou inference publique",
    5: "inconnu",
}

#: Qualite de base par rang. Utilisee par le score de confiance, jamais par F/V.
_HAZARD_QUALITY = {1: 1.00, 2: 0.85, 3: 0.70, 4: 0.50, 5: 0.25, 6: 0.0}
_BUILDING_QUALITY = {1: 1.00, 2: 0.80, 3: 0.65, 4: 0.50, 5: 0.0}

#: Base de reponse declaree par l'habitant (PROMPT §6).
ANSWER_BASIS = ("observe", "document", "souvenir", "estimation", "inconnu")

#: Correspondance base de reponse -> rang bâtiment.
ANSWER_BASIS_RANK = {
    "document": 1,
    "observe": 2,
    "souvenir": 3,
    "estimation": 3,
    "inconnu": 5,
}


def rank_quality(domain: Domain, source_rank: int) -> float:
    table = _HAZARD_QUALITY if domain == Domain.HAZARD else _BUILDING_QUALITY
    return table.get(source_rank, 0.0)


@dataclass
class CanonicalVariable:
    """Une variable normalisee, avec toute sa tracabilite.

    `value` n'a de sens que si `status` appartient a USABLE_STATUSES.
    """

    key: str
    value: Any = None
    unit: Optional[str] = None
    status: Status = Status.UNKNOWN
    source: str = "unknown"
    raw_path: Optional[str] = None
    scope: Scope = Scope.BUILDING
    spatial_scale: Scope = Scope.BUILDING
    time_horizon: TimeHorizon = TimeHorizon.CURRENT
    observation_date: Optional[str] = None
    source_rank: int = 5
    domain: Domain = Domain.BUILDING
    quality: float = 0.0
    is_default: bool = False
    answer_basis: Optional[str] = None
    notes: Optional[str] = None
    #: Valeurs concurrentes ecartees par la hierarchie (conservees, jamais perdues).
    superseded: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.is_default:
            # Un fallback arbitraire n'est jamais une observation (D04).
            self.status = Status.DEFAULT_VALUE
        if self.quality == 0.0 and self.status in USABLE_STATUSES:
            self.quality = rank_quality(self.domain, self.source_rank)
        if self.status not in USABLE_STATUSES:
            self.quality = 0.0

    @property
    def usable(self) -> bool:
        """Utilisable dans un score : statut exploitable ET horizon non prospectif."""
        return (
            self.status in USABLE_STATUSES
            and not self.is_default
            and self.time_horizon in CURRENT_HORIZONS
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("status", "scope", "spatial_scale", "time_horizon", "domain"):
            d[k] = d[k].value if hasattr(d[k], "value") else d[k]
        d["superseded"] = [
            {kk: (vv.value if hasattr(vv, "value") else vv) for kk, vv in s.items()}
            for s in self.superseded
        ]
        return d


class VariableBag:
    """Collection indexee par cle canonique, avec resolution de conflit integree."""

    def __init__(self) -> None:
        self._vars: dict[str, CanonicalVariable] = {}
        self.conflicts: list[dict] = []

    def add(self, var: CanonicalVariable) -> None:
        """Ajoute une variable en respectant la hierarchie de rang.

        Une source de rang inferieur n'ecrase jamais une source de rang superieur.
        La valeur ecartee est conservee dans `superseded` et, si les valeurs
        different reellement, un conflit est enregistre.
        """
        existing = self._vars.get(var.key)
        if existing is None:
            self._vars[var.key] = var
            return

        keep, drop = (existing, var)
        # Rang plus petit = meilleur. A rang egal, une valeur utilisable prime.
        if (var.source_rank, not var.usable) < (existing.source_rank, not existing.usable):
            keep, drop = var, existing

        if keep.usable and drop.usable and _differs(keep.value, drop.value):
            self.conflicts.append(
                {
                    "key": var.key,
                    "kept": {"value": keep.value, "source": keep.source,
                             "source_rank": keep.source_rank},
                    "dropped": {"value": drop.value, "source": drop.source,
                                "source_rank": drop.source_rank},
                }
            )
        keep.superseded = keep.superseded + [
            {"value": drop.value, "source": drop.source,
             "source_rank": drop.source_rank, "status": drop.status}
        ]
        self._vars[var.key] = keep

    def get(self, key: str) -> Optional[CanonicalVariable]:
        return self._vars.get(key)

    def status_of(self, key: str) -> Status:
        v = self._vars.get(key)
        return v.status if v else Status.NOT_COLLECTED

    def __contains__(self, key: str) -> bool:
        return key in self._vars

    def __len__(self) -> int:
        return len(self._vars)

    def keys(self):
        return sorted(self._vars.keys())

    def values(self):
        return [self._vars[k] for k in self.keys()]

    def to_dict(self) -> dict:
        return {k: self._vars[k].to_dict() for k in self.keys()}


def _differs(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) > 1e-9
    return a != b
