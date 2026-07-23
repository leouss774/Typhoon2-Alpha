"""
Pipeline de collecte de données de risque pour une adresse en France.

Objectif : à partir d'une adresse texte, produire UN SEUL fichier JSON
contenant TOUTES les données brutes de risque disponibles, SANS calcul de
score (le score sera géré par une autre partie du projet / une autre
personne de l'équipe).

Étapes :
    1. Géocodage de l'adresse -> (latitude, longitude, code INSEE) via l'API
       Adresse (Base Adresse Nationale, data.gouv.fr) — gratuite, sans clé.
    2. Géorisques (BRGM) -> RGA, sismicité, inondation (AZI/CatNat/TRI/PPR),
       mouvements de terrain, cavités, radon, ICPE, sites pollués.
    3. IGN (Géoplateforme) -> altitude au point (API gratuite, sans clé).
    4. Hub'Eau -> nappes phréatiques, hydrométrie (débits rivières), qualité
       des eaux (gratuit, sans clé, mais paramètres à vérifier sur la doc).
    5. OpenStreetMap (Overpass API) -> distances aux éléments naturels
       (forêt, cours d'eau, littoral) — gratuit, sans clé.
    6. Stubs clairement marqués TODO pour les sources qui nécessitent une
       inscription / clé API et un traitement de données plus lourd
       (DRIAS/Météo-France, Copernicus CDS, Sentinel, INSEE, BRGM
       géologie avancée, ONRN) : elles ne peuvent pas être appelées avec un
       simple `requests.get` sans identifiants, donc on ne les invente pas.

Dépendances : requests
    pip install requests

Auteur : projet de stage Talan
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

import requests


# ---------------------------------------------------------------------------
# 1. GÉOCODAGE — API Adresse (Base Adresse Nationale)
# ---------------------------------------------------------------------------

ADRESSE_API_URL = "https://api-adresse.data.gouv.fr/search/"


@dataclass
class GeocodedAddress:
    label: str
    latitude: float
    longitude: float
    code_insee: str
    score: float


def geocoder_adresse(adresse: str) -> GeocodedAddress:
    """Transforme une adresse texte en coordonnées + code INSEE de la commune."""
    resp = requests.get(ADRESSE_API_URL, params={"q": adresse, "limit": 1}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        raise ValueError(f"Aucune adresse trouvée pour : {adresse!r}")

    feat = features[0]
    lon, lat = feat["geometry"]["coordinates"]
    props = feat["properties"]

    return GeocodedAddress(
        label=props.get("label", adresse),
        latitude=lat,
        longitude=lon,
        code_insee=props.get("citycode", ""),
        score=props.get("score", 0.0),
    )


# ---------------------------------------------------------------------------
# 2. GÉORISQUES — API v1 (BRGM) — https://georisques.gouv.fr/doc-api
# ---------------------------------------------------------------------------

GEORISQUES_BASE_URL = "https://georisques.gouv.fr/api/v1"
RAYON_DEFAUT_M = 1000

_dernier_appel_georisques: dict[str, float] = {}


def _throttle(cle: str, delai_min: float) -> None:
    """Attend si nécessaire pour respecter un délai minimum entre deux appels."""
    maintenant = time.monotonic()
    dernier = _dernier_appel_georisques.get(cle, 0.0)
    attente = delai_min - (maintenant - dernier)
    if attente > 0:
        time.sleep(attente)
    _dernier_appel_georisques[cle] = time.monotonic()


def _get_georisques(endpoint: str, params: dict[str, Any]) -> list[dict]:
    """Appel générique à un endpoint Géorisques, normalisé en liste de dicts.

    - {"data": [...]}         -> la liste
    - objet unique {...}      -> enveloppé dans une liste à 1 élément
    - déjà une liste           -> inchangé
    - erreur réseau/HTTP/404  -> [] (le pipeline continue, ne plante jamais)
    """
    _throttle("default", 1 / 5)
    url = f"{GEORISQUES_BASE_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[georisques] Avertissement — endpoint '{endpoint}' indisponible : {exc}")
        return []

    donnees: Any = payload.get("data", payload) if isinstance(payload, dict) else payload

    if isinstance(donnees, dict):
        donnees = [donnees]
    elif not isinstance(donnees, list):
        donnees = []

    return donnees


def get_resultats_rapport_risque(lat: float, lon: float) -> dict[str, Any]:
    """Rapport consolidé des risques Géorisques (remplace l'ancien PPR obsolète).

    L'endpoint v1 officiel couvre les risques réglementaires et les éléments
    d'aléa de façon plus robuste que l'ancien endpoint PPR.
    """
    _throttle("resultats_rapport_risque", 1 / 1)
    url = "https://www.georisques.gouv.fr/api/v1/resultats_rapport_risque"
    try:
        resp = requests.get(
            url,
            params={"latlon": f"{lon},{lat}"},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[georisques] Avertissement — resultats_rapport_risque indisponible : {exc}")
        return {}


def get_risques_georisques(lat: float, lon: float, code_insee: str) -> dict[str, Any]:
    """Interroge les couches Géorisques et renvoie les données BRUTES par thématique.

    NB : les noms de routes ci-dessous datent de la doc publique au moment de
    l'écriture. Si un endpoint renvoie 404 de façon persistante, vérifiez le
    nom exact et les paramètres attendus sur https://www.georisques.gouv.fr/doc-api
    (Swagger interactif), l'API évoluant régulièrement.
    """
    latlon = f"{lon},{lat}"

    return {
        # Sismicité — zonage réglementaire par commune (1 à 5)
        "zonage_sismique": _get_georisques("zonage_sismique", {"code_insee": code_insee}),

        # Retrait-gonflement des argiles (RGA) -> objet unique
        # {"codeExposition": "0-3", "exposition": "..."}
        "argiles_rga": _get_georisques("rga", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # Inondation : atlas des zones inondables + arrêtés catastrophe naturelle
        # + territoires à risque important d'inondation
        "azi": _get_georisques("gaspar/azi", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),
        "catnat": _get_georisques("gaspar/catnat", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),
        "tri": _get_georisques("gaspar/tri", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # Rapport consolidé de risques (remplace l'ancien endpoint PPR obsolète
        # qui n'est plus disponible sur l'API v1).
        "rapport_risque": get_resultats_rapport_risque(lat, lon),

        # Mouvements de terrain (BDMvT)
        "mouvements_terrain": _get_georisques("mvt", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # Cavités souterraines
        "cavites": _get_georisques("cavites", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # Potentiel radon (classe 1 à 3, par commune)
        "radon": _get_georisques("radon", {"code_insee": code_insee}),

        # Installations classées à proximité (ICPE)
        "icpe": _get_georisques("installations_classees", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # Sites et sols pollués (SSP)
        "sites_sols_pollues": _get_georisques("ssp", {"latlon": latlon, "rayon": RAYON_DEFAUT_M}),

        # TODO équipe : "feux de forêt" (aléa dédié) et "OLD" (obligation légale
        # de débroussaillement) ne correspondent à aucun endpoint confirmé dans
        # la doc Géorisques v1 au moment de l'écriture. Le risque incendie de
        # forêt apparaît en partie dans "ppr" ci-dessus (type de PPR). Pour l'OLD,
        # vérifier la disponibilité d'une couche dédiée sur georisques.gouv.fr
        # ou data.gouv.fr avant de l'ajouter ici.
    }


# ---------------------------------------------------------------------------
# 3. IGN — Géoplateforme (altimétrie) — https://geoservices.ign.fr
# ---------------------------------------------------------------------------

IGN_ALTI_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"


def get_ign_altitude(lat: float, lon: float) -> dict[str, Any]:
    """Altitude au point donné via l'API Altimétrie IGN (gratuite, sans clé).

    NB : cette API ne donne que l'altitude ponctuelle. Le calcul de pente
    et d'exposition nécessite un traitement de MNT (raster) et n'est pas
    disponible via un simple appel REST -> voir TODO plus bas
    (get_ign_pente_exposition).
    """
    params = {
        "lon": lon,
        "lat": lat,
        "resource": "ign_rge_alti_wld",
        "indent": "false",
    }
    try:
        resp = requests.get(IGN_ALTI_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[ign] Avertissement — altimétrie indisponible : {exc}")
        return {}


def get_ign_pente_exposition(lat: float, lon: float) -> dict[str, Any]:
    """TODO équipe : la pente et l'exposition (orientation du terrain) se
    calculent à partir d'un Modèle Numérique de Terrain (MNT) — cela demande
    de télécharger une dalle RGE ALTI (IGN, gratuit) et de la traiter avec
    une lib type rasterio/numpy (dérivées locales), pas un simple appel API.
    Laissé en stub pour ne pas produire une donnée inventée.
    """
    return {}


# ---------------------------------------------------------------------------
# 4. HUB'EAU — https://hubeau.eaufrance.fr (gratuit, sans clé)
# ---------------------------------------------------------------------------

HUBEAU_BASE_URL = "https://hubeau.eaufrance.fr/api/v1"


def _get_hubeau(path: str, params: dict[str, Any]) -> list[dict]:
    """Appel générique à un sous-service Hub'Eau. Même logique défensive que
    Géorisques : ne plante jamais, renvoie [] en cas d'erreur/format inattendu.

    ATTENTION équipe : Hub'Eau regroupe plusieurs API indépendantes
    (piézométrie, hydrométrie, qualité des nappes, qualité des rivières...)
    dont les noms de champs et paramètres diffèrent. Vérifier chaque
    endpoint sur https://hubeau.eaufrance.fr/page/api-piezometrie (etc.)
    avant mise en prod.
    """
    url = f"{HUBEAU_BASE_URL}/{path}"
    try:
        resp = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[hubeau] Avertissement — endpoint '{path}' indisponible : {exc}")
        return []

    donnees = payload.get("data", []) if isinstance(payload, dict) else payload
    return donnees if isinstance(donnees, list) else []


def _bbox_autour_point(lat: float, lon: float, delta_deg: float = 0.05) -> str:
    """Construit une bbox simple (lon_min,lat_min,lon_max,lat_max) autour d'un point."""
    return f"{lon - delta_deg},{lat - delta_deg},{lon + delta_deg},{lat + delta_deg}"


def get_hubeau_nappes(lat: float, lon: float, code_insee: str) -> dict[str, Any]:
    """Stations piézométriques (niveaux de nappes) à proximité + dernières
    chroniques disponibles."""
    stations = _get_hubeau(
        "niveaux_nappes/stations",
        {"bbox": _bbox_autour_point(lat, lon), "size": 5},
    )
    return {"stations_piezometrie": stations}


def get_hubeau_hydrometrie(lat: float, lon: float) -> dict[str, Any]:
    """TODO : l'hydrométrie n'est pas disponible de façon stable via l'API v1.

    On retourne un objet vide explicite pour éviter de produire une donnée
    inventée et conserver un pipeline robuste.
    """
    return {
        "stations_hydrometrie": [],
        "source_status": "TODO - service hydrométrie non couvert par l'API Hub'Eau v1 stable",
    }


def get_hubeau_qualite_eaux(code_insee: str) -> dict[str, Any]:
    qualite_nappes = _get_hubeau(
        "qualite_nappes/analyses",
        {"code_insee": code_insee, "size": 10},
    )
    return {
        "qualite_eaux_souterraines": qualite_nappes,
        "stations_qualite_rivieres": [],
        "qualite_eaux_superficielles": [],
        "source_status": "TODO - services qualité des rivières non disponibles via l'API Hub'Eau v1 stable",
    }
# ---------------------------------------------------------------------------
# 5. OPENSTREETMAP — Overpass API (gratuit, sans clé)
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def get_osm_proximite(lat: float, lon: float, rayon_m: int = 3000) -> dict[str, Any]:
    """Recherche les éléments naturels les plus proches (forêt, cours d'eau,
    littoral) dans un rayon donné via Overpass API, et calcule une distance
    approximative (à vol d'oiseau) en mètres.

    NB : Overpass est un service communautaire gratuit mais avec des quotas
    d'usage raisonnables (pas d'appels massifs) et demande un User-Agent.
    """
    query = f"""
    [out:json][timeout:25];
    (
      way["natural"="wood"](around:{rayon_m},{lat},{lon});
      way["landuse"="forest"](around:{rayon_m},{lat},{lon});
      way["waterway"](around:{rayon_m},{lat},{lon});
      way["natural"="coastline"](around:{rayon_m},{lat},{lon});
    );
    out center;
    """
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": "talan-risque-adresse/1.0"},
            timeout=25,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"[osm] Avertissement — Overpass indisponible : {exc}")
        return {}

    def distance_m(lat2: float, lon2: float) -> float:
        # Formule de Haversine
        r = 6371000
        phi1, phi2 = math.radians(lat), math.radians(lat2)
        dphi = math.radians(lat2 - lat)
        dlambda = math.radians(lon2 - lon)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    plus_proche: dict[str, dict[str, Any]] = {}
    for el in elements:
        centre = el.get("center")
        if not centre:
            continue
        d = distance_m(centre["lat"], centre["lon"])
        tags = el.get("tags", {})
        if "waterway" in tags:
            categorie = "cours_eau"
        elif tags.get("natural") == "coastline":
            categorie = "littoral"
        else:
            categorie = "foret"

        if categorie not in plus_proche or d < plus_proche[categorie]["distance_m"]:
            plus_proche[categorie] = {"distance_m": round(d), "id_osm": el.get("id")}

    return {"elements_naturels_proches": plus_proche}


