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
        "risques_commune":    ("gaspar/risques",          {"code_insee": citycode}),
        "catnat":             ("gaspar/catnat",            {"code_insee": citycode}),
        "zones_inondables":   ("azi",                     {"code_insee": citycode}),
        "cavites":            ("cavites",                  {"latlon": latlon, "rayon": rayon_m}),
        "zonage_sismique":    ("zonage_sismique",          {"code_insee": citycode}),
        "radon":              ("radon",                    {"code_insee": citycode}),
        "mouvements_terrain": ("mvt",                     {"latlon": latlon, "rayon": rayon_m}),
        # pageSize=100 : la reponse gaspar est paginee (page de 10 par defaut)
        # — sans ca, on ne lit que les 10 premiers PPR de la commune.
        "ppr":                ("gaspar/pprn",              {"code_insee": citycode, "pageSize": 100}),
        "pprt":               ("gaspar/pprt",              {"code_insee": citycode, "pageSize": 100}),
        "ssp":                ("ssp",                      {"code_insee": citycode}),
        "icpe":               ("installations_classees",   {"code_insee": citycode}),
    }

    # Endpoints that legitimately return 404 when no data exists for the commune
    _404_ok = {"zones_inondables", "ppr", "pprt", "ssp", "icpe"}

    for cle, (path, params) in sources.items():
        try:
            resultat[cle] = await _get(client, path, params)
        except httpx.HTTPStatusError as exc:
            resultat[cle] = None
            if exc.response.status_code == 404 and cle in _404_ok:
                pass  # no data = expected, normalizers handle it
            else:
                resultat["erreurs"].append({
                    "source": f"georisques.{cle}",
                    "erreur": str(exc),
                })
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
        # Deux formes selon l'endpoint : `data` (gaspar/risques, catnat…) ou
        # `content` (gaspar/pprn, gaspar/pprt — réponse paginée Spring).
        d = val.get("data")
        if not isinstance(d, list):
            d = val.get("content")
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


def _is_source_failed(raw: dict, cle: str) -> bool:
    return any(
        cle in (e.get("source") or "")
        for e in (raw.get("erreurs") or [])
    )


# ---------------------------------------------------------------------------
# Normalisation aléa par aléa
# ---------------------------------------------------------------------------

def _alea_icpe(raw: dict) -> AleaDetail:
    """Installations classées (ICPE) — dont Seveso."""
    failed = _is_source_failed(raw, "icpe")
    if failed:
        return AleaDetail(
            code="icpe", libelle="Installations industrielles (ICPE)",
            present=None, present_commune=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/installations-classees-pour-la-protection-de-lenvironnement-icpe",
        )
    icpe_list = _data_list(raw, "icpe")
    n = len(icpe_list)
    seveso = any(
        (
            "seveso" in str(e.get("statut_seveso", "") or "").lower()
            or "seveso" in str(e.get("lib_statut_seveso", "") or "").lower()
        )
        for e in icpe_list
        if isinstance(e, dict)
    )
    base = 10
    if seveso: base = 80
    elif n >= 10: base = 65
    elif n >= 3: base = 45
    elif n >= 1: base = 30
    return AleaDetail(
        code="icpe", libelle="Installations industrielles (ICPE)",
        present=(n > 0),
        present_commune=(n > 0),
        niveau=_score_to_niveau(base),
        zonage=(f"{n} installation(s) classée(s)" + (" dont Seveso" if seveso else "")) if n > 0 else None,
        url_detail="https://www.georisques.gouv.fr/risques/installations-classees-pour-la-protection-de-lenvironnement-icpe",
    )


def _alea_canalisations(raw: dict) -> AleaDetail:
    """Réseaux et canalisations de matières dangereuses (GASPAR)."""
    failed = _is_source_failed(raw, "risques_commune")
    if failed:
        return AleaDetail(
            code="canalisations", libelle="Réseaux et canalisations",
            present=None, present_commune=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/transport-de-matieres-dangereuses",
        )
    hazard = (
        _has_hazard_keyword(raw, "canalisation")
        or _has_hazard_keyword(raw, "matières dangereuses")
        or _has_hazard_keyword(raw, "transport de marchandises dangereuses")
        or _has_hazard_keyword(raw, "tmd")
    )
    score = 45 if hazard else 5
    return AleaDetail(
        code="canalisations", libelle="Réseaux et canalisations",
        present=hazard,
        present_commune=hazard,
        niveau=_score_to_niveau(score),
        url_detail="https://www.georisques.gouv.fr/risques/transport-de-matieres-dangereuses",
    )


