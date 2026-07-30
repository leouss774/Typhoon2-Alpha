# -*- coding: utf-8 -*-
"""
Cache mémoire simple avec TTL pour les appels API externes (ADEME, recherche entreprises).
Évite de ratelimit les APIs et accélère les recherches répétées sur un même code postal.
"""

from __future__ import annotations

import time
import threading
from collections import OrderedDict


class TTLCache:
    """Cache thread-safe avec TTL et éviction LRU."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 300):
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def _is_expired(self, timestamp: float) -> bool:
        return (time.monotonic() - timestamp) > self._ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._store:
                return None
            ts, value = self._store[key]
            if self._is_expired(ts):
                del self._store[key]
                return None
            # Move to end (most recently used)
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self._maxsize:
                self._store.popitem(last=False)  # LRU eviction
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ── Singletons partagés ────────────────────────────────────

# Cache pour l'API ADEME (liste des entreprises RGE)
# Clé : "{code_postal}|{domaine}"
# TTL : 10 minutes (la liste change rarement)
rge_cache = TTLCache(maxsize=512, ttl_seconds=600)

# Cache pour l'API Recherche d'Entreprises
# Clé : "{code_postal}|{code_naf}"
# TTL : 30 minutes (données SIREN stables)
entreprise_cache = TTLCache(maxsize=512, ttl_seconds=1800)

