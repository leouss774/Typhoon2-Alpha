"""
analyses_store.py
------------------
Persistance SQLite pour le stockage des analyses.

Remplace le dict en mémoire par un stockage persistant :
- Base de données SQLite locale (data/analyses.db)
- Cache mémoire pour un accès rapide
- Thread-safe (verrouillage)
- Sauvegarde automatique à chaque écriture
- Compatible avec les formats legacy ET diagnostic

Utilisation :
    from services.analyses_store import store

    # Écrire
    store.save("session-abc", {"score_global": 65, ...})

    # Lire
    data = store.load("session-abc")

    # Lister
    all_ids = store.list_sessions()

    # Supprimer
    store.delete("session-abc")
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Chemin de la base ───────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "analyses.db")
LOCK = threading.Lock()


class AnalysesStore:
    """Store persistant pour les analyses, avec cache mémoire."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._cache: dict[str, dict[str, Any]] = {}
        self._init_db()

    # ── Initialisation ─────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Crée la table si elle n'existe pas."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_analyses_updated
                ON analyses(updated_at DESC)
            """)
            conn.commit()
        logger.info("AnalysesStore prêt : %s", self.db_path)

    # ── Opérations ─────────────────────────────────────────────────────

    def save(self, session_id: str, data: dict[str, Any]) -> None:
        """Sauvegarde ou met à jour une analyse.

        Thread-safe : verrou + écriture synchrone.
        """
        serialized = json.dumps(data, ensure_ascii=False, default=str)
        now = datetime.now(timezone.utc).isoformat()
        with LOCK, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analyses (session_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (session_id, serialized, now, now),
            )
            conn.commit()
        # Mettre à jour le cache mémoire
        self._cache[session_id] = data
        logger.debug("Analyse sauvegardée : %s", session_id[:16])

    def load(self, session_id: str) -> dict[str, Any] | None:
        """Charge une analyse.

        Vérifie d'abord le cache mémoire, puis la base SQLite.
        Retourne None si introuvable.
        """
        # Cache mémoire
        cached = self._cache.get(session_id)
        if cached is not None:
            return cached

        # Base SQLite
        with LOCK, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data FROM analyses WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        data: dict[str, Any] = json.loads(row[0])
        self._cache[session_id] = data  # populate cache
        return data

    def delete(self, session_id: str) -> bool:
        """Supprime une analyse. Retourne True si existante."""
        self._cache.pop(session_id, None)
        with LOCK, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM analyses WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_sessions(self) -> list[dict[str, str]]:
        """Liste toutes les sessions (id + date de mise à jour)."""
        with LOCK, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT session_id, updated_at FROM analyses ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        return [{"session_id": r[0], "updated_at": r[1]} for r in rows]

    def clear_all(self) -> int:
        """Supprime toutes les analyses. Retourne le nombre."""
        self._cache.clear()
        with LOCK, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM analyses")
            conn.commit()
            return cursor.rowcount

    def count(self) -> int:
        """Nombre d'analyses stockées."""
        with LOCK, sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()
        return row[0] if row else 0


# ── Instance singleton ──────────────────────────────────────────────────
store = AnalysesStore()

# Alias pour compatibilité
analyses_store: dict[str, dict[str, Any]] = {}  # cache mémoire partagé


def get_analysis(session_id: str) -> dict[str, Any] | None:
    """Interface de compatibilité : cherche d'abord dans le dict mémoire,
    puis dans le store SQLite."""
    data = analyses_store.get(session_id)
    if data is not None:
        return data
    return store.load(session_id)


def set_analysis(session_id: str, data: dict[str, Any]) -> None:
    """Interface de compatibilité : écrit dans le dict mémoire ET dans SQLite."""
    analyses_store[session_id] = data
    store.save(session_id, data)
