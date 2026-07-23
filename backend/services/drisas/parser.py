"""Parseur des données climatiques DRIAS.

DRIAS (Données Climatiques Régionalisées) fournit des projections
climatiques à l'échelle communale pour la France.
Format : NetCDF, CSV ou JSON selon la source.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)


class DriasParser:
    """Parse et transforme les données DRIAS en indicateurs exploitables."""

    def __init__(self, data_path: str | None = None):
        settings = get_settings()
        self.data_path = Path(data_path or settings.DRIAS_DATA_PATH)

    def charger_projections_communales(
        self, code_insee: str, horizon: str = "2050"
    ) -> dict[str, Any]:
        """Charge les projections climatiques pour une commune.

        Args:
            code_insee: Code INSEE de la commune.
            horizon: Horizon temporel (2025, 2050, 2100).

        Returns:
            Dict avec les indicateurs climatiques projetés.
        """
        fichier = self.data_path / f"projections_{code_insee}.json"
        if not fichier.exists():
            logger.warning(f"Fichier DRIAS non trouvé : {fichier}")
            return self._projections_default(code_insee, horizon)

        with open(fichier, encoding="utf-8") as f:
            data = json.load(f)

        return data.get(horizon, data.get("2050", {}))

    def _projections_default(self, code_insee: str, horizon: str) -> dict:
        """Retourne des projections par défaut simulées."""
        # TODO: Remplacer par un vrai chargement DRIAS
        facteur = {"2025": 1.0, "2050": 1.3, "2100": 1.8}.get(horizon, 1.0)
        return {
            "horizon": horizon,
            "temperature_moyenne_deg": round(12.5 + (facteur - 1.0) * 3, 1),
            "jours_canicule": round(15 * facteur),
            "precipitations_intenses_pct": round(10 * (facteur - 0.8) * 100),
            "secheresse_sols_pct": round(25 * facteur),
            "vent_max_kmh": round(100 * (1 + (facteur - 1.0) * 0.3)),
        }

    def charger_csv(self, chemin: str) -> list[dict]:
        """Charge un fichier CSV DRIAS."""
        fichier = self.data_path / chemin
        if not fichier.exists():
            return []

        with open(fichier, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
