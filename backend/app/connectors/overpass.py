"""
Connecteur Overpass API (OpenStreetMap) — détection du type de bâtiment.

Interroge Overpass pour déterminer si l'adresse correspond à une usine,
un bâtiment industriel, un entrepôt, ou un bâtiment résidentiel normal.

API : https://overpass-api.de/api/interpreter (publique, gratuite, sans clé)
Limite : ~1 requête / 5 secondes par IP (usage raisonnable).

Tags OSM utilisés :
  - building=industrial / building=warehouse / building=manufacture → industriel
  - man_made=works / man_made=storage_tank / man_made=silo → industriel
  - landuse=industrial → zone industrielle
  - building=house / building=residential / building=apartments → résidentiel
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tags OSM indiquant un bâtiment industriel
TAGS_INDUSTRIELS = {
    "building": {"industrial", "warehouse", "manufacture", "factory", "hangar"},
    "man_made": {"works", "storage_tank", "silo", "chimney", "water_tower"},
    "landuse": {"industrial", "commercial"},
}

# Tags OSM indiquant un bâtiment résidentiel
TAGS_RESIDENTIELS = {
    "building": {"house", "residential", "apartments", "detached", "terrace", "semidetached_house"},
}


async def detecter_type_batiment_osm(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    rayon_m: int = 200,
) -> dict:
    """Détecte le type de bâtiment via Overpass API autour des coordonnées.

    Retourne :
      - type : "industriel" | "residentiel" | "inconnu"
      - confiance : float (0-1)
      - tags : dict des tags OSM trouvés
      - nom : nom du bâtiment si disponible
      - erreur : str | None
    """
    # Requête Overpass : bâtiments dans un rayon autour du point
    query = f"""
    [out:json][timeout:15];
    (
      way(around:{rayon_m},{lat},{lon})["building"];
      way(around:{rayon_m},{lat},{lon})["man_made"];
      way(around:{rayon_m},{lat},{lon})["landuse"="industrial"];
      relation(around:{rayon_m},{lat},{lon})["landuse"="industrial"];
    );
    out tags;
    """

    try:
        resp = await client.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=20.0,
            headers={"User-Agent": "Typhoon2-Risk/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("overpass -- échec pour (%.5f, %.5f) : %s", lat, lon, exc)
        return {"type": "inconnu", "confiance": 0.0, "tags": {}, "nom": None, "erreur": str(exc)}
    except Exception as exc:
        logger.warning("overpass -- erreur inattendue : %s", exc)
        return {"type": "inconnu", "confiance": 0.0, "tags": {}, "nom": None, "erreur": str(exc)}

    elements = data.get("elements", [])
    if not elements:
        return {"type": "inconnu", "confiance": 0.0, "tags": {}, "nom": None, "erreur": None}

    # Analyser les tags des éléments trouvés
    score_industriel = 0
    score_residentiel = 0
    tags_trouves: dict = {}
    nom_trouve = None

    for el in elements:
        tags = el.get("tags", {})
        if not tags:
            continue

        # Mémoriser les tags pour le retour
        for k, v in tags.items():
            if k in ("building", "man_made", "landuse", "name", "industrial", "product"):
                tags_trouves[k] = v

        # Nom du bâtiment
        if not nom_trouve:
            nom_trouve = tags.get("name") or tags.get("operator") or tags.get("brand")

        # Score industriel
        building = tags.get("building", "")
        if building in TAGS_INDUSTRIELS["building"]:
            score_industriel += 3
        man_made = tags.get("man_made", "")
        if man_made in TAGS_INDUSTRIELS["man_made"]:
            score_industriel += 3
        landuse = tags.get("landuse", "")
        if landuse in TAGS_INDUSTRIELS["landuse"]:
            score_industriel += 2
        if tags.get("industrial") or tags.get("product"):
            score_industriel += 2

        # Score résidentiel
        if building in TAGS_RESIDENTIELS["building"]:
            score_residentiel += 2

    # Décision
    if score_industriel > score_residentiel and score_industriel >= 2:
        type_detecte = "industriel"
        confiance = min(score_industriel / 5.0, 1.0)
    elif score_residentiel > 0:
        type_detecte = "residentiel"
        confiance = min(score_residentiel / 3.0, 1.0)
    else:
        type_detecte = "inconnu"
        confiance = 0.0

    logger.info(
        "overpass -- type=%s confiance=%.2f tags=%s nom=%r",
        type_detecte, confiance, tags_trouves, nom_trouve,
    )

    return {
        "type": type_detecte,
        "confiance": round(confiance, 2),
        "tags": tags_trouves,
        "nom": nom_trouve,
        "erreur": None,
    }