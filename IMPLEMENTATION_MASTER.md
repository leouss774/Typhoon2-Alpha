# Typhoon — Implémentation complète GEE-like + réparation Zone Risk (backend + frontend)

Document exécutable, dans l'ordre. Deux fronts sont couverts car ils
partagent le même backend :

- **`frontend/promoteurs/`** (carte "Zone Risk" par grille) → Partie A, Phases R0-R3,
  **à traiter en premier** : câblé sur une route inexistante et un port erroné,
  ce front ne peut pas afficher de résultat aujourd'hui.
- **`frontend/jumeau_numerique/`** (carte adresse unique + jumeau 3D, style GEE) → Partie B, Phases 0-5.

## Réconciliation v2 (corrections vs v1 — toutes vérifiées sur `feature/restructure`)

La v1 de ce document contenait des inexactitudes qui ont été corrigées après
relecture du code réel (audit `docs/audit_zone_risk_promoteurs.md`, 01/08/2026) :

| # | Point v1 | Réalité vérifiée | Correction |
|---|----------|------------------|------------|
| 1 | Partie B supposait **Mapbox GL** (`mapboxgl`, styles Mapbox, projection pour "Mapbox") | Les deux fronts utilisent **MapLibre GL 4.7.1** (`maplibregl`, unpkg) — `jumeau_numerique/index.html:11-12` | Tout le code B est écrit en `maplibregl` ; aucune dépendance Mapbox nulle part |
| 2 | Partie B mentionnait `typhoon_gee_shell.html` et `frontend/jumeau_numerique/property-id/index.html` | Ces fichiers **n'existent pas**. La carte single-adresse vit dans `frontend/jumeau_numerique/index.html` (bloc `zoneMap`, l.4517+) ; la page certification est `frontend/property-id/index.html` | Toutes les cibles B pointent vers `jumeau_numerique/index.html` |
| 3 | Partie B/Phase 0 ajoutait `pyproj` + `projection.py` | `footprint.py` implémente **déjà** `lambert93_to_wgs84(x, y)` (l.515) et `wgs84_to_lambert93` (l.540), en pur Python, sans dépendance géo | Réutiliser `footprint.lambert93_to_wgs84` ; **pas de `pyproj`**, pas de nouveau module |
| 4 | Partie B/Phase 1 câblait via `api_routes.__init__` → `api_router.include_router(...)` | `backend/app/api/routes/__init__.py` est **vide** ; chaque route est enregistrée par `app.include_router(...)` dans `backend/app/main.py:40-44` | Nouveaux routers enregistrés dans `main.py` |
| 5 | Phase 2 lisait des clés Géorisques `azi`/`mvt` | `fetch_georisques(client, citycode, lat, lon, rayon_m=1000)` (georisques.py:41) renvoie : `risques_commune, catnat, zones_inondables, cavites, zonage_sismique, radon, mouvements_de_terrain, erreurs, lien_rapport_pdf` | `key_map` corrigé ; le mapping `azi→zones_inondables`, `mvt→mouvements_de_terrain` est interne |
| 6 | Phase 2 colorait en `eleve/modere/faible` | `_niveau_alerte` renvoie **`fort`/`moyen`/`faible`** (zone_scoring.py:121-126), pure, sans état simulé | Couches risques colorées `fort/moyen/faible` |
| 7 | Phase 4 lisait `data.altitude_m`, `data.dvf?.prix_m2_median`, `data.risque_inondation_niveau` | Le contrat `/diagnostic` (diagnostic_builder.py:112-153) n'a **ni** `altitude_m` **ni** `dvf.prix_m2_median` **ni** `risque_inondation_niveau` au niveau racine | Lire `data.zones.sous_sol.risque` ; altitude via nouvelle route `/api/altitude` (IGN `fetch_altitude`, ign_altitude.py:51) ; prix m² via route existante `/diagnostic/zone/prix` |
| 8 | Phase 5 créait `/api/layers/dvf` appelant `lookup_dvf_for_commune` | La fonction réelle est `lookup_dvf(citycode, max_rows=20)` (dvf_lookup.py:160) **sans géolocalisation** ; les ventes géolocalisées passent par `real_transactions_for_zone` (l.355) ; les stats par `zone_price_stats` (l.216). Les routes `POST /diagnostic/zone/prix` (diagnostic.py:252) et `POST /diagnostic/zone/annonces` existent déjà | **Supprimer** `/layers/dvf` : réutiliser `/diagnostic/zone/prix` (stats) + `/diagnostic/zone/annonces` (points réels) |
| 9 | Phase 5 DRIAS : "fichier local par département (`data/lookup/drias/`)" | `backend/data/lookup/drias/` **n'existe pas** | DRIAS = nouveau connecteur HTTP à concevoir (aucune donnée locale) |
| 10 | R0.2/R0.3/R0.4 codaient sur des signatures devinées | Signatures réelles vérifiées (voir Partie A) | Snippets corrigés aux signatures exactes |
| 11 | Partie A/R0.1 → `/diagnostic/zone` corps `{bounds, spacing_km, max_points, land_only}` | Confirmé `ZoneRequest` (diagnostic.py:189-199) ; réponse = `rating_zone_to_dict` (diagnostic.py:234) | RAS, mais le contrat de réponse (clés exactes) est maintenant documenté |

