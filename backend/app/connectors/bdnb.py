"""
Caracteristiques physiques du bati via la BDNB (Base de Donnees Nationale
des Batiments) : geometrie, materiaux de structure/toiture, annee de
construction, etc.

En plus de la fiche par adresse (fetch_bdnb), ce module expose une requete
par emprise/viewport (fetch_buildings_in_bbox) : tous les groupes de
batiments intersectant une bounding box, reduits a l'empreinte + la hauteur
moyenne — suffisant pour une extrusion MapLibre `fill-extrusion` (vue 2D/3D
de l'etape Cartographie).

Procedure en 2 appels (confirmee via usage reel de l'API, cf.
docs/GUIDE_ORCHESTRATEUR_API.md) :

  1. Geocodeur propre a BDNB (different du geocodeur BAN utilise ailleurs
     dans ce projet) :
       GET https://api.bdnb.io/v1/bdnb/geocodage?q={adresse}
     -> le champ "id" de la meilleure correspondance est la
        "cle_interop_adr" (cle d'interoperabilite adresse), de la forme
        "37031_xxxx_00026" (code INSEE commune + identifiant de voie +
        numero).

  2. Donnees du/des groupe(s) de batiments a cette adresse EXACTE :
       GET https://api.bdnb.io/v1/bdnb/donnees/batiment_groupe_complet/adresse
           ?cle_interop_adr=eq.{id}
     -> renvoie directement les groupes de batiments a cette adresse
        precise. Plus besoin de deviner le batiment le plus proche dans
        toute la commune (approche abandonnee).

L'offre "Open" de BDNB ne necessite aucune cle API pour ces deux appels
(confirme par un test reel : les deux requetes fonctionnent sans en-tete
Authorization). Si BDNB_API_KEY est renseignee dans .env (ex. pour
beneficier d'un quota plus eleve), elle est ajoutee automatiquement ;
sinon les appels partent sans en-tete, sans bloquer le diagnostic.
Aucune donnee n'est simulee ici : si l'adresse n'est pas trouvee par le
geocodeur BDNB, une exception explicite est levee et remontee comme
source en erreur par collector_agent, plutot que de renvoyer un resultat
invente.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from pyproj import CRS, Transformer

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lambert-93 (EPSG:2154, CRS natif de la BDNB) -> WGS84 (EPSG:4326, CRS de MapLibre).
_L93_TO_WGS84 = Transformer.from_crs(CRS.from_epsg(2154), CRS.from_epsg(4326), always_xy=True)
_WGS84_TO_L93 = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(2154), always_xy=True)


class BdnbAdresseIntrouvable(RuntimeError):
    pass


def _headers() -> dict:
    if settings.bdnb_api_key:
        return {"Authorization": f"Bearer {settings.bdnb_api_key}"}
    return {}


async def _geocode_bdnb(client: httpx.AsyncClient, address: str) -> str:
    """Etape 1 : geocodeur BDNB -> cle_interop_adr de la meilleure correspondance."""
    response = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/geocodage",
        params={"q": address},
        headers=_headers(),
    )
    response.raise_for_status()
    data = response.json()

    # La forme exacte (liste brute, ou objet avec "results"/"features") peut
    # varier selon la version de l'API : on gere les variantes plausibles
    # plutot que de supposer un seul format et de planter dessus.
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results") or data.get("features") or [data]
    else:
        results = []

    if not results:
        raise BdnbAdresseIntrouvable(f"Geocodeur BDNB : aucun resultat pour {address!r}")

    best = results[0]
    # Confirme par un test reel : ce geocodeur repond avec un objet GeoJSON
    # Feature (`{"type": "Feature", "properties": {"id": "...", ...}}`), pas
    # une liste plate avec "id" au premier niveau. On verifie donc aussi
    # dans "properties" avant d'abandonner.
    properties = best.get("properties") if isinstance(best.get("properties"), dict) else {}
    cle_interop_adr = (
        best.get("id")
        or best.get("cle_interop_adr")
        or properties.get("id")
        or properties.get("cle_interop_adr")
    )
    if not cle_interop_adr:
        raise BdnbAdresseIntrouvable(
            f"Geocodeur BDNB : champ 'id' absent de la reponse : {best!r}"
        )
    return cle_interop_adr


async def fetch_bdnb(client: httpx.AsyncClient, address: str) -> dict | None:
    """Retourne les donnees BDNB (geometrie, materiaux...) pour cette adresse exacte.

    Leve BdnbAdresseIntrouvable si le geocodeur BDNB ne trouve pas
    l'adresse. Retourne None (sans erreur) si l'adresse est geocodee mais
    qu'aucun batiment n'est associe a cette cle_interop_adr dans la BDNB.
    """
    cle_interop_adr = await _geocode_bdnb(client, address)

    response = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_complet/adresse",
        params={"cle_interop_adr": f"eq.{cle_interop_adr}"},
        headers=_headers(),
    )
    response.raise_for_status()
    rows = response.json()

    if not rows:
        return None

    return {
        "cle_interop_adr": cle_interop_adr,
        "batiment": rows[0],
        "autres_batiments_meme_adresse": rows[1:] if len(rows) > 1 else [],
    }


# ---------------------------------------------------------------------------
# Fiche complète d'un bâtiment par identifiant (clic sur la carte — story A2)
# ---------------------------------------------------------------------------

async def fetch_batiment_groupe(
    client: httpx.AsyncClient, batiment_groupe_id: str
) -> dict | None:
    """Retourne la fiche BDNB complète (batiment_groupe_complet) d'un groupe de
    bâtiments identifié par son `batiment_groupe_id` (ex. `bdnb-bg-XXXX-XXXX-XXXX`),
    plus les niveaux de risque bâtiment (`batiment_groupe_risques` : argile,
    radon, sismique) si disponibles.

    C'est l'endpoint derrière le clic sur une géométrie 3D (story A2 du MVP) :
    la couche bbox ne transporte que `batiment_groupe_id` + hauteur ; au clic,
    le frontend récupère ici la fiche complète pour alimenter le panneau.
    Retourne None si l'identifiant est inconnu (jamais d'exception).
    """
    response = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_complet",
        params={"batiment_groupe_id": f"eq.{batiment_groupe_id}"},
        headers=_headers(),
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None

    batiment = rows[0]

    # Risques bâtiment (argile / radon / sismique) — table publique BDNB Open.
    risques: dict | None = None
    try:
        risques_response = await client.get(
            f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_risques",
            params={"batiment_groupe_id": f"eq.{batiment_groupe_id}"},
            headers=_headers(),
        )
        risques_response.raise_for_status()
        risques_rows = risques_response.json()
        if risques_rows:
            risques = risques_rows[0]
    except Exception:
        # Non bloquant : la fiche reste exploitable sans le tableau risques.
        risques = None

    return {"batiment": batiment, "risques": risques}


# ---------------------------------------------------------------------------
# Requete par emprise (viewport MapLibre) — bâtiments extrudés en 2D/3D
# ---------------------------------------------------------------------------

def _reproject_geometry(geometry: dict) -> dict:
    """Reprojette une geometrie GeoJSON (Polygon/MultiPolygon) de Lambert-93
    vers WGS84, en conservant la structure. Retourne la geometrie telle quelle
    si le type est inconnu (on ne fait jamais planter la couche pour un cas
    atypique)."""
    def reproject_ring(ring: list) -> list:
        return [list(_L93_TO_WGS84.transform(x, y)) for x, y in ring]

    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [reproject_ring(ring) for ring in polygon] for polygon in coords
            ],
        }
    if geom_type == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [reproject_ring(ring) for ring in coords],
        }
    return geometry


# Cache en mémoire des requêtes bbox (clé = bbox arrondie + limit, TTL 5 min) :
# les moveend du frontend réinterrogent la même zone au cours du déplacement, et
# le tier Open (sans clé) rate-limite vite les appels séquentiels. Un cache côté
# serveur évite de re-paginer 10×10 lignes pour une même fenêtre.
_BBOX_CACHE: dict[str, tuple[float, dict]] = {}
_BBOX_CACHE_TTL = 300.0


def _bbox_cache_key(west: float, south: float, east: float, north: float, limit: int) -> str:
    return f"{west:.4f},{south:.4f},{east:.4f},{north:.4f},{limit}"


async def fetch_buildings_in_bbox(
    client: httpx.AsyncClient,
    west: float,
    south: float,
    east: float,
    north: float,
    limit: int = 800,
) -> dict:
    """Retourne une GeoJSON FeatureCollection des groupes de batiments BDNB
    dont l'empreinte intersecte la bounding box (WGS84), reprojetee en 4326.

    Chaque feature ne porte que ce dont l'extrusion a besoin :
    `batiment_groupe_id` (identification / surbrillance) et `hauteur_mean`
    (metres, hauteur moyenne du groupe). Les resultats sont plafonnes a
    `limit` ; `limit <= 0` signifie « tous » : on pagine jusqu'a epuisement
    (plafond de securite 10 000 pour ne pas marteler le tier Open).

    L'API BDNB (PostgREST + PostGIS) accepte un filtre spatial via
    l'operateur `ov` (overlap, bbox) : `geom_groupe=ov.SRID=2154;POLYGON(...)`.
    """
    if limit < 1:
        limit = 10000
    limit = min(limit, 10000)

    # Bbox WGS84 -> polygone Lambert-93 (les 4 coins reprojetes suffisent pour
    # une intersection de bbox ; l'operateur `ov` travaille sur les bboxes).
    corners = [
        _WGS84_TO_L93.transform(west, south),
        _WGS84_TO_L93.transform(east, south),
        _WGS84_TO_L93.transform(east, north),
        _WGS84_TO_L93.transform(west, north),
    ]
    ring = "POLYGON((" + ",".join(f"{x:.1f} {y:.1f}" for x, y in corners) + f",{corners[0][0]:.1f} {corners[0][1]:.1f}))"
    wkt = f"SRID=2154;{ring}"

    # Cache : la même fenêtre re-demandée dans la minute est servie sans
    # re-paginer (le tier Open rate-limite vite les appels séquentiels).
    cache_key = _bbox_cache_key(west, south, east, north, limit)
    cached = _BBOX_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _BBOX_CACHE_TTL:
        return cached[1]

    # L'API BDNB plafonne chaque requete a 10 lignes (quota Open, sans cle) :
    # on pagine par offset jusqu'a `limit` (ou jusqu'a epuisement si
    # `limit <= 0` — la boucle s'arrete quand une page retourne < 10 lignes).
    page_size = 10
    max_pages = (limit + page_size - 1) // page_size
    seen: set[str] = set()
    features = []

    for page in range(max_pages):
        offset = page * page_size
        try:
            response = await _get_bdnb_page(client, wkt, offset, page_size)
        except httpx.HTTPStatusError as exc:
            # Tier Open rate-limite les rafales : on rend ce qu'on a deja
            # pagine plutot que de faire echouer toute la couche (0 bâtiment).
            logger.warning(
                "  [bdnb bbox] page %d rate-limitee (%s) -> retour partiel de %d batiments",
                page, exc.response.status_code, len(features),
            )
            break
        rows = response.json()
        if not rows:
            break
        for row in rows:
            geom = row.get("geom_groupe")
            if not isinstance(geom, dict) or not geom.get("coordinates"):
                continue
            bid = row.get("batiment_groupe_id")
            if bid in seen:
                continue
            seen.add(bid)
            features.append(
                {
                    "type": "Feature",
                    "geometry": _reproject_geometry(geom),
                    "properties": {
                        "batiment_groupe_id": bid,
                        "hauteur_mean": row.get("hauteur_mean"),
                    },
                }
            )
            if len(features) >= limit:
                break
        if len(features) >= limit or len(rows) < page_size:
            break

    result = {"type": "FeatureCollection", "features": features}
    _BBOX_CACHE[cache_key] = (time.monotonic(), result)
    return result


async def _get_bdnb_page(
    client: httpx.AsyncClient, wkt: str, offset: int, page_size: int
) -> httpx.Response:
    """Une page de la pagination bbox, avec un seul retry court sur 429/5xx
    (le tier Open sans cle est rate-limite par rafales)."""
    for attempt in range(2):
        response = await client.get(
            f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_complet",
            params={
                "select": "batiment_groupe_id,hauteur_mean,geom_groupe",
                "limit": page_size,
                "offset": offset,
                "order": "batiment_groupe_id",
                "geom_groupe": f"ov.{wkt}",
            },
            headers=_headers(),
        )
        if response.status_code in (429, 500, 502, 503) and attempt == 0:
            await asyncio.sleep(0.8)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("BDNB bbox : retry epuise")  # pragma: no cover
