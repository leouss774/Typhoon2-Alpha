"""Configuration du logging serveur.

Objectif : pouvoir suivre en clair, dans la console du serveur, le fil des
agents pour un diagnostic donné - collecte, scoring, assemblage du jumeau
numérique - avec le temps pris par chacun.
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

    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
