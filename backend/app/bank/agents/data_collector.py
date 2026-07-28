"""Bank data aggregation wrapper.

This agent reuses the existing Typhoon collector instead of duplicating
BDNB, DVF, Georisques, climate and CATNAT connectors.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from app.agents.collector_agent import collect
from app.schemas.typhoon_bank import BankDataBundle, LoanData, TyphoonBankInput


class BankDataCollectorAgent:
    async def run(self, payload: TyphoonBankInput) -> BankDataBundle:
        try:
            building_data = await collect(payload.adresse)
        except Exception as exc:
            # Les sources publiques (geocodage, BDNB, Georisques, etc.) ne
            # doivent pas rendre l'API bancaire inutilisable. Le dashboard
            # peut continuer avec un calcul indicatif et expose l'erreur dans
            # building_data["erreurs"] pour permettre le diagnostic.
            building_data = _fallback_building_data(payload.adresse, exc)
        market_data = self._extract_market_data(building_data, payload)
        climate_data = {
            "georisques": building_data.get("georisques"),
            "open_meteo": building_data.get("climat_open_meteo"),
            "copernicus": building_data.get("climat_copernicus"),
            "catnat": (building_data.get("georisques") or {}).get("catnat"),
        }
        loan_data = LoanData(
            amount=payload.montant_credit,
            duration_years=payload.duree,
            max_ltv=payload.max_ltv,
            base_rate=payload.taux_base,
        )
        return BankDataBundle(
            building_data=building_data,
            climate_data=climate_data,
            market_data=market_data,
            loan_data=loan_data,
        )

    def _extract_market_data(self, building_data: dict[str, Any], payload: TyphoonBankInput) -> dict[str, Any]:
        if payload.prix_m2:
            return {
                "price_per_m2": payload.prix_m2,
                "price_source": "bank_input",
                "transactions_count": 0,
                "samples": [],
            }

        prices = []
        for row in building_data.get("dvf_local") or []:
            value = _first_number(row, ("valeur_fonciere", "valeurfonc", "valeur", "prix"))
            surface = _first_number(
                row,
                (
                    "surface_reelle_bati",
                    "surface_reelle",
                    "surface_bati",
                    "surface",
                    "sbati",
                ),
            )
            if value and surface and surface > 0:
                price_m2 = value / surface
                if 500 <= price_m2 <= 30000:
                    prices.append(price_m2)

        if prices:
            return {
                "price_per_m2": round(median(prices), 2),
                "price_source": "dvf_local_median",
                "transactions_count": len(prices),
                "samples": [round(p, 2) for p in prices[:8]],
            }

        return {
            "price_per_m2": _fallback_price_per_m2(building_data, payload),
            "price_source": "fallback_by_department_and_property_type",
            "transactions_count": 0,
            "samples": [],
        }


def _first_number(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name not in row:
            continue
        raw = row[name]
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = raw.replace(" ", "").replace(",", ".")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _fallback_price_per_m2(building_data: dict[str, Any], payload: TyphoonBankInput) -> float:
    department = str(building_data.get("departement") or "")
    by_department = {
        "06": 5200,
        "13": 4100,
        "83": 4300,
        "84": 2900,
        "04": 2400,
        "05": 2600,
    }
    base = by_department.get(department, 3200)
    if payload.type_bien == "appartement":
        base *= 1.08
    elif payload.type_bien == "terrain":
        base *= 0.35
    elif payload.type_bien == "immeuble":
        base *= 0.92
    return round(base, 2)


def _fallback_building_data(address: str, exc: Exception) -> dict[str, Any]:
    """Return a transparent offline-safe bundle when live APIs are unavailable."""
    postcode_match = re.search(r"\b(\d{5})\b", address)
    postcode = postcode_match.group(1) if postcode_match else ""
    department = postcode[:2] if postcode else ""
    return {
        "adresse": {
            "label": address,
            "citycode": "",
            "postcode": postcode,
            "city": "",
            "score_geocodage": 0.0,
            "lat": None,
            "lon": None,
        },
        "departement": department,
        "departement_nom": "",
        "dans_perimetre_paca": False,
        "altitude_m": None,
        "bdnb": None,
        "georisques": {"erreurs": ["Données live indisponibles"]},
        "climat_open_meteo": None,
        "climat_copernicus": None,
        "dvf_local": None,
        "erreurs": [
            {
                "source": "collector",
                "erreur": f"{type(exc).__name__}: {exc}",
                "mode": "fallback_indicatif",
            }
        ],
    }