# ---------------------------------------------------------------------------
# 6. STUBS — sources nécessitant une inscription / clé API
# ---------------------------------------------------------------------------

def get_drias_meteofrance(lat: float, lon: float) -> dict[str, Any]:
    """TODO équipe : projections climatiques DRIAS (température, sécheresse,
    précipitations, vagues de chaleur, horizons 2030/2050/2100).
    Les données DRIAS sont distribuées via https://www.drias-climat.fr en
    téléchargement (NetCDF/CSV par maille), pas via une API REST publique
    simple avec lat/lon -> nécessite un script de traitement dédié une fois
    les fichiers de la maille correspondante téléchargés."""
    return {}


def get_copernicus(lat: float, lon: float) -> dict[str, Any]:
    """TODO équipe : Copernicus Climate Data Store (CDS) — température du
    sol, humidité, sécheresse, végétation, évapotranspiration, neige, etc.
    Nécessite un compte + clé API CDS et le package `cdsapi`
    (https://cds.climate.copernicus.eu/api-how-to). Les requêtes sont
    asynchrones (mise en file d'attente), pas un simple GET."""
    return {}


def get_sentinel(lat: float, lon: float) -> dict[str, Any]:
    """TODO équipe : imagerie satellite Sentinel (végétation, humidité,
    imperméabilisation des sols). Accessible via Copernicus Data Space
    Ecosystem (https://dataspace.copernicus.eu) — nécessite un compte et un
    traitement d'images (pas un endpoint direct par adresse)."""
    return {}


