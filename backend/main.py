"""Point d'entrée de l'API Typhoon.

Utilise l'application configurée dans backend.api.main.

Lancement depuis la racine : uvicorn backend.main:app --reload
Lancement depuis backend/ : uvicorn main:app --reload
"""

import os
import sys

# Garantit que la racine du projet est dans sys.path
# (nécessaire pour "uvicorn main:app" lancé depuis backend/)
_racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _racine not in sys.path:
    sys.path.insert(0, _racine)

from backend.api.main import app

__all__ = ["app"]