Sauf mention contraire ("NON CONFIRMÉ"), chaque phase ci-dessous a été relue
contre le code réel et est applicable telle quelle.

---

## PARTIE A — Réparation "Zone Risk" (`frontend/promoteurs/`)

Coût estimé Phase R0 : ~1 jour (câblage pur, aucune nouvelle donnée). Tant
que R0 n'est pas fait, ce front ne renvoie jamais de résultat.

### Phase R0 — Réparer le câblage

**Contrat backend réel (déjà en place, à NE PAS modifier)**
`POST /diagnostic/zone` — `backend/app/api/routes/diagnostic.py:202` :
- Requête : `{ bounds: [lat_min, lon_min, lat_max, lon_max], spacing_km (0.05-5.0, déf. 0.5), max_points (5-200, déf. 50), land_only (bool, déf. false) }`
- Réponse (`rating_zone_to_dict`, zone_scoring.py:547-577) : `nb_points, nb_points_valides, nb_points_erreur, score_moyen, score_pondere, rating_global, land_only, message, perils{...}, worst_case_peril, worst_case_score, points_echantillon[ {index, lat, lon, adresse_approx, score{score_global, inondation, rga, tempete, incendie, seisme}, erreur} ]`
- **Absents aujourd'hui** (ajoutés en R0.2-R0.4) : `rapport_promoteur`, `duree_evaluation_s`, `niveau_global` par point.

**R0.1 — Front : bonne URL, bon port, bon contrat**

`frontend/promoteurs/index.html` — `BACKEND_URL` (l.354) et handler `assessBtn` (l.729-757) :

```js
// AVANT (cassé) — l.354 et l.734
const BACKEND_URL = 'http://localhost:8765';
const resp = await fetch(`${BACKEND_URL}/api/v1/zone/assess`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ zone: state.bounds, spacing_km, max_points: 50, max_concurrency: 5, land_only, include_samples: true }),
});

// APRÈS (corrigé) — state.bounds = { lat_min, lon_min, lat_max, lon_max }
// NOTE PORT : l'URL RESTE sur 8765 — convention repo (README "port 8765 obligatoire",
// l'uvicorn est lancé avec --port 8765). Un audit antérieur préconisait 8000
// (défaut uvicorn) ; c'était FAUX et a cassé les fronts. Ne pas y revenir.
const BACKEND_URL = 'http://localhost:8765';
const resp = await fetch(`${BACKEND_URL}/diagnostic/zone`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    bounds: [state.bounds.lat_min, state.bounds.lon_min, state.bounds.lat_max, state.bounds.lon_max],
    spacing_km: parseFloat(spacingSelect.value),
    max_points: 50,
    land_only: modeSelect.value === 'land_only',
  }),
});
if (!resp.ok) throw new Error(`Évaluation échouée (${resp.status}) : ${await resp.text()}`);
const data = await resp.json();
```

> `max_concurrency` n'est **pas** un champ du `ZoneRequest` ; le backend fixe 5.
> L'ajouter au contrat backend (R1, point 2) si on veut l'exposer.

**R0.2 — Backend : rapport promoteur + accord accentué**

`_rating_from_mean` (zone_scoring.py:489-497) renvoie `"Eleve"/"Modere"/"Faible"`
(sans accent) alors que `promoteur_report.py` compare des libellés accentués
(`rating_lower == "élevé"`). Corriger à la source :

```python
# zone_scoring.py
def _rating_from_mean(mean_score: float, worst_case: float) -> str:
    """Retourne des libellés accentués, cohérents avec promoteur_report.py."""
    if worst_case >= 70:
        return "Élevé"
    if mean_score >= 45:
        return "Élevé"
    if mean_score >= 20:
        return "Modéré"
    return "Faible"
```

En défense en profondeur, rendre `promoteur_report.py` insensible aux
accents/casse (une future erreur de renommage ne recasse plus tout) :

```python
# promoteur_report.py — en tête de module
import unicodedata

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

# remplacer chaque `if rating_lower == "élevé":` par `if _norm(rating_lower) == "eleve":`
# (idem pour "modéré"/"modere", "faible"/"faible").
```

Brancher le rapport dans la **route** (pas dans `rating_zone_to_dict`, qui reste un
sérialiseur pur). Signature réelle de `generer_rapport_promoteur` — 8 paramètres,
`promoteur_report.py:257-266` ; sortie `PromoteurReport.to_dict()` — clés
`faisabilite_construction, impact_valeur_fonciere, perspective_assurabilite, notes`
(l.31-37) — exactement ce que lit le front (index.html:702-704) :

