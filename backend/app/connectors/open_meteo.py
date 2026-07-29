"""
Projections climatiques (equivalent Copernicus/IPCC CMIP6) via l'Open-Meteo
Climate API.

Doc : https://open-meteo.com/en/docs/climate-api
Public, gratuit en usage non-commercial, sans cle. Donnees disponibles de
1950 a 2050 (au-dela, l'incertitude entre scenarios d'emission devient trop
grande, l'API s'arrete donc a 2050 - ce qui tombe bien pour nos besoins de
projection 2050 deja prevus dans le contrat jumeau numerique).

Pour rester rapide dans ce script de test, on ne demande que 2 modeles
climatiques (parmi les 7 disponibles) et 2 fenetres temporelles courtes
plutot que l'intervalle complet 1950-2050 recommande par la doc : une
fenetre "recente" (reference actuelle) et une fenetre "future" (horizon
2050). Le detail complet (7 modeles, 1950-2050) pourra etre active plus
tard dans scoring_agent si necessaire.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

# Modeles couvrant toutes les variables utilisees ici (temperature,
# precipitation, humidite) - voir tableau de compatibilite dans la doc.
_MODELS = ["EC_Earth3P_HR", "MRI_AGCM3_2_S"]
_DAILY_VARS = ["temperature_2m_max", "precipitation_sum"]

_BASELINE_WINDOW = ("2015-01-01", "2024-12-31")
_PROJECTION_WINDOW = ("2041-01-01", "2050-12-31")


@dataclass
class ClimatePeriodSummary:
    periode: str
    temperature_max_moyenne_c: float | None  # moyenne annuelle des max quotidiens
    temperature_max_absolue_c: float | None  # pic absolu sur toute la periode
    precipitation_annuelle_moyenne_mm: float | None
    jours_chaleur_extreme_par_an: float | None  # jours > 35 degC, moyenne annuelle


@dataclass
class ClimateSummary:
    reference_2015_2024: ClimatePeriodSummary
    projection_2041_2050: ClimatePeriodSummary
    modeles_utilises: list[str] = field(default_factory=lambda: list(_MODELS))


async def _fetch_daily(client: httpx.AsyncClient, lat: float, lon: float, start: str, end: str) -> dict:
    response = await client.get(
        settings.open_meteo_climate_url,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "models": ",".join(_MODELS),
            "daily": ",".join(_DAILY_VARS),
        },
    )
    response.raise_for_status()
    return response.json()


def _summarize(payload: dict, label: str) -> ClimatePeriodSummary:
    daily = payload.get("daily") or {}

    # Avec plusieurs modeles, Open-Meteo suffixe chaque variable par le nom
    # du modele (ex. "temperature_2m_max_EC_Earth3P_HR"). On moyenne toutes
    # les colonnes correspondantes, tous modeles confondus.
    temp_cols = [v for k, v in daily.items() if k.startswith("temperature_2m_max") and isinstance(v, list)]
    precip_cols = [v for k, v in daily.items() if k.startswith("precipitation_sum") and isinstance(v, list)]

    temp_values = [t for col in temp_cols for t in col if t is not None]
    precip_values = [p for col in precip_cols for p in col if p is not None]

    temp_moy = round(statistics.mean(temp_values), 1) if temp_values else None
    temp_max_abs = round(max(temp_values), 1) if temp_values else None
    jours_chaleur = None
    if temp_values:
        nb_annees = max(1, len(temp_values) / 365)
        jours_chaleur = round(sum(1 for t in temp_values if t >= 35) / nb_annees, 1)

    precip_annuelle = None
    if precip_values:
        nb_annees = max(1, len(precip_values) / 365)
        precip_annuelle = round(sum(precip_values) / nb_annees, 0)

    return ClimatePeriodSummary(
        periode=label,
        temperature_max_moyenne_c=temp_moy,
        temperature_max_absolue_c=temp_max_abs,
        precipitation_annuelle_moyenne_mm=precip_annuelle,
        jours_chaleur_extreme_par_an=jours_chaleur,
    )


async def fetch_climate_summary(client: httpx.AsyncClient, lat: float, lon: float) -> ClimateSummary:
    """Retourne un resume climatique reference (2015-2024) vs projection (2041-2050)."""
    baseline_payload = await _fetch_daily(client, lat, lon, *_BASELINE_WINDOW)
    projection_payload = await _fetch_daily(client, lat, lon, *_PROJECTION_WINDOW)

    return ClimateSummary(
        reference_2015_2024=_summarize(baseline_payload, "2015-2024"),
        projection_2041_2050=_summarize(projection_payload, "2041-2050"),
    )
