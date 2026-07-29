"""
Annonces immobilieres "en vente" pour la carte de zone (marqueurs colores
par score climatique - cf. frontend/jumeau_numerique/index.html).

UNIQUEMENT des donnees reelles : pas de generateur DEMO (retire a la
demande explicite de l'utilisateur - la carte ne doit jamais afficher de
biens fictifs). Deux sources reelles possibles :

  1. DVF (ventes deja realisees, cf. dvf_lookup.py - priorite dans
     app/api/routes/diagnostic.py::run_zone_annonces).
  2. RAPIDAPI (des que ANNONCES_RAPIDAPI_KEY/HOST sont renseignes) : appelle
     un wrapper RapidAPI d'annonces FR reel (voir _call_rapidapi). Si non
     configure ou en echec, fetch_annonces_zone renvoie une liste VIDE
     plutot que des donnees fabriquees - jamais de repli demo.
"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.scoring.zone_scoring import score_point_climat

logger = get_logger(__name__)

# Correspondance type de bien -> libelles deja utilises ailleurs dans l'app
# (badges DVF, legende carte). Cle en minuscules, valeur par defaut = valeur
# brute mise en forme si absente de la table.
_PROPERTY_TYPE_LABELS = {
    "flat": "Appartement",
    "apartment": "Appartement",
    "studio": "Appartement",
    "duplex": "Appartement",
    "house": "Maison",
    "villa": "Maison",
    "loft": "Appartement",
}


class AnnoncesProviderUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------------------
#   Mode RapidAPI - schema confirme sur un vrai echantillon fourni par
#   l'utilisateur (enveloppe {"size": N, "results": [...]}, donnees issues
#   d'un flux Ubiflow agrege). ATTENTION : l'echantillon observe est un flux
#   de LOCATIONS (loyers mensuels - "Loyer", "Dépôt de garantie", "bail"
#   dans les descriptions), pas de ventes. Le champ "prix" ci-dessous reste
#   donc a verifier selon le parametre de transaction envoye a l'API (voir
#   _call_rapidapi) : ne pas presenter un loyer comme un prix de vente.
# ---------------------------------------------------------------------------

_PHOTO_ID_RE = re.compile(r"/(\d+)/photos/")


def _extract_id_from_photo(photo_url: str | None) -> str | None:
    """Les URLs de photos Ubiflow contiennent l'identifiant du bien
    (.../{agence}/{id_bien}/photos/1.jpg) : plus stable qu'un hash si
    aucun champ id explicite n'est fourni par l'API."""
    if not photo_url:
        return None
    m = _PHOTO_ID_RE.search(photo_url)
    return m.group(1) if m else None


def _map_listing(raw: dict, climat_score: int) -> dict:
    """Normalise une annonce brute de l'API (schema confirme, voir
    docstring de section ci-dessus) vers le format interne partage avec le
    mode demo et les ventes DVF."""
    location = raw.get("location") or {}
    coords = location.get("coordinates") or {}
    data = raw.get("data") or {}
    carac = raw.get("propertyCaracteristics") or {}
    metadata = raw.get("metadata") or {}

    lat = coords.get("lat")
    lon = coords.get("lon")

    photos = data.get("photos") or []
    photo = photos[0] if photos else None
    title = (data.get("title") or "").strip()
    city = location.get("city")
    adresse = f"{title} — {city}" if title and city else (title or city or "Bien immobilier")

    surface = carac.get("propertySurface")
    prix = carac.get("price")
    prix_m2 = round(prix / surface, 0) if (prix and surface) else None

    jours_en_ligne = metadata.get("daysSinceOnMarket")
    date_publication = (
        (datetime.now(timezone.utc) - timedelta(days=jours_en_ligne)).date().isoformat()
        if jours_en_ligne is not None else None
    )

    property_type_raw = (raw.get("propertyType") or "").lower()
    type_bien = _PROPERTY_TYPE_LABELS.get(property_type_raw, raw.get("propertyType") or "Bien")

    listing_id = _extract_id_from_photo(photo) or hashlib.sha1(
        f"{lat}:{lon}:{title}".encode()
    ).hexdigest()[:12]

    return {
        "id": f"api-{listing_id}",
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "adresse": adresse,
        "type_bien": type_bien,
        "surface_m2": surface,
        "prix": prix,
        "prix_m2": prix_m2,
        "pieces": carac.get("rooms"),
        "dpe": None,  # pas de champ DPE structure dans ce flux (uniquement en texte libre parfois)
        "date_publication": date_publication,
        "climat_score": climat_score,
        "source": "rapidapi",
        "url": None,  # pas d'URL de fiche annonce dans ce flux, seulement des photos
        "photo": photo,
    }


def _in_bounds(lat: float, lon: float, bounds: tuple[float, float, float, float]) -> bool:
    lat_min, lon_min, lat_max, lon_max = bounds
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bounds_center_and_radius_m(bounds: tuple[float, float, float, float]) -> tuple[float, float, int]:
    lat_min, lon_min, lat_max, lon_max = bounds
    lat_c, lon_c = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    radius = _haversine_m(lat_min, lon_min, lat_max, lon_max) / 2
    return lat_c, lon_c, max(500, min(int(radius), 50_000))  # borne 500m..50km


def _to_float(value) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
#   Mode RapidAPI - wrapper "leboncoin1.p.rapidapi.com", endpoint confirme
#   "GET /v2/leboncoin/search?query=<URL leboncoin.fr encodee>". Ce wrapper
#   proxie une vraie recherche leboncoin.fr : on construit donc une URL de
#   recherche leboncoin.fr (category=9 = Ventes immobilieres, PAS Locations -
#   ca resout le probleme loyer/vente rencontre avec le wrapper precedent),
#   centree sur la zone visible via le parametre locations=Nom__lat_lon_rayon.
#
#   Schema de reponse NON CONFIRME (le wrapper ne fait que proxier, donc
#   probablement l'API interne leboncoin.fr classique : {"ads": [...]} avec
#   subject/price/location/attributes/images - documente par plusieurs
#   clients non officiels, ex. github.com/etienne-hd/lbc). A verifier/
#   corriger avec l'onglet "Example Responses" du wrapper des que possible.
# ---------------------------------------------------------------------------

def _map_listing_leboncoin(raw: dict, climat_score: int) -> dict:
    location = raw.get("location") or {}
    lat = location.get("lat")
    lon = location.get("lng") or location.get("lon")

    attrs = {a.get("key"): a.get("value") for a in (raw.get("attributes") or []) if isinstance(a, dict)}
    surface = _to_float(attrs.get("square"))
    type_bien = attrs.get("real_estate_type") or "Bien"

    price = raw.get("price")
    prix = _to_float(price[0]) if isinstance(price, list) and price else _to_float(price)
    prix_m2 = round(prix / surface, 0) if (prix and surface) else None

    images = raw.get("images") or {}
    photos = images.get("urls") or images.get("urls_thumb") or []
    photo = photos[0] if photos else None

    date_pub_raw = raw.get("first_publication_date") or raw.get("index_date")
    date_publication = str(date_pub_raw)[:10] if date_pub_raw else None

    ad_id = raw.get("list_id") or raw.get("id")
    listing_id = str(ad_id) if ad_id else hashlib.sha1(
        f"{lat}:{lon}:{raw.get('subject')}".encode()
    ).hexdigest()[:12]

    return {
        "id": f"lbc-{listing_id}",
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "adresse": raw.get("subject") or location.get("city") or "Bien immobilier",
        "type_bien": type_bien,
        "surface_m2": surface,
        "prix": prix,
        "prix_m2": prix_m2,
        "pieces": attrs.get("rooms"),
        "dpe": attrs.get("energy_rate_value"),
        "date_publication": date_publication,
        "climat_score": climat_score,
        "source": "rapidapi",
        "url": raw.get("url"),
        "photo": photo,
    }


def _map_listing_auto(raw: dict, climat_score: int) -> dict:
    """Aiguille vers le mapper adapte au schema effectivement recu (les deux
    wrappers testes n'ont pas le meme format de reponse)."""
    if "propertyCaracteristics" in raw:
        return _map_listing(raw, climat_score)
    return _map_listing_leboncoin(raw, climat_score)


def _extract_lat_lon(raw: dict) -> tuple[float | None, float | None]:
    if "propertyCaracteristics" in raw:
        coords = (raw.get("location") or {}).get("coordinates") or {}
        return coords.get("lat"), coords.get("lon")
    location = raw.get("location") or {}
    return location.get("lat"), (location.get("lng") or location.get("lon"))


_MAX_PAGES = 6  # securite anti-boucle : leboncoin.fr pagine ~35 annonces/page


async def _call_rapidapi(bounds: tuple[float, float, float, float], max_results: int) -> list[dict]:
    """Appelle le wrapper RapidAPI "leboncoin1.p.rapidapi.com" (endpoint
    confirme : "Search via URL", GET /v2/leboncoin/search?query=<url encodee>).

    Recherche NATIONALE (pas de parametre "locations") : category=9 =
    "Ventes immobilieres" sur toute la France, comme demande explicitement
    (voir aussi bounds, desormais ignore pour cet appel - il ne sert plus
    qu'aux autres modes/zone-scoring). httpx se charge de l'encodage de
    l'URL leboncoin.fr imbriquee dans le parametre "query". Pagine (param
    "page" de leboncoin.fr) jusqu'a max_results ou _MAX_PAGES, en s'arretant
    des qu'une page ne renvoie plus rien (fin des resultats).
    """
    if not (settings.annonces_rapidapi_key and settings.annonces_rapidapi_host):
        raise AnnoncesProviderUnavailable("ANNONCES_RAPIDAPI_KEY/HOST non renseignes (mode demo actif)")

    url = f"https://{settings.annonces_rapidapi_host}{settings.annonces_rapidapi_search_path}"
    headers = {
        "X-RapidAPI-Key": settings.annonces_rapidapi_key,
        "X-RapidAPI-Host": settings.annonces_rapidapi_host,
    }

    mapped: list[dict] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for page in range(1, _MAX_PAGES + 1):
            target_url = f"https://www.leboncoin.fr/recherche?category=9&page={page}"
            params = {settings.annonces_rapidapi_search_param: target_url}

            resp = await client.get(url, params=params, headers=headers)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Le corps de reponse RapidAPI contient generalement la vraie
                # raison (cle non souscrite a CETTE api, quota depasse,
                # parametre invalide...) - bien plus utile que juste le code
                # HTTP pour comprendre un "aucune offre disponible" cote UI.
                body_preview = resp.text[:500]
                raise AnnoncesProviderUnavailable(
                    f"RapidAPI HTTP {resp.status_code} sur {url} (page {page}) : {body_preview}"
                ) from exc
            payload = resp.json()

            root_keys = list(payload.keys()) if isinstance(payload, dict) else f"<list de {len(payload)}>"
            logger.info("annonces_lookup -- page %d : HTTP %d, cles racine=%s", page, resp.status_code, root_keys)

            # "ads" = enveloppe habituelle de l'API interne leboncoin.fr. Repli
            # sur d'autres formes courantes si le wrapper reformate differemment.
            items = payload if isinstance(payload, list) else (
                payload.get("ads") or payload.get("results") or payload.get("data") or []
            )
            if not items:
                if page == 1:
                    logger.warning(
                        "annonces_lookup -- reponse HTTP 200 mais aucune annonce extraite "
                        "(cles racine=%s) - le nom d'enveloppe (\"ads\"/\"results\"/\"data\") "
                        "ne correspond peut-etre pas au schema reel de ce wrapper",
                        root_keys,
                    )
                break  # plus de resultats, inutile de continuer a paginer

            for item in items:
                lat, lon = _extract_lat_lon(item)
                if lat is None or lon is None:
                    continue
                climat = score_point_climat(float(lat), float(lon))
                listing = _map_listing_auto(item, climat)
                if listing["id"] in seen_ids:
                    continue
                seen_ids.add(listing["id"])
                mapped.append(listing)
                if len(mapped) >= max_results:
                    return mapped

    return mapped


# ---------------------------------------------------------------------------
#   Point d'entrée
# ---------------------------------------------------------------------------

async def fetch_annonces_zone(
    bounds: tuple[float, float, float, float],
    max_results: int = 40,
    prix_m2_base: float | None = None,  # conserve pour compat. signature (plus utilise, aucun mode demo)
) -> dict:
    """Retourne les annonces réelles à afficher sur la zone visible.

    Tente RapidAPI UNIQUEMENT si settings.annonces_rapidapi_enabled est
    explicitement True (voir app/core/config.py — désactivé par défaut :
    les wrappers testés facturent dès le premier appel, même avec une clé
    valide). Si désactivé, non configuré, ou en cas d'échec du wrapper,
    renvoie une liste VIDE avec la raison — jamais de données fabriquées,
    jamais d'appel facturable silencieux.
    """
    if not settings.annonces_rapidapi_enabled:
        return {
            "source": "none",
            "listings": [],
            "fallback_reason": "RapidAPI désactivé (ANNONCES_RAPIDAPI_ENABLED=false) — "
            "évite tout appel facturable non désiré. Seul DVF (gratuit) alimente la carte.",
        }

    if settings.annonces_rapidapi_key and settings.annonces_rapidapi_host:
        try:
            listings = await _call_rapidapi(bounds, max_results)
            return {"source": "rapidapi", "listings": listings}
        except Exception as exc:  # noqa: BLE001 - on ne casse jamais la carte, on renvoie juste vide
            return {
                "source": "none",
                "listings": [],
                "fallback_reason": f"{type(exc).__name__}: {exc}",
            }

    return {
        "source": "none",
        "listings": [],
        "fallback_reason": "ANNONCES_RAPIDAPI_KEY/HOST non renseignés — aucune source réelle disponible",
    }