def _alea_vent_cyclonique(raw: dict) -> AleaDetail:
    """Vents cycloniques — pertinent essentiellement pour les DOM-TOM."""
    failed = _is_source_failed(raw, "risques_commune")
    if failed:
        return AleaDetail(
            code="vent_cyclonique", libelle="Vents cycloniques",
            present=None, present_commune=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/cyclones",
        )
    hazard = (
        _has_hazard_keyword(raw, "cyclone")
        or _has_hazard_keyword(raw, "vent cyclonique")
        or _has_hazard_keyword(raw, "phénomène météorologique")
        or _has_hazard_keyword(raw, "phenomene meteorologique")
    )
    score = 60 if hazard else 5
    return AleaDetail(
        code="vent_cyclonique", libelle="Vents cycloniques",
        present=hazard,
        present_commune=hazard,
        niveau=_score_to_niveau(score),
        url_detail="https://www.georisques.gouv.fr/risques/cyclones",
    )


def _alea_ppr(raw: dict) -> AleaDetail:
    """Plans de Prévention des Risques (PPRN + PPRT fusionnés)."""
    failed = _is_source_failed(raw, "ppr")
    if failed:
        return AleaDetail(
            code="ppr", libelle="Plan de Prévention des Risques (PPR)",
            present=None, present_commune=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/plans-de-prevention-des-risques",
        )
    ppr_list = _data_list(raw, "ppr")
    pprt_list = _data_list(raw, "pprt")
    n_ppr = len(ppr_list) + len(pprt_list)
    score = 10
    if n_ppr >= 3: score = 75
    elif n_ppr >= 1: score = 50
    return AleaDetail(
        code="ppr", libelle="Plan de Prévention des Risques (PPR)",
        present=(n_ppr > 0),
        present_commune=(n_ppr > 0),
        niveau=_score_to_niveau(score),
        zonage=f"{n_ppr} PPR recensé(s)" if n_ppr > 0 else "Aucun PPR prescrit",
        url_detail="https://www.georisques.gouv.fr/risques/plans-de-prevention-des-risques",
    )


def _alea_ssp(raw: dict) -> AleaDetail:
    """Sites et Sols Pollués (BASOL / CASIAS / SIS)."""
    failed = _is_source_failed(raw, "ssp")
    if failed:
        return AleaDetail(
            code="ssp", libelle="Sites et sols pollués (SSP)",
            present=None, present_commune=None, niveau=None,
            erreur="source Géorisques indisponible",
            url_detail="https://www.georisques.gouv.fr/risques/sites-et-sols-pollues",
        )
    ssp_list = _data_list(raw, "ssp")
    n_ssp = len(ssp_list)
    score = 10
    if n_ssp >= 5: score = 70
    elif n_ssp >= 1: score = 40
    return AleaDetail(
        code="ssp", libelle="Sites et sols pollués (SSP)",
        present=(n_ssp > 0),
        present_commune=(n_ssp > 0),
        niveau=_score_to_niveau(score),
        zonage=f"{n_ssp} site(s) ou sol(s) pollué(s)" if n_ssp > 0 else "Aucun site recensé",
        url_detail="https://www.georisques.gouv.fr/risques/sites-et-sols-pollues",
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
    Couvre les périls conservés (ICPE, canalisations, vents cycloniques, PPR, SSP).
    """
    raw = await fetch_georisques_raw(client, code_insee, lat, lon)

    aleas = [
        _alea_icpe(raw),
        _alea_canalisations(raw),
        _alea_vent_cyclonique(raw),
        _alea_ppr(raw),
        _alea_ssp(raw),
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
