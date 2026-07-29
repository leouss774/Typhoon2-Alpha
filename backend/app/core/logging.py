"""
Configuration du logging serveur.

Objectif explicite (demande utilisateur) : pouvoir suivre en clair, dans la
console du serveur, le fil des agents pour un diagnostic donne - collecte,
scoring, assemblage du jumeau numerique - avec le temps pris par chacun.
Chaque agent appelle `get_logger(__name__)` et logue ses etapes en INFO ;
les details de debogage (payloads bruts, etc.) restent en DEBUG pour ne pas
noyer la trace principale.

Format volontairement simple (pas de JSON structure) : c'est fait pour etre
lu a l'oeil dans un terminal pendant une demo / un test manuel, pas pour
etre parse par un collecteur de logs.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-7s %(name)-32s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Les librairies HTTP sont tres verbeuses en DEBUG/INFO : on les laisse
    # tranquilles pour que la trace des agents Typhoon reste lisible.
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