```python
# backend/app/api/routes/diagnostic.py — dans run_zone_diagnostic(), avant `return result` (l.236)
from app.scoring.promoteur_report import generer_rapport_promoteur

result = rating_zone_to_dict(rating)
rapport = generer_rapport_promoteur(
    score_moyen=rating.score_moyen,
    rating_global=rating.rating_global,
    perils=rating.perils,              # dict[str, DistributionPeril] BRUT, pas le dict sérialisé
    land_only=rating.land_only,
    worst_case_peril=rating.worst_case_peril,
    worst_case_score=rating.worst_case_score,
    nb_points_valides=rating.nb_points_valides,
    nb_points_erreur=rating.nb_points_erreur,
)
result["rapport_promoteur"] = rapport.to_dict()
```

> Pièges évités : ne PAS passer `perils_dict` (déjà sérialisé, les sous-fonctions
> accèdent à `dist.pct_critique` en attribut) ; ne PAS oublier `land_only`,
> `nb_points_valides`, `nb_points_erreur` (requis, sans défaut).

**R0.3 — Backend : `niveau_global` par point**

`_niveau_alerte(score)` existe (zone_scoring.py:121-126) : `≥70 → "fort"`,
`≥40 → "moyen"`, sinon `"faible"`. L'ajouter dans `_result_to_point_dict`
(l.522-533). `result` est un **dict** (sortie de `compute_risk_scores`) :

```python
def _result_to_point_dict(result: dict) -> dict | None:
    if not result:
        return None
    score_global = result.get("score_global", 0)
    return {
        "score_global": score_global,
        "niveau_global": _niveau_alerte(score_global),   # AJOUT
        "inondation": {"score": _peril_score_from_zones(result, "inondation")},
        "rga": {"score": _peril_score_from_zones(result, "rga")},
        "tempete": {"score": _peril_score_from_zones(result, "tempete")},
        "incendie": {"score": _peril_score_from_zones(result, "incendie")},
        "seisme": {"score": _peril_score_from_zones(result, "seisme")},
    }
```

**R0.4 — Backend : `duree_evaluation_s`**

`run_zone_risk_assessment` calcule déjà `duree = time.time() - t0` (zone_scoring.py:393)
mais ne l'attache pas au résultat :

```python
# zone_scoring.py — dataclass RatingZone (l.62-75)
class RatingZone:
    ...
    duree: float = 0.0                       # AJOUT

# zone_scoring.py — les DEUX constructions : l.401 (chemin échec total) et l.473 (nominal)
return RatingZone(..., duree=duree)          # dans les deux

# zone_scoring.py — rating_zone_to_dict (l.564-577)
"duree_evaluation_s": round(rz.duree, 2),    # AJOUT
```

**R0.5 — Frontend : couleurs `fort/moyen/faible` + points en erreur + vraie progression**

