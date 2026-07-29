"""Données climatiques via Open-Meteo Climate API.

https://climate-api.open-meteo.com/v1/climate
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from app.core.config import settings


@dataclass
class PeriodeClimat:
    temperature_max_moyenne_c: float | None = None
    temperature_max_absolue_c: float | None = None
    precipitation_annuelle_moyenne_mm: float | None = None
    jours_chaleur_extreme_par_an: float | None = None


@dataclass
class ClimateSummary:
    modeles_utilises: list[str]
    reference_2015_2024: PeriodeClimat
    projection_2041_2050: PeriodeClimat


async def fetch_climate_summary(client: httpx.AsyncClient, lat: float, lon: float) -> ClimateSummary | None:
    """Récupère un résumé climatique (référence + projection 2050)."""
    try:
        response = await client.get(
            settings.open_meteo_climate_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_mean,precipitation_sum",
                "start_date": "2015-01-01",
                "end_date": "2050-12-31",
                "models": "EC_Earth3P_HR,MPI_ESM1_2_HR",
            },
        )
        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})
        times = daily.get("time", [])

        ref_temps = [t for t in times if t < "2025-01-01"]
        proj_temps = [t for t in times if t >= "2041-01-01"]

        def _stats(temps_list):
            if not temps_list:
                return PeriodeClimat()
            max_temps = []
            precip = []
            for i, t in enumerate(times):
                if t in temps_list:
                    v = daily.get("temperature_2m_max", [])
                    if i < len(v) and v[i] is not None:
                        max_temps.append(float(v[i]))
                    p = daily.get("precipitation_sum", [])
                    if i < len(p) and p[i] is not None:
                        precip.append(float(p[i]))
            if not max_temps:
                return PeriodeClimat()
            return PeriodeClimat(
                temperature_max_moyenne_c=round(sum(max_temps) / len(max_temps), 1),
                temperature_max_absolue_c=round(max(max_temps), 1),
                precipitation_annuelle_moyenne_mm=round(sum(precip) / max(len(precip), 1), 1) if precip else None,
                jours_chaleur_extreme_par_an=round(sum(1 for t in max_temps if t >= 35) / max(len(temps_list) / 365, 1), 1),
            )

        return ClimateSummary(
            modeles_utilises=data.get("models", []),
            reference_2015_2024=_stats(ref_temps),
            projection_2041_2050=_stats(proj_temps),
        )

    except httpx.HTTPError:
        return None
