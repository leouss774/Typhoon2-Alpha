"""Deterministic extraction from the Collecteur payload to ProfilRisqueCondense.

The extractor is intentionally strict about traceability and permissive about
missing or partially populated blocks. It only transforms the raw JSON into a
normalized, auditable structure; it does not score anything.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import re
from typing import Any, Iterable

from schema_profil_risque import (
    DonneesTopo,
    EauxSouterraines,
    ExpositionArgiles,
    FacilitesProches,
    CavitesPotentielles,
    HistoriqueEvts,
    EvenementHistorique,
    ProfilRisqueCondense,
    ProxyClimatique,
    RadonPotentiel,
    RisqueNaturel,
    ZoneSismique,
)

DEFAULT_MISSING_BLOCKS = (
    "drias_meteofrance",
    "copernicus",
    "sentinel",
    "insee",
    "brgm_geologie_avancee",
    "onrn",
)

RISK_KEY_MAP = {
    "inondation": "inondation",
    "remonteeNappe": "remontee_nappe",
    "risqueCotier": "risque_cotier",
    "seisme": "seisme",
    "mouvementTerrain": "mouvement_terrain",
    "reculTraitCote": "recul_trait_cote",
    "retraitGonflementArgile": "retrait_gonflement_argile",
    "avalanche": "avalanche",
    "feuForet": "feu_foret",
    "eruptionVolcanique": "eruption_volcanique",
    "cyclone": "cyclone",
    "radon": "radon",
}


def extract_profil_risque_condense(payload: dict[str, Any]) -> ProfilRisqueCondense:
    """Normalize a raw Collecteur payload into a condensed risk profile."""
    geo = _as_dict(payload.get("georisques"))
    ign = _as_dict(payload.get("ign"))
    hubeau = _as_dict(payload.get("hubeau"))
    rapport_risque = _as_dict(geo.get("rapport_risque"))
    risques_naturels_raw = _as_dict(rapport_risque.get("risquesNaturels"))
    risques_technologiques_raw = _as_dict(rapport_risque.get("risquesTechnologiques"))

    coordonnees = _as_dict(payload.get("coordonnees"))
    latitude = _coerce_float(coordonnees.get("latitude"))
    longitude = _coerce_float(coordonnees.get("longitude"))
    geocodage_score = _coerce_float(payload.get("score_geocodage"), default=0.0)

    profil = ProfilRisqueCondense(
        adresse=str(payload.get("adresse", "") or ""),
        code_insee=str(payload.get("code_insee", "") or ""),
        coordonnees_lat=latitude if latitude is not None else 0.0,
        coordonnees_lon=longitude if longitude is not None else 0.0,
        geocodage_score=geocodage_score if geocodage_score is not None else 0.0,
        risques_naturels=_extract_risques_naturels(risques_naturels_raw),
        rga=_extract_rga(geo.get("argiles_rga")),
        zone_sismique=_extract_zone_sismique(geo.get("zonage_sismique")),
        radon=_extract_radon(geo.get("radon")),
        cavites=_extract_cavites(geo.get("cavites")),
        historique_evts=_extract_catnat(geo.get("catnat")),
        facilites_proches=_extract_facilites_proches(geo, risques_technologiques_raw),
        donnees_topo=_extract_topographie(ign),
        proxy_climatique=derive_proxy_climatique(latitude),
        eaux_souterraines=_extract_eaux_souterraines(hubeau),
        donnees_manquantes=_list_missing_blocks(payload),
    )
    return profil


def derive_proxy_climatique(latitude: float | None) -> ProxyClimatique:
    """Derive a simple, auditable climate proxy from latitude bands.

    V1 thresholds are intentionally simple and deterministic:
    - latitude < 43.5 => tres_chaud
    - 43.5 <= latitude < 45.5 => chaud
    - 45.5 <= latitude < 48.5 => intermediaire
    - latitude >= 48.5 => froid
    """
    thresholds = {
        "tres_chaud_max": 43.5,
        "chaud_max": 45.5,
        "intermediaire_max": 48.5,
    }
    if latitude is None:
        return ProxyClimatique(
            code=None,
            source="latitude_band_v1",
            libelle_source="latitude_band_v1",
            latitude=None,
            seuils=thresholds,
            disponible=False,
        )

    if latitude < thresholds["tres_chaud_max"]:
        code = "tres_chaud"
    elif latitude < thresholds["chaud_max"]:
        code = "chaud"
    elif latitude < thresholds["intermediaire_max"]:
        code = "intermediaire"
    else:
        code = "froid"

    return ProxyClimatique(
        code=code,
        source="latitude_band_v1",
        libelle_source="latitude_band_v1",
        latitude=latitude,
        seuils=thresholds,
        disponible=True,
    )


def _extract_risques_naturels(raw: dict[str, Any]) -> dict[str, RisqueNaturel]:
    result: dict[str, RisqueNaturel] = {}
    for source_key, internal_code in RISK_KEY_MAP.items():
        item = _as_dict(raw.get(source_key))
        present = bool(item.get("present")) if item else False
        result[internal_code] = RisqueNaturel(
            code=internal_code,
            present=present,
            libelle_source=source_key,
            statut_adresse=item.get("libelleStatutAdresse") if item else None,
            statut_commune=item.get("libelleStatutCommune") if item else None,
            disponible=bool(item),
            notes=item.get("specifique") if item else None,
        )
    return result


def _extract_rga(raw: Any) -> ExpositionArgiles:
    item = _first_item(raw)
    if not item:
        return ExpositionArgiles(present=False, disponible=False, libelle_source="argiles_rga")

    exposition = _normalize_rga_exposition(item.get("exposition"))
    code_exposition = item.get("codeExposition")
    return ExpositionArgiles(
        present=True,
        exposition=exposition,
        code_exposition=str(code_exposition) if code_exposition is not None else None,
        libelle_source="argiles_rga",
        disponible=True,
    )


def _extract_zone_sismique(raw: Any) -> ZoneSismique:
    item = _first_item(raw)
    if not item:
        return ZoneSismique(present=False, disponible=False, libelle_source="zonage_sismique")

    return ZoneSismique(
        present=True,
        zone_code=str(item.get("code_zone")) if item.get("code_zone") is not None else None,
        zone_libelle=item.get("zone_sismicite"),
        libelle_source="zonage_sismique",
        disponible=True,
    )


def _extract_radon(raw: Any) -> RadonPotentiel:
    item = _first_item(raw)
    if not item:
        return RadonPotentiel(present=False, disponible=False, libelle_source="radon")

    return RadonPotentiel(
        present=True,
        classe_potentiel=str(item.get("classe_potentiel")) if item.get("classe_potentiel") is not None else None,
        libelle_source="radon",
        disponible=True,
    )


def _extract_cavites(raw: Any) -> CavitesPotentielles:
    entries = raw if isinstance(raw, list) else []
    count = len(entries)
    if count == 0:
        return CavitesPotentielles(present=False, count=0, libelle_source="cavites", disponible=False)

    return CavitesPotentielles(present=True, count=count, libelle_source="cavites", disponible=True)


def _extract_catnat(raw: Any) -> HistoriqueEvts:
    entries = raw if isinstance(raw, list) else []
    unique_events: dict[tuple[str, str], EvenementHistorique] = {}
    now = datetime.now(UTC)

    for entry in entries:
        item = _as_dict(entry)
        code_national = str(item.get("code_national_catnat") or "").strip()
        libelle_risque = str(item.get("libelle_risque_jo") or "").strip()
        if not code_national or not libelle_risque:
            continue

        date_debut = _parse_date(item.get("date_debut_evt"))
        date_fin = _parse_date(item.get("date_fin_evt")) or date_debut
        date_publi = _parse_date(item.get("date_publication_jo")) or date_fin or date_debut
        if date_debut is None:
            continue

        internal_type = _normalize_catnat_type(libelle_risque)
        key = (code_national, internal_type)
        event = EvenementHistorique(
            code_national=code_national,
            type_risque=internal_type,
            date_debut=date_debut,
            date_fin=date_fin or date_debut,
            date_publication_jo=date_publi or date_debut,
        )
        event.jours_depuis_evt = _days_since(event.date_debut, now)
        event.jours_depuis_publi = _days_since(event.date_publication_jo, now)
        unique_events[key] = event

    events = sorted(unique_events.values(), key=lambda evt: evt.date_debut, reverse=True)
    counts: dict[str, int] = {}
    nb_evt_10ans = 0
    ten_years_ago = now - timedelta(days=3652)
    for evt in events:
        counts[evt.type_risque] = counts.get(evt.type_risque, 0) + 1
        if evt.date_publication_jo >= ten_years_ago:
            nb_evt_10ans += 1

    return HistoriqueEvts(
        total_evts=len(events),
        evts_par_type=counts,
        evts=events,
        disponible=bool(entries),
        evt_le_plus_recent=events[0] if events else None,
        nb_evt_10ans=nb_evt_10ans,
    )


def _extract_facilites_proches(georisques: dict[str, Any], risques_technologiques: dict[str, Any]) -> FacilitesProches:
    icpe_entries = georisques.get("icpe")
    sites_sols_pollues = _as_dict(georisques.get("sites_sols_pollues"))
    icpe_count = len(icpe_entries) if isinstance(icpe_entries, list) else 0

    casias = _as_dict(sites_sols_pollues.get("casias"))
    instructions = _as_dict(sites_sols_pollues.get("instructions"))
    ssp_count = _coerce_int(casias.get("results"))
    if ssp_count is None:
        ssp_count = _coerce_int(instructions.get("results"))
    if ssp_count is None and isinstance(casias.get("data"), list):
        ssp_count = len(casias.get("data"))
    if ssp_count is None:
        ssp_count = 0

    canalisation = _classify_risque_statut(
        _as_dict(risques_technologiques.get("canalisationsMatieresDangereuses"))
    )

    return FacilitesProches(
        icpe_count=icpe_count,
        icpe_present=icpe_count > 0,
        sites_sols_pollues_count=ssp_count,
        sites_sols_pollues_present=ssp_count > 0,
        canalisation_matieres_dangereuses=canalisation,
        disponible=True,
    )


def _extract_topographie(ign: dict[str, Any]) -> DonneesTopo:
    altitude_block = _as_dict(ign.get("altitude"))
    elevations = altitude_block.get("elevations")
    if isinstance(elevations, list) and elevations:
        first = _as_dict(elevations[0])
        altitude = _coerce_float(first.get("z"))
        if altitude is not None:
            return DonneesTopo(altitude_m=altitude, disponible=True)
    return DonneesTopo(altitude_m=None, disponible=False)


def _extract_eaux_souterraines(hubeau: dict[str, Any]) -> EauxSouterraines:
    stations = hubeau.get("stations_piezometrie")
    count = len(stations) if isinstance(stations, list) else 0
    return EauxSouterraines(
        stations_piezometriques_count=count,
        presente=count > 0,
        disponible=bool(hubeau),
    )


def _list_missing_blocks(payload: dict[str, Any]) -> list[str]:
    missing = [block for block in DEFAULT_MISSING_BLOCKS if not payload.get(block)]
    return missing


def _normalize_catnat_type(label: str) -> str:
    normalized = label.lower()
    if "inond" in normalized or "coulée" in normalized or "coulee" in normalized:
        return "inondation"
    if "mouvement" in normalized:
        return "mouvement_terrain"
    if "sécheresse" in normalized or "secheresse" in normalized:
        return "secheresse"
    if "tempête" in normalized or "tempete" in normalized:
        return "tempete"
    if "retrait" in normalized or "argile" in normalized:
        return "retrait_gonflement_argile"
    return _slugify(label)


def _normalize_rga_exposition(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    text = text.replace("é", "e").replace("è", "e").replace("ê", "e")
    text = text.replace("à", "a").replace("â", "a")
    text = text.replace("î", "i").replace("ï", "i")
    text = text.replace("ô", "o").replace("û", "u")
    text = re.sub(r"^exposition\s+", "", text)
    text = text.replace("moderee", "modere")
    return text.strip()


def _classify_risque_statut(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    statut = str(item.get("libelleStatutAdresse") or "").lower()
    if not statut:
        return None
    if "non concerne" in statut:
        return "absent"
    if "concerne" in statut or "existant" in statut:
        return "present"
    return _slugify(item.get("libelleStatutAdresse") or "")


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    formats = (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _days_since(when: datetime, now: datetime) -> int:
    return max(0, int((now - when).days))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_item(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, list) and raw:
        return _as_dict(raw[0])
    if isinstance(raw, dict) and raw:
        return raw
    return None


def _coerce_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


if __name__ == "__main__":
    import json
    from pathlib import Path

    payload_path = Path(__file__).with_name("risques_adresse.json")
    profile = extract_profil_risque_condense(json.loads(payload_path.read_text(encoding="utf-8")))
    print(profile)
    print(asdict(profile))
