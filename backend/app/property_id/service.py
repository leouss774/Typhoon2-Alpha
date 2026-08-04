"""
Service Property ID — orchestre la génération et la persistance.

Utilise PropertyIDFileStore (models.py) pour le stockage, avec une
interface (PropertyIDStore protocol) qui permet de remplacer
l'implémentation par SQLite/Postgres sans modifier ce module.

Voir models.py pour les détails de persistance.
"""

from __future__ import annotations

from typing import Any

from app.core.config import BASE_DIR
from app.core.logging import get_logger
from app.property_id.generator import _get_current_sequence, generate as _generate, set_sequence
from app.property_id.models import PropertyIDFileStore
from app.property_id.schemas import PropertyID

logger = get_logger(__name__)

STORAGE_DIR = BASE_DIR / "data" / "property_ids"
_store: PropertyIDFileStore | None = None


def _get_store() -> PropertyIDFileStore:
    """Retourne le store (initialisé au démarrage)."""
    if _store is None:
        msg = "Property ID store non initialisé — appeler init_service() au démarrage de l'application."
        raise RuntimeError(msg)
    return _store


def init_service() -> None:
    """Charge l'état depuis le disque au démarrage.

    À appeler depuis l'événement startup de FastAPI (cf. app/main.py).
    """
    global _store  # noqa: PLW0603
    _store = PropertyIDFileStore(STORAGE_DIR)
    counter = _store.load_counter()
    set_sequence(counter)
    count = _store.load_all_from_disk()
    logger.info(
        "property_id.service — initialisé : compteur=%d, %d Property ID(s) chargés",
        counter,
        count,
    )


def generate_property_id(
    building_data: dict[str, Any],
    risk_scores: dict[str, Any],
    digital_twin: dict[str, Any],
) -> PropertyID:
    """Génère un nouveau Property ID et le persiste.

    Paramètres
    ----------
    building_data : dict
        Sortie du collector_agent (adresse, bdnb, georisques, climat...).
    risk_scores : dict
        Sortie du scoring_agent (score_global, zones, projection_2050).
    digital_twin : dict
        Contrat final du digital_twin_agent.

    Retourne
    -------
    PropertyID
        Le Property ID généré et persisté.
    """
    store = _get_store()
    property_id = _generate(building_data, risk_scores, digital_twin)
    data = property_id.model_dump(mode="json")
    store.save(property_id.property_id, data)
    store.save_counter(_get_current_sequence())
    logger.info("property_id.service — %s sauvegardé (mémoire + disque)", property_id.property_id)
    return property_id


def get_property_id(pid: str) -> PropertyID | None:
    """Retourne un Property ID par son identifiant.

    Paramètres
    ----------
    pid : str
        L'identifiant unique (format "TY-YYYY-NNNNNN").

    Retourne
    -------
    PropertyID | None
        Le Property ID s'il existe, None sinon.
    """
    store = _get_store()
    data = store.load(pid)
    if data is None:
        return None
    return PropertyID(**data)


def list_property_ids(limit: int = 20) -> list[PropertyID]:
    """Liste les Property IDs les plus récents.

    Paramètres
    ----------
    limit : int
        Nombre maximum de résultats (défaut 20).

    Retourne
    -------
    list[PropertyID]
        Les Property IDs triés par date de génération (du plus récent).
    """
    store = _get_store()
    all_pids = store.list_all(limit)
    return [PropertyID(**d) for d in all_pids]
