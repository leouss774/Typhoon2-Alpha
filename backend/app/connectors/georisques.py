"""
Connecteur Géorisques v1 — appel brut + normalisation vers RisqueReport.

API : https://www.georisques.gouv.fr/api/v1 (BRGM / MTE)
Publique, gratuite, sans clé. Limite : 1000 req/min/IP.

Chaque sous-appel est isolé dans son propre try/except :
si une route est indisponible, le reste du rapport continue
et l'erreur remonte dans erreurs_partielles (jamais un 500 global).

Règle clé : aucune valeur inventée si la source est absente.
Un aléa absent = present=None + erreur explicite dans AleaDetail.erreur.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from app.core.config import settings
from app.schemas.risque_report import AleaDetail, NiveauRisque, RisqueReport

_BASE = settings.georisques_base_url


# ---------------------------------------------------------------------------
# Appel HTTP bas niveau
# ---------------------------------------------------------------------------

async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict | list | None:
    response = await client.get(f"{_BASE}/{path}", params=params, timeout=8.0)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Collecte brute des données Géorisques
# ---------------------------------------------------------------------------

async def fetch_georisques_raw(
    client: httpx.AsyncClient,
    citycode: str,
    lat: float,
    lon: float,
    rayon_m: int = 1000,
) -> dict:
    """
    Interroge les endpoints Géorisques pour une adresse.

    Retourne un dict avec une clé par sous-source + "erreurs" (liste).
    Ne lève jamais d'exception : les erreurs partielles sont consignées.
    """
    resultat: dict = {"erreurs": []}
    latlon = f"{lon},{lat}"

    sources = {
        "risques_commune":    ("gaspar/risques",   {"code_insee": citycode}),
        "catnat":             ("gaspar/catnat",     {"code_insee": citycode}),
        "zones_inondables":   ("azi",              {"code_insee": citycode}),
        "cavites":            ("cavites",           {"latlon": latlon, "rayon": rayon_m}),
        "zonage_sismique":    ("zonage_sismique",   {"code_insee": citycode}),
        "radon":              ("radon",             {"code_insee": citycode}),
        "mouvements_terrain": ("mvt",              {"latlon": latlon, "rayon": rayon_m}),
        "feu_foret":          ("gaspar/risques",    {"code_insee": citycode}),  # filtré ci-dessous
    }

    for cle, (path, params) in sources.items():
        if cle == "feu_foret":
            # feu_foret est dans risques_commune, pas une route séparée
            continue
        try:
            resultat[cle] = await _get(client, path, params)
        except httpx.HTTPError as exc:
            resultat[cle] = None
            resultat["erreurs"].append({
                "source": f"georisques.{cle}",
                "erreur": str(exc),
            })

    return resultat


# ---------------------------------------------------------------------------
# Helpers d'extraction
# ---------------------------------------------------------------------------

def _data_list(raw: dict, key: str) -> list:
    val = (raw or {}).get(key)
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        d = val.get("data")
        return d if isinstance(d, list) else []
    return []


def _has_hazard_keyword(raw: dict, keyword: str) -> bool:
    rc = (raw or {}).get("risques_commune") or {}
    data = rc.get("data") if isinstance(rc, dict) else None
    if not data:
        return False
    kw = keyword.lower()
    for entry in data:
        for detail in (entry.get("risques_detail") or []):
            if kw in (detail.get("libelle_risque_long") or "").lower():
                return True
    return False


def _count_catnat_keyword(raw: dict, keyword: str) -> int:
    catnat = (raw or {}).get("catnat") or {}
    data = catnat.get("data") if isinstance(catnat, dict) else None
    if not data:
        return 0
    kw = keyword.lower()
    return sum(
        1 for a in data
        if kw in (a.get("libelle_risque_jo") or "").lower()
    )


def _catnat_entries(raw: dict) -> list[dict]:
    catnat = (raw or {}).get("catnat") or {}
    data = catnat.get("data") if isinstance(catnat, dict) else None
    return data or []


def _is_source_failed(raw: dict, cle: str) -> bool:
    return any(
        cle in (e.get("source") or "")
        for e in (raw.get("erreurs") or [])
    )


# ---------------------------------------------------------------------------
# Normalisation aléa par aléa
# ---------------------------------------------------------------------------

def _alea_inondation(raw: dict) -> AleaDetail:
    failed = _is_source_failed(raw, "risques_commune") and _is_source_failed(raw, "catnat")
    if failed:
        return AleaDetail(
            code="inondation", libelle="Inondation",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/inondations",
        )
    n_catnat = _count_catnat_keyword(raw, "inondation") + _count_catnat_keyword(raw, "coulée")
    hazard = _has_hazard_keyword(raw, "inondation")
    zi = _data_list(raw, "zones_inondables")

    base = 10
    if n_catnat >= 6: base = 75
    elif n_catnat >= 3: base = 55
    elif n_catnat >= 1: base = 35
    if hazard: base += 8
    if zi: base += 12
    score = min(base, 100)

    niveau = _score_to_niveau(score)
    catnat_hist = _catnat_entries(raw) or None
    return AleaDetail(
        code="inondation", libelle="Inondation",
        present=(hazard or n_catnat > 0 or bool(zi)),
        niveau=niveau,
        catnat_historique=catnat_hist,
        url_detail="https://www.georisques.gouv.fr/risques/inondations",
    )


def _alea_rga(raw: dict) -> AleaDetail:
    """Retrait-gonflement des argiles."""
    failed = _is_source_failed(raw, "risques_commune")
    if failed:
        return AleaDetail(
            code="rga", libelle="Retrait-gonflement des argiles",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/retrait-gonflement-des-argiles",
        )
    hazard = _has_hazard_keyword(raw, "argile") or _has_hazard_keyword(raw, "retrait")
    n_sec = _count_catnat_keyword(raw, "sécheresse") + _count_catnat_keyword(raw, "secheresse")
    base = 15
    if hazard: base = 50
    base += min(n_sec * 8, 30)
    score = min(base, 100)
    return AleaDetail(
        code="rga", libelle="Retrait-gonflement des argiles",
        present=(hazard or n_sec > 0),
        niveau=_score_to_niveau(score),
        url_detail="https://www.georisques.gouv.fr/risques/retrait-gonflement-des-argiles",
    )


def _alea_sismicite(raw: dict) -> AleaDetail:
    failed = _is_source_failed(raw, "zonage_sismique")
    if failed:
        return AleaDetail(
            code="sismicite", libelle="Sismicité",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/seismes",
        )
    zonage = _data_list(raw, "zonage_sismique")
    zone_val = None
    if zonage and isinstance(zonage[0], dict):
        zone_val = zonage[0].get("zone_sismicite")
    # Aussi chercher dans risques_commune
    if zone_val is None:
        rc = (raw.get("risques_commune") or {})
        data = rc.get("data") if isinstance(rc, dict) else None
        for entry in (data or []):
            for detail in (entry.get("risques_detail") or []):
                if detail.get("zone_sismicite") is not None:
                    zone_val = detail["zone_sismicite"]
                    break

    zone_int = None
    if zone_val is not None:
        m = re.match(r"\s*(\d+)", str(zone_val))
        if m:
            zone_int = int(m.group(1))

    mapping = {0: 5, 1: 15, 2: 30, 3: 50, 4: 70, 5: 88}
    score = mapping.get(zone_int, 15) if zone_int is not None else 15
    zonage_str = f"Zone {zone_int}" if zone_int is not None else None

    return AleaDetail(
        code="sismicite", libelle="Sismicité",
        present=(zone_int is not None and zone_int >= 1),
        niveau=_score_to_niveau(score),
        zonage=zonage_str,
        url_detail="https://www.georisques.gouv.fr/risques/seismes",
    )


def _alea_radon(raw: dict) -> AleaDetail:
    failed = _is_source_failed(raw, "radon")
    if failed:
        return AleaDetail(
            code="radon", libelle="Radon",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/radon",
        )
    radon_data = _data_list(raw, "radon")
    classe = None
    if radon_data and isinstance(radon_data[0], dict):
        classe = radon_data[0].get("classe_potentiel")
    try:
        classe_int = int(classe)
    except (TypeError, ValueError):
        classe_int = None

    mapping = {1: (10, "Catégorie 1 - faible"), 2: (35, "Catégorie 2 - moyen"), 3: (65, "Catégorie 3 - élevé")}
    if classe_int in mapping:
        score, zonage_str = mapping[classe_int]
    else:
        score, zonage_str = 10, None

    return AleaDetail(
        code="radon", libelle="Radon",
        present=(classe_int is not None and classe_int >= 2),
        niveau=_score_to_niveau(score),
        zonage=zonage_str,
        url_detail="https://www.georisques.gouv.fr/risques/radon",
    )


def _alea_feu_foret(raw: dict) -> AleaDetail:
    failed = _is_source_failed(raw, "risques_commune")
    if failed:
        return AleaDetail(
            code="feu_foret", libelle="Feu de forêt",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/feux-de-foret",
        )
    hazard = (
        _has_hazard_keyword(raw, "feu de forêt")
        or _has_hazard_keyword(raw, "feu de foret")
        or _has_hazard_keyword(raw, "incendie")
    )
    score = 55 if hazard else 5
    return AleaDetail(
        code="feu_foret", libelle="Feu de forêt",
        present=hazard,
        niveau=_score_to_niveau(score),
        url_detail="https://www.georisques.gouv.fr/risques/feux-de-foret",
    )


def _alea_mouvement_terrain(raw: dict) -> AleaDetail:
    failed = _is_source_failed(raw, "mouvements_terrain") and _is_source_failed(raw, "cavites")
    if failed:
        return AleaDetail(
            code="mouvement_terrain", libelle="Mouvement de terrain",
            present=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/mouvements-de-terrain",
        )
    cavites = _data_list(raw, "cavites")
    mvt = _data_list(raw, "mouvements_terrain")
    n_mvt_catnat = _count_catnat_keyword(raw, "mouvement de terrain")
    n = len(cavites) + len(mvt) + n_mvt_catnat
    base = 10 + min(n * 10, 60)
    return AleaDetail(
        code="mouvement_terrain", libelle="Mouvement de terrain",
        present=(n > 0),
        niveau=_score_to_niveau(base),
        url_detail="https://www.georisques.gouv.fr/risques/mouvements-de-terrain",
    )


def _score_to_niveau(score: int) -> NiveauRisque:
    if score < 20: return NiveauRisque.TRES_FAIBLE
    if score < 40: return NiveauRisque.FAIBLE
    if score < 60: return NiveauRisque.MODERE
    if score < 80: return NiveauRisque.ELEVE
    return NiveauRisque.CRITIQUE


# ---------------------------------------------------------------------------
# Point d'entrée principal : normalise le brut en RisqueReport
# ---------------------------------------------------------------------------

async def get_risque_report(
    client: httpx.AsyncClient,
    adresse_saisie: str,
    adresse_normalisee: str,
    lat: float,
    lon: float,
    code_insee: str,
) -> RisqueReport:
    """
    Orchestre les appels Géorisques et retourne un RisqueReport normalisé.
    Ne lève jamais d'exception réseau (erreurs_partielles à la place).
    """
    raw = await fetch_georisques_raw(client, code_insee, lat, lon)

    aleas = [
        _alea_inondation(raw),
        _alea_rga(raw),
        _alea_sismicite(raw),
        _alea_radon(raw),
        _alea_feu_foret(raw),
        _alea_mouvement_terrain(raw),
    ]

    erreurs_partielles = [
        f"{e['source']}: {e['erreur']}"
        for e in (raw.get("erreurs") or [])
    ]
    alea_count = sum(1 for a in aleas if a.present is True)

    return RisqueReport(
        adresse_saisie=adresse_saisie,
        adresse_normalisee=adresse_normalisee,
        lat=lat,
        lon=lon,
        code_insee=code_insee,
        date_generation=date.today(),
        alea_count=alea_count,
        aleas=aleas,
        erreurs_partielles=erreurs_partielles,
    )
