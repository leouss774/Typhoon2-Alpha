"""
Annonces immobilieres "en vente" pour la carte de zone (marqueurs colores
par score climatique - cf. frontend/jumeau_numerique/index.html).

UNIQUEMENT des donnees reelles : pas de generateur DEMO, pas d'appel API
tiers payant (RapidAPI a ete retire du code - un essai reel a facture
0,40e des le premier appel, meme avec une cle valide : voir l'historique
du projet si besoin, mais aucune trace de ce code ne subsiste ici).

Deux sources reelles possibles, dans l'ordre de priorite applique par
app/api/routes/diagnostic.py::run_zone_annonces :

  1. DVF (ventes deja realisees, cf. dvf_lookup.py).
  2. CSV local (ce module) : une base d'annonces "en vente" constituee a la
     main par l'utilisateur (backend/data/annonces_maisons_france.csv),
     avec de vrais liens PAP.fr. Gratuit, pas d'appel reseau, pas de risque
     de facturation. Chargee une fois puis mise en cache en memoire.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
# zone_scoring removed — climate scores no longer computed here

logger = get_logger(__name__)

# backend/app/connectors/annonces_lookup.py -> backend/data/annonces_maisons_france.csv
_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "annonces_maisons_france.csv"

_cache: list[dict] | None = None


class AnnoncesProviderUnavailable(RuntimeError):
    pass


def _to_float(value) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _load_csv() -> list[dict]:
    """Charge backend/data/annonces_maisons_france.csv une seule fois
    (mis en cache en memoire - fichier de quelques dizaines de lignes,
    pas besoin de le relire a chaque requete). Colonnes attendues :
    prix,ville,departement,surface,pieces,latitude,longitude,source,url.
    """
    global _cache
    if _cache is not None:
        return _cache

    if not _CSV_PATH.exists():
        raise AnnoncesProviderUnavailable(f"CSV d'annonces introuvable : {_CSV_PATH}")

    listings: list[dict] = []
    with open(_CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            lat = _to_float(row.get("latitude"))
            lon = _to_float(row.get("longitude"))
            if lat is None or lon is None:
                logger.warning("annonces_lookup (csv) -- ligne %d ignoree (lat/lon manquants) : %s", idx, row)
                continue

            prix = _to_float(row.get("prix"))
            surface = _to_float(row.get("surface"))
            prix_m2 = round(prix / surface, 0) if (prix and surface) else None

            listings.append({
                "id": f"csv-{idx}",
                "lat": lat,
                "lon": lon,
                "adresse": (row.get("ville") or "Bien immobilier").strip(),
                "type_bien": "Maison",
                "surface_m2": surface,
                "prix": prix,
                "prix_m2": prix_m2,
                "pieces": _to_int(row.get("pieces")),
                "dpe": None,  # pas de DPE dans cette base
                "date_publication": None,  # pas de date de publication dans cette base
                "climat_score": None,  # zone scoring pipeline removed; use /diagnostic/adresse per address
                "source": "csv",
                "url": (row.get("url") or "").strip() or None,
                "photo": None,
            })

    _cache = listings
    logger.info("annonces_lookup (csv) -- %d annonces chargees depuis %s", len(listings), _CSV_PATH)
    return listings


# ---------------------------------------------------------------------------
#   Point d'entrée
# ---------------------------------------------------------------------------

async def fetch_annonces_zone(
    bounds: tuple[float, float, float, float],
    max_results: int = 40,
    prix_m2_base: float | None = None,  # conserve pour compat. signature (non utilise par cette source)
) -> dict:
    """Retourne les annonces réelles à afficher (base CSV locale, voir
    _load_csv). Ne filtre PAS par bounds : la base couvre déjà toute la
    France par construction (demande explicite précédente), et MapLibre
    n'affiche de toute façon que les points dans la zone visible à l'écran.
    Jamais d'erreur dure : liste vide + raison si le CSV est absent/invalide.
    """
    try:
        listings = _load_csv()
    except AnnoncesProviderUnavailable as exc:
        return {"source": "none", "listings": [], "fallback_reason": str(exc)}

    return {"source": "csv", "listings": listings[:max_results]}