def get_insee_contexte(code_insee: str) -> dict[str, Any]:
    """TODO équipe : statistiques locales (densité, ancienneté du bâti,
    revenus, population). Nécessite un compte développeur INSEE (OAuth,
    gratuit) sur https://api.insee.fr — clé non incluse ici."""
    return {}


def get_brgm_geologie_avancee(lat: float, lon: float) -> dict[str, Any]:
    """TODO équipe : données géologiques BRGM plus fines (nature des sols,
    roche, profondeur, hydrogéologie) au-delà du RGA déjà couvert par
    Géorisques -> voir les services BRGM InfoTerre
    (https://infoterre.brgm.fr) qui exposent des flux WMS/WFS plus complexes
    qu'un simple GET JSON."""
    return {}


def get_onrn(code_insee: str) -> dict[str, Any]:
    """TODO équipe : Observatoire National des Risques Naturels — fréquence
    et coût des sinistres, ratio sinistres/primes par commune. Les données
    ONRN sont majoritairement diffusées en jeux de données statiques sur
    data.gouv.fr / georisques.gouv.fr plutôt que via une API REST par
    adresse -> à identifier le bon jeu de données avant intégration."""
    return {}


# ---------------------------------------------------------------------------
# PIPELINE COMPLET — sortie JSON brute, sans score
# ---------------------------------------------------------------------------

