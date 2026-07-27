"""
Modèles de persistance pour le Property ID.

Ce fichier définit l'interface de stockage (protocol / classe abstraite)
et l'implémentation légère actuelle (JSON file-based).

Architecture évolutive :
  1. MVP actuel : storage JSON sur disque (PropertyIDFileStore).
  2. Étape suivante : implémenter un store SQLite avec la même interface.
  3. Production : store PostgreSQL via SQLAlchemy.

Chaque implémentation doit respecter le protocole PropertyIDStore
pour que le service (service.py) reste interchangeable.

Référence : `app/core/config.py` pour la logique de chemin absolu,
`app/digital_twin/contract.py` pour le pattern de contrat.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from app.property_id.schemas import PropertyID


class PropertyIDStore(ABC):
    """Contrat que tout store Property ID doit implémenter.

    Permet de remplacer le stockage fichier par SQLite/Postgres
    sans modifier le service (service.py).
    """

    @abstractmethod
    def save(self, pid: str, data: dict[str, Any]) -> None:
        """Persiste un Property ID."""

    @abstractmethod
    def load(self, pid: str) -> dict[str, Any] | None:
        """Charge un Property ID par son identifiant."""

    @abstractmethod
    def list_all(self, limit: int = 20) -> list[dict[str, Any]]:
        """Liste les Property IDs les plus récents."""

    @abstractmethod
    def count(self) -> int:
        """Nombre total de Property IDs stockés."""

    @abstractmethod
    def save_counter(self, value: int) -> None:
        """Persiste la valeur du compteur séquentiel."""

    @abstractmethod
    def load_counter(self) -> int:
        """Restaure la valeur du compteur séquentiel."""


class PropertyIDFileStore(PropertyIDStore):
    """Stockage Property ID en fichiers JSON.

    Structure :
      backend/data/property_ids/
        counter.json          -> {"counter": 42}
        TY-2026-000001.json   -> Property ID complet
        ...

    Cette implémentation est conçue pour être remplacée par un store
    plus robuste (SQLite, Postgres) sans impact sur le service.
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._counter_path = storage_dir / "counter.json"
        self._cache: dict[str, dict[str, Any]] = {}
        self.load_all_from_disk()

    def save(self, pid: str, data: dict[str, Any]) -> None:
        fpath = self.storage_dir / f"{pid}.json"
        fpath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        self._cache[pid] = data

    def load(self, pid: str) -> dict[str, Any] | None:
        fpath = self.storage_dir / f"{pid}.json"
        if not fpath.exists():
            return None
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            self._cache[pid] = data
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def list_all(self, limit: int = 20) -> list[dict[str, Any]]:
        all_items = sorted(
            self._cache.values(),
            key=lambda x: x.get("generated_at", ""),
            reverse=True,
        )
        return all_items[:limit]

    def count(self) -> int:
        return len(self._cache)

    def save_counter(self, value: int) -> None:
        self._counter_path.write_text(
            json.dumps({"counter": value}, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_counter(self) -> int:
        if not self._counter_path.exists():
            return 0
        try:
            data = json.loads(self._counter_path.read_text(encoding="utf-8"))
            return data.get("counter", 0)
        except (json.JSONDecodeError, OSError):
            return 0

    def load_all_from_disk(self) -> int:
        """Charge tous les Property IDs du disque dans le cache.
        Retourne le nombre chargé."""
        count = 0
        for fpath in self.storage_dir.glob("TY-*.json"):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                pid = data.get("property_id", fpath.stem)
                self._cache[pid] = data
                count += 1
            except (json.JSONDecodeError, OSError):
                pass
        return count