1. Aligner le vocabulaire de la couche `sample-dots` (l.448-454) sur `_niveau_alerte` :
```js
'circle-color': ['match', ['get', 'niveau'],
  'faible', '#1F9D6C',
  'moyen',  '#D98A2B',
  'fort',   '#C0392B',
  '#8B959D'],                                  // défaut : gris
```
   (le fallback `p.score.niveau_global || 'moyen'`, l.680, devient correct dès R0.3 ;
   le filtre `p.score && p.score.score_global !== undefined` continue d'exclure les points en erreur — on peut ajouter un point gris `#8B959D` pour eux si souhaité).
2. Remplacer la barre de progression simulée (`startLoading`, l.568-596 : `setInterval`
   factice bloqué à 90 %) par une vraie fin de tâche :
```js
// endLoading(interval) devient : stop du setInterval, puis
loadingBar.style.width = '100%';
loadingText.textContent = `Zone évaluée en ${data.duree_evaluation_s ?? '—'} s
  (${data.nb_points_valides}/${data.nb_points} points valides)`;
// et sampleInfo (l.690) : `… ${data.nb_points_erreur} en erreur` quand > 0
```
3. Remplacer l'`alert()` d'erreur (l.755) par un affichage inline (même style que `showSearchError` Partie B/Phase 1).

**R0.6 — Nettoyage rapide (faible risque)**

- `backend/app/main.py` : supprimer le **double appel** à `load_index()` — l.52 (non
  protégé) et l.57-59 (dans un `try/except`) ; ne garder que le bloc `try/except`.
- `backend/app/main.py:22-23` : import dupliqué (`from app.api.routes import ...`) —
  fusionner en une seule ligne.
- `frontend/promoteurs/index.html` mode "Parcelle" (l.230) : n'est pas câblé
  (ne fait rien ou `alert()`) — brancher dessus l'évaluation single-parcelle une fois
  R0-R1 finis, ou le masquer en attendant.

### Phase R1 — Vraies données par point

Aucun appel réseau réel n'a lieu en mode zone aujourd'hui (`collect_fn` jamais passé,
confirmé diagnostic.py:223-228) :

```python
# diagnostic.py, dans run_zone_diagnostic() :
from app.agents.collector_agent import collect

rating = await run_zone_risk_assessment(
    bounds=payload.bounds, spacing_km=payload.spacing_km,
    max_points=payload.max_points, land_only=payload.land_only,
    collect_fn=collect,   # AJOUT — active le chemin "vraies données"
)
```

Points d'attention :

1. **Budget temps** : avec `max_points=50` et des API externes à ~200-500 ms chacune,
   même avec `max_concurrency=5`, le total peut dépasser 30-60s. Réduire les défauts
   (`max_points` ≤ 20) ou ajouter un cache par coordonnées arrondies (TTL quelques heures).
2. **`max_concurrency` non transmis** — l'ajouter au `ZoneRequest` et le propager à
   `run_zone_risk_assessment` (paramètre existant, l.369).
3. **`land_only` réellement appliqué** : actuellement accepté mais inutilisé. Une fois
   `collect_fn` branché, transmettre un flag `skip_bdnb=land_only` au collecteur.
   > **NON CONFIRMÉ** : vérifier que `collect()` (collector_agent.py:102) accepte un
   > paramètre `skip_bdnb` (ou équivalent) ; sinon l'ajouter d'abord à sa signature.
4. **Scores par péril** : une fois `collect_fn` branché, le payload Géorisques contient
   les vrais aléas — les zones bâtiment (fondations/murs/toiture) décrivent la
   vulnérabilité, pas l'aléa ; les deux sont utiles mais distincts.

### Phase R2 — Zones réelles, DVF, annonces

- **Polygones réels** au lieu de rectangles : route commune
  `GET /api/commune-polygon/{code}` (contour INSEE via
  `geo.api.gouv.fr/communes/{code}?fields=contour&format=geojson`, même helper que
  Partie B/Phase 2), partagée entre les deux fronts.
- **Activer DVF** : `dvf_enabled=False` par défaut (config.py), CSV départementaux non
  versionnés. Documenter la procédure de téléchargement dans `data/lookup/dvf/README.md`
  (existe déjà), puis activer en dev.
- **Annonces** : `POST /diagnostic/zone/annonces` ne filtre pas par bounds
  (constat audit) — filtrer par bounds avant de répondre. Le CSV
  (`annonces_lookup.py:53-100`, ~102 lignes quasi 100% Paris) contredit le commentaire
  "couvre toute la France" — corriger le commentaire et/ou élargir le CSV.
- **`climat_score` des annonces = simulé** (`score_point_climat`) — remplacer par un
  vrai appel une fois R1 fait.

### Phase R3 — Fiabilité (tests, unification, streaming)

- Réparer `test_run_zone_small`/`test_run_zone_land_only` (`test_scoring.py:255-300`) :
  le premier définit `fake_collect` sans jamais le passer à `run_zone_risk_assessment`
  (teste la simulation, pas le chemin réel) ; le second ne vérifie qu'un champ trivial.
- Ajouter un test E2E de `/diagnostic/zone` figeant le contrat complet (présence de
  `niveau_global`, `rapport_promoteur`, `duree_evaluation_s`, points en erreur).
- Unifier les bandes de risque : le point porte `fort/moyen/faible` (`_niveau_alerte`,
  3 bandes) alors que les périls agrégés portent `pct_faible/modere/eleve/critique`
  (4 bandes, zone_scoring.py:442-445). Décider et documenter (ou aligner).
- Barre de progression réelle par flux (SSE/WebSocket, un événement par point) :
  transforme `run_zone_risk_assessment` en générateur asynchrone — chantier isolé,
  pas à mélanger avec R0-R2.

---

## PARTIE B — Carte adresse unique GEE-style (`frontend/jumeau_numerique/`)

Toute l'UI vit dans `frontend/jumeau_numerique/index.html` : carte `zoneMap`
MapLibre GL 4.7.1 (l.4517), `ZONE_BACKEND` → routes `/diagnostic/zone` (l.4755),
`/diagnostic/zone/prix` (l.4843), `/diagnostic/zone/annonces` (l.4889), marqueur
"Vous êtes ici" (l.4663), popup annonce (l.4967). Pas de Mapbox, pas de
`typhoon_gee_shell.html`, pas de page `jumeau_numerique/property-id/`.

### Phase 0 — Prérequis communs (vérifiés)

- **CORS** : déjà ouvert (`allow_origins=["*"]`, `backend/app/main.py:33-38`) — rien à faire.
- **Reprojection Lambert-93 → WGS84** : **rien à ajouter**. `footprint.py` contient
  déjà `lambert93_to_wgs84(x, y) -> (lat, lon)` (l.515, pur Python, aucun pyproj) et
  `wgs84_to_lambert93` (l.540, pour tests d'aller-retour). Les routes B l'importent.
- **Fichiers** : les changements B sont des **éditions** de `jumeau_numerique/index.html`
  + nouveaux fichiers backend enregistrés dans `main.py` (pattern l.40-44).

### Phase 1 — Recherche (géocodage)

**Backend** — `backend/app/api/routes/geocoding.py` (nouveau) ; `geocode_address(client,
address)` et `GeocodeResult{label, citycode, postcode, city, score, lat, lon}` vérifiés
(geocoding.py:70, 21-29) :

```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.connectors.geocoding import GeocodingError, geocode_address

router = APIRouter()


@router.get("/geocode")
async def geocode(q: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            result = await geocode_address(client, q)
        except GeocodingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Geocodage indisponible: {exc}") from exc

    return {
        "lat": result.lat, "lon": result.lon, "label": result.label,
        "citycode": result.citycode, "postcode": result.postcode,
        "city": result.city, "score": result.score,
    }
```

**Enregistrement** (NE PAS toucher à `api/routes/__init__.py`, il est vide) —
dans `backend/app/main.py`, avec les autres `include_router` :

```python
from app.api.routes import geocoding as geocoding_router
# ...
app.include_router(geocoding_router.router, prefix="/api", tags=["geocoding"])
```

**Frontend** — dans `jumeau_numerique/index.html` (bloc `zoneMap`) ; utiliser un
`maplibregl.Marker` réutilisé (une seule référence, remplacée à chaque recherche)
et `ZONE_BACKEND` :

```js
let currentCitycode = null, currentLatLon = null, searchMarker = null;

async function doSearch(q) {
  try {
    const res = await fetch(`${ZONE_BACKEND}/api/geocode?q=${encodeURIComponent(q)}`);
    if (!res.ok) { showSearchError(`Adresse introuvable : "${q}"`); return; }
    const g = await res.json();
    currentCitycode = g.citycode;
    currentLatLon = { lat: g.lat, lon: g.lon };
    zoneMap.flyTo({ center: [g.lon, g.lat], zoom: 16, duration: 900 });
    if (searchMarker) searchMarker.remove();
    searchMarker = new maplibregl.Marker({ color: '#1a73e8' }).setLngLat([g.lon, g.lat]).addTo(zoneMap);
    document.getElementById('search-input').value = g.label;
    onLocationResolved(g.lat, g.lon, g.citycode); // déclenche Phases 2 et 4
  } catch (err) {
    showSearchError('Erreur réseau pendant le géocodage.');
  }
}
```

### Phase 2 — Zones de risque Géorisques → GeoJSON par commune

**Backend** — `backend/app/digital_twin/risk_geometry.py` (nouveau). `fetch_georisques`
et `_niveau_alerte` sont réutilisés (tous deux vérifiés purs/indépendants des simulés) :

```python
"""Convertit les réponses Géorisques (JSON métier, pas de géométrie propre)
en GeoJSON affichable, en attachant le contour de commune (API Découpage
Administratif INSEE, gratuite, sans clé) au niveau de risque calculé.
"""
from __future__ import annotations

import httpx

from app.connectors.georisques import fetch_georisques
from app.scoring.zone_scoring import _niveau_alerte

_INSEE_DECOUPAGE_URL = "https://geo.api.gouv.fr/communes/{code}"


async def fetch_commune_polygon(client: httpx.AsyncClient, code_insee: str) -> dict:
    """Contour officiel de la commune en GeoJSON (Polygon/MultiPolygon, WGS84)."""
    response = await client.get(
        _INSEE_DECOUPAGE_URL.format(code=code_insee),
        params={"fields": "contour", "format": "geojson", "geometry": "contour"},
    )
    response.raise_for_status()
    data = response.json()
    if "geometry" not in data:
        raise ValueError(f"Pas de contour disponible pour la commune {code_insee}")
    return data  # Feature avec .geometry et .properties.code


def _score_for_risk_type(georisques_result: dict, risk_type: str) -> float:
    """Mappe une sous-clé Géorisques vers un score 0-100 exploitable par _niveau_alerte.

    Clés RÉELLES retournées par fetch_georisques (georisques.py:53-61) :
    risques_commune, catnat, zones_inondables, cavites, zonage_sismique,
    radon, mouvements_de_terrain, erreurs, lien_rapport_pdf.
    Logique volontairement simple pour la v1 : présence de données = risque à
    signaler, absence = faible. Un scoring plus fin (nb d'arrêtés CATNAT, zone
    sismique 1-5, etc.) est à affiner phase par phase sur de vraies données.
    """
    payload = georisques_result.get(risk_type)
    if not payload or (isinstance(payload, list) and len(payload) == 0):
        return 15.0  # faible par défaut si pas de donnée
    return 75.0      # présence de données = à signaler ; affiner plus tard


async def build_risk_layer(
    client: httpx.AsyncClient, code_insee: str, lat: float, lon: float, risk_type: str
) -> dict:
    commune = await fetch_commune_polygon(client, code_insee)
    georisques_result = await fetch_georisques(client, code_insee, lat, lon)

    score = _score_for_risk_type(georisques_result, risk_type)
    niveau = _niveau_alerte(score)  # fort / moyen / faible

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": commune["geometry"],
                "properties": {
                    "code_insee": code_insee,
                    "risk_type": risk_type,
                    "niveau_risque": niveau,
                    "score": score,
                    "detail": georisques_result.get(risk_type) or georisques_result,
                },
            }
        ],
    }
```

**Backend** — `backend/app/api/routes/risk_layers.py` (nouveau) :

```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.digital_twin.risk_geometry import build_risk_layer

router = APIRouter()

# Clés RÉELLES de fetch_georisques (georisques.py:53-61)
_VALID_TYPES = {"risques_commune", "catnat", "zones_inondables",
                "cavites", "zonage_sismique", "radon", "mouvements_de_terrain"}


@router.get("/layers/risk/{risk_type}")
async def risk_layer(risk_type: str, citycode: str, lat: float, lon: float) -> dict:
    if risk_type not in _VALID_TYPES:
        raise HTTPException(400, f"risk_type invalide. Attendus: {sorted(_VALID_TYPES)}")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            return await build_risk_layer(client, citycode, lat, lon, risk_type)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Géorisques/INSEE indisponible: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
```

Enregistrer dans `main.py` (même pattern que Phase 1).

**Frontend** — les 6 checkboxes de risque se câblent sur le vocabulaire `fort/moyen/faible` :

```js
const RISK_COLORS = { fort: '#DC4B39', moyen: '#D98A2B', faible: '#1F9D6C', default: '#999999' };
const RISK_LAYER_MAP = {
  'flood-zones': 'zones_inondables', 'seismic-zones': 'zonage_sismique',
  'cavites': 'cavites', 'mouvements-terrain': 'mouvements_de_terrain',
  'radon': 'radon', 'catnat': 'catnat',
};

async function toggleRiskLayer(layerId, riskType, checked) {
  if (!currentCitycode || !currentLatLon) return; // nécessite une recherche d'abord
  if (checked) {
    const url = `${ZONE_BACKEND}/api/layers/risk/${riskType}?citycode=${currentCitycode}` +
                `&lat=${currentLatLon.lat}&lon=${currentLatLon.lon}`;
    const geojson = await fetch(url).then(r => r.json());
    if (zoneMap.getSource(layerId)) {
      zoneMap.getSource(layerId).setData(geojson);
      zoneMap.setLayoutProperty(layerId, 'visibility', 'visible');
    } else {
      zoneMap.addSource(layerId, { type: 'geojson', data: geojson });
      zoneMap.addLayer({
        id: layerId, type: 'fill', source: layerId,
        paint: {
          'fill-color': ['match', ['get', 'niveau_risque'],
            'fort', RISK_COLORS.fort, 'moyen', RISK_COLORS.moyen,
            'faible', RISK_COLORS.faible, RISK_COLORS.default],
          'fill-opacity': 0.45, 'fill-outline-color': '#fff',
        },
      });
      zoneMap.on('click', layerId, (e) => showRiskPopup(e, riskType));
    }
  } else if (zoneMap.getLayer(layerId)) {
    zoneMap.setLayoutProperty(layerId, 'visibility', 'none');
  }
}

document.querySelectorAll('[data-layer]').forEach(cb => {
  const riskType = RISK_LAYER_MAP[cb.dataset.layer];
  if (!riskType) return;
  cb.addEventListener('change', () => toggleRiskLayer(cb.dataset.layer, riskType, cb.checked));
});
```

### Phase 3 — Bâtiments BDNB réels (extrusions 3D, remplacement du composite générique)

**Backend** — `backend/app/api/routes/buildings.py` (nouveau). `BdnbAdresseIntrouvable`
(bdnb.py:42) et `lambert93_to_wgs84` (footprint.py:515) vérifiés :

```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.connectors.bdnb import BdnbAdresseIntrouvable, fetch_bdnb
from app.digital_twin.footprint import lambert93_to_wgs84

router = APIRouter()


def _ring_l93_to_wgs84(ring: list) -> list:
    return [list(lambert93_to_wgs84(x, y)) for x, y in ring]


def _geom_to_geojson(geom_groupe: dict) -> dict:
    """Reprojette un geom_groupe BDNB (EPSG:2154) en GeoJSON WGS84 [lon, lat]."""
    if geom_groupe["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [_ring_l93_to_wgs84(r) for r in geom_groupe["coordinates"]]}
    if geom_groupe["type"] == "MultiPolygon":
        return {"type": "MultiPolygon",
                "coordinates": [[_ring_l93_to_wgs84(r) for r in poly] for poly in geom_groupe["coordinates"]]}
    raise ValueError(f"Type de géométrie non géré : {geom_groupe['type']}")


@router.get("/building-footprint-geojson")
async def building_footprint_geojson(address: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            bdnb = await fetch_bdnb(client, address)
        except BdnbAdresseIntrouvable as exc:
            raise HTTPException(404, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"BDNB indisponible: {exc}") from exc

    if not bdnb:
        raise HTTPException(404, "Aucun bâtiment BDNB à cette adresse.")

    batiment = bdnb["batiment"]
    geom_groupe = batiment.get("geom_groupe")
    if not geom_groupe:
        raise HTTPException(404, "Bâtiment trouvé mais sans géométrie (geom_groupe).")

    return {
        "type": "Feature",
        "geometry": _geom_to_geojson(geom_groupe),
        "properties": {
            "adresse": address,
            "hauteur_m": batiment.get("hauteur_mean") or batiment.get("hauteur_rnb") or 6.0,
            "annee_construction": batiment.get("annee_construction"),
            "dpe": batiment.get("classe_bilan_dpe"),
        },
    }


@router.get("/buildings-in-bbox")
async def buildings_in_bbox(bbox: str) -> dict:
    """bbox = 'minLon,minLat,maxLon,maxLat'.

    NON CONFIRMÉ : contrairement à fetch_bdnb() (validé par un test réel, cf.
    docstring de bdnb.py), cette route suppose que l'endpoint BDNB
    `batiment_groupe_complet` accepte un filtre spatial bbox. À vérifier dans
    la doc interactive (api.bdnb.io) avant mise en prod ; si le filtre spatial
    n'existe pas sous cette forme, utiliser la syntaxe PostgREST réellement
    documentée (ex. `?geom_groupe=within.POLYGON((...))`).
    """
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(400, "bbox invalide, attendu 'minLon,minLat,maxLon,maxLat'") from exc

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://api.bdnb.io/v1/bdnb/donnees/batiment_groupe_complet",
            params={
                "geom_groupe": f"bbox.{min_lon},{min_lat},{max_lon},{max_lat}",  # à vérifier
                "limit": 500,
            },
        )
        response.raise_for_status()
        rows = response.json()

    features = []
    for row in rows:
        geom_groupe = row.get("geom_groupe")
        if not geom_groupe:
            continue
        try:
            geometry = _geom_to_geojson(geom_groupe)
        except ValueError:
            continue
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "hauteur_m": row.get("hauteur_mean") or 6.0,
                "adresse": row.get("libelle_adr_principale_ban"),
                "dpe": row.get("classe_bilan_dpe"),
            },
        })

    return {"type": "FeatureCollection", "features": features}
```

Enregistrer dans `main.py` (même pattern). **Frontend** : layer `fill-extrusion`
chargé au `moveend` (debounce 300 ms, zoom ≥ 15), hauteur = `hauteur_m`, couleur = DPE.

### Phase 4 — Clic bâtiment → onglet Détails (diagnostic complet existant)

La route `POST /diagnostic` existe (`diagnostic.py`), montée **sans préfixe `/api`**
(main.py:41) — appeler `${ZONE_BACKEND}/diagnostic`. **Contrat réel** du retour
(diagnostic_builder.py:112-153) :

- `data.zones.sous_sol.risque` : score 0-100 inondation/sous-sol (pas de
  `risque_inondation_niveau` racine) → mapper en `fort/moyen/faible` côté client
  (seuils 70/40, mêmes que `_niveau_alerte`).
- `data.marche.dvf_disponible`, `data.marche.nb_transactions`,
  `data.marche.dernieres_transactions` (≥ 0 enregistrement) — PAS de
  `dvf.prix_m2_median`. Pour la médiane, appeler la route existante
  `POST ${ZONE_BACKEND}/diagnostic/zone/prix` avec `{bounds, citycode}` qui renvoie
  `{disponible, prix_m2_median, prix_m2_moyen, nb_ventes, par_type}` (diagnostic.py:252-284).
- Pas d'`altitude_m` : ajouter la route `GET /api/altitude?lat&lon` qui délègue à
  `ign_altitude.fetch_altitude(client, lat, lon)` (ign_altitude.py:51), fallback `null`.

```js
zoneMap.on('click', 'building-footprints', async (e) => {
  const props = e.features[0].properties;
  if (!props.adresse) return;
  // ouvrir l'onglet Détails, afficher "Chargement…"
  try {
    const res = await fetch(`${ZONE_BACKEND}/diagnostic`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adresse: props.adresse }),
    });
    if (!res.ok) throw new Error(await res.text());
    renderDetailPanel(await res.json(), props);
  } catch (err) {
    document.getElementById('detail-empty').textContent = 'Diagnostic indisponible pour ce bâtiment.';
  }
});

function renderDetailPanel(data, footprintProps) {
  // d-altitude : fetch(`${ZONE_BACKEND}/api/altitude?lat=..&lon=..`) — pas data.altitude_m
  // d-price : POST ${ZONE_BACKEND}/diagnostic/zone/prix { bounds, citycode: currentCitycode }
  // d-flood-badge : data.zones?.sous_sol?.risque >= 70 ? 'FORT' : >= 40 ? 'MOYEN' : 'FAIBLE'
  // btn-open-3d → window.open(`/property-id/index.html?adresse=${encodeURIComponent(footprintProps.adresse)}`)
}
```

> `frontend/property-id/index.html` (page certification, utilise `API_BASE` →
> `/property-id/generate`) : vérifier qu'il lit déjà `?adresse=` (`URLSearchParams`) ;
> sinon l'ajouter, pour pré-remplir l'adresse sans dupliquer la logique de diagnostic.

### Phase 5 — DVF et DRIAS (couches secondaires)

**DVF — aucune nouvelle route.** Les deux besoins sont déjà couverts :
- **Stats prix m²** : `POST /diagnostic/zone/prix` (médiane/moyenne/nb ventes, vrai DVF
  si `dvf_enabled=True` + CSV du département présent, sinon `disponible=false`).
- **Points de vente réels géolocalisés** : `POST /diagnostic/zone/annonces` (via
  `real_transactions_for_zone`, dvf_lookup.py:355 — enregistrements avec `lon/lat/prix_m2`
  — puis repli sur le CSV d'annonces). Layer `circle` interpolé sur `prix_m2`
  (palette vert→orange→rouge), comme la carte le fait déjà pour les annonces (l.4889+).

Supprimer l'idée de `/api/layers/dvf` et `lookup_dvf_for_commune` : `lookup_dvf(citycode)`
renvoie des lignes **non géolocalisées** (colonne lat/lon vide dans le format brut,
dvf_lookup.py:104-108) — inutilisable pour des marqueurs carte.

**DRIAS — nouveau connecteur à concevoir.** Il n'existe **aucune** donnée locale
(`backend/data/lookup/drias/` absent) ni de paramètre de config associé. Deux options :
1. (Recommandé) Connecteur HTTP vers l'API publique DRIAS (ArcGIS), avec cache
   disque court TTL, agrégé au grain département via `department_code_from_citycode`
   (import `app.core.paca`, déjà utilisé par `diagnostic.py:30`), contour départemental
   via `geo.api.gouv.fr/departements/{code}?fields=contour&format=geojson`.
   **NON CONFIRMÉ** : endpoint/contrat exact de l'API DRIAS à valider avant implémentation.
2. Importer les sorties DRIAS d'un pair (format NetCDF/CSV) et les versionner comme les
   CSV DVF — décision produit (licence, poids, fraîcheur).

---

## Récapitulatif des fichiers

**Partie A (modifications)**
```
backend/app/scoring/zone_scoring.py              (R0.2 accents, R0.3 niveau_global, R0.4 duree)
backend/app/scoring/promoteur_report.py          (R0.2 normalisation accents)
backend/app/api/routes/diagnostic.py             (R0.2 rapport_promoteur dans /diagnostic/zone)
backend/app/main.py                              (R0.6 double load_index + import dupliqué)
frontend/promoteurs/index.html                   (R0.1 URL/route/contrat, R0.5 couleurs+progression)
```

**Partie B (créations)**
```
backend/app/api/routes/geocoding.py              (Phase 1)
backend/app/digital_twin/risk_geometry.py        (Phase 2)
backend/app/api/routes/risk_layers.py            (Phase 2)
backend/app/api/routes/buildings.py              (Phase 3)
backend/app/api/routes/altitude.py               (Phase 4)
```
**Partie B (modifications)** : `backend/app/main.py` (4 `include_router`),
`frontend/jumeau_numerique/index.html` (Phases 1-5, blocs `zoneMap`/recherche/détails).
Aucun changement à `backend/requirements.txt` (pas de pyproj).

## Ordre de test recommandé

Partie A :
1. `cd backend && uvicorn app.main:app --reload` ; `curl -X POST localhost:8000/diagnostic/zone -H 'Content-Type: application/json' -d '{"bounds":[48.85,2.30,48.87,2.33],"spacing_km":0.5,"max_points":50}'` → vérifier `rapport_promoteur`, `duree_evaluation_s`, `points_echantillon[].score.niveau_global`.
2. Ouvrir `frontend/promoteurs/index.html` → mode Commune → Évaluer → points colorés `fort/moyen/faible`, rapport 3 champs affiché, barre de progression à 100 %.

Partie B :
3. `GET localhost:8000/api/geocode?q=...` seul (curl/Postman).
4. `GET localhost:8000/api/layers/risk/zones_inondables?citycode=...&lat=...&lon=...` seul.
5. `GET localhost:8000/api/building-footprint-geojson?address=...` seul, vérifier le polygone sur geojson.io avant de brancher au front.
6. Brancher ces routes dans `jumeau_numerique/index.html` phase par phase ; Phase 4 (clic → diagnostic) et Phase 5 (DVF existant, DRIAS à concevoir) en dernier.