def analyser_adresse(adresse: str) -> dict[str, Any]:
    """Fonction d'entrée : adresse texte -> dictionnaire de toutes les
    données de risque brutes disponibles (aucun calcul de score ici)."""
    geo = geocoder_adresse(adresse)
    print(f"Adresse géocodée : {geo.label} ({geo.latitude:.5f}, {geo.longitude:.5f}) — INSEE {geo.code_insee}")

    return {
        "adresse": geo.label,
        "coordonnees": {"latitude": geo.latitude, "longitude": geo.longitude},
        "code_insee": geo.code_insee,
        "score_geocodage": geo.score,
        "georisques": get_risques_georisques(geo.latitude, geo.longitude, geo.code_insee),
        "ign": {
            "altitude": get_ign_altitude(geo.latitude, geo.longitude),
            "pente_exposition": get_ign_pente_exposition(geo.latitude, geo.longitude),
        },
        "hubeau": {
            **get_hubeau_nappes(geo.latitude, geo.longitude, geo.code_insee),
            **get_hubeau_hydrometrie(geo.latitude, geo.longitude),
            **get_hubeau_qualite_eaux(geo.code_insee),
        },
        "osm": get_osm_proximite(geo.latitude, geo.longitude),
        "drias_meteofrance": get_drias_meteofrance(geo.latitude, geo.longitude),
        "copernicus": get_copernicus(geo.latitude, geo.longitude),
        "sentinel": get_sentinel(geo.latitude, geo.longitude),
        "insee": get_insee_contexte(geo.code_insee),
        "brgm_geologie_avancee": get_brgm_geologie_avancee(geo.latitude, geo.longitude),
        "onrn": get_onrn(geo.code_insee),
    }


def sauvegarder_json(resultat: dict[str, Any], chemin: str = "risques_adresse.json") -> str:
    """Écrit le résultat complet dans un fichier JSON et renvoie le chemin."""
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)
    return chemin


if __name__ == "__main__":
    resultat = analyser_adresse("8 boulevard du Port, 44000 Nantes")
    chemin = sauvegarder_json(resultat, "risques_adresse.json")
    print(f"\nFichier JSON généré : {chemin}")