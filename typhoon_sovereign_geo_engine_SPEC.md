# SPEC — Typhoon Sovereign Geo-Risk Engine (rebuild from zero)

> **Rôle de ce document** : prompt d'ingénierie complet, à donner à un agent de code (ou à une équipe) pour reconstruire **from scratch** le module de diagnostic bâtiment/zone de Typhoon, sur le modèle d'un framework géospatial intégré type Google Earth Engine / VoxCity — mais **100 % souverain France/UE**, sans aucune dépendance à un hyperscaler non-européen (pas de Google Earth Engine, pas d'AWS obligatoire, pas de Vercel/Azure comme dépendance structurelle).
>
> Ce document remplace la logique "on répare l'existant" (voir `AUDIT.md` et `audit_zone_risk_promoteurs.md`) par une logique "on reconstruit le moteur géospatial proprement, une fois, avec la bonne architecture dès le départ". Le nouveau moteur doit pouvoir **remplacer entièrement** `backend/app/scoring/zone_scoring.py`, `risk_model.py`, et le pipeline de collecte simulé.

---

## 0. Principe directeur

**"VoxCity, mais souverain."** VoxCity résout : *donnée géospatiale hétérogène → grille/voxel unifiée → simulation*. On veut la même **forme** de pipeline (ingestion multi-source → modèle unifié par bâtiment/point → moteur de calcul → exports), mais :

| VoxCity (à ne PAS reproduire) | Typhoon Sovereign Engine (à construire) |
|---|---|
| Google Earth Engine obligatoire | Aucune auth cloud obligatoire — que des API REST publiques FR/UE |
| Sources mondiales (Microsoft, Meta, NASA) | Sources exclusivement France/UE (RNB, BDNB, Géorisques, DVF, DPE, IGN, Copernicus, Open-Meteo) |
| Sortie = voxel 3D pour simulation physique (solaire, vue) | Sortie = fiche de risque + score d'assurabilité + géométrie réelle par bâtiment |
| GDAL + conda + Python 3.12 pin | Stack standard FastAPI/Python, aucune dépendance native lourde sauf si strictement nécessaire (Shapely/PyProj acceptables) |
| Une exécution = un modèle 3D détaillé, coûteux | Une exécution = un point ou une grille de points, rapide (< 60s pour un lot) |

**Contrainte non négociable : chaque connecteur de données doit être 100 % traçable à une source publique France/UE, sans clé d'accès à un cloud non-européen.**

---

## 1. Ce qu'on jette, ce qu'on garde

### À jeter entièrement (dette actuelle)
- `backend/typhon_risk_engine/` doublette racine (suppression pure)
- `zone_scoring.py` en mode simulé (`_building_data_minimal`)
- Les deux pipelines de matching artisans (`app/artisans/` vs `app/matching/`)
- Le vocabulaire de bandes de risque incohérent (4 bandes zone vs 5 bandes D03)
- Les proxies de zones pour les périls (inondation→sous_sol, etc.) — remplacés par de vrais scores par péril

### À garder et faire pivoter
- Le graphe LangGraph (`agents/graph.py`) comme squelette d'orchestration — mais chaque nœud est réécrit pour consommer le nouveau moteur
- Le contrat `HouseGeometry` (Pydantic) pour le jumeau numérique — inchangé, c'est un bon contrat
- `PropertyID` (`property_id/schemas.py`) — inchangé
- Le principe fail-soft "jamais de donnée inventée" — **renforcé**, pas retiré

---

## 2. Architecture cible (from scratch)

```
                         ┌─────────────────────────────┐
                         │   Address / BBox / RNB-ID   │
                         └───────────────┬─────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │  RESOLVER (identité bâtiment)│
                         │  IGN Geoplateforme → RNB-ID  │
                         └───────────────┬─────────────┘
                                         ▼
        ┌────────────────────────────────────────────────────────┐
        │                CONNECTOR LAYER (fail-soft)              │
        │  chaque connecteur = 1 source, 1 contrat, 1 timeout,     │
        │  jamais de donnée inventée, erreur explicite si absent   │
        ├──────────────┬──────────────┬──────────────┬────────────┤
        │  RNB-coeur   │    BDNB       │  Géorisques  │  IGN Alti  │
        │ (géométrie,  │ (matériaux,   │ (aléas par   │ (altitude) │
        │  identité)   │  année, DPE)  │  parcelle)   │            │
        ├──────────────┼──────────────┼──────────────┼────────────┤
        │ dvf_as_api   │  ADEME DPE   │ Open-Meteo   │ Copernicus │
        │ (cquest,     │  (perf.      │ (climat      │ CDS (clim. │
        │  self-hosté) │  énergétique)│  observé)    │ projeté)   │
        └──────────────┴──────────────┴──────────────┴────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │   BUILDING STATE (unifié)    │
                         │   contrat unique par bâtiment │
                         └───────────────┬─────────────┘
                                         ▼
                ┌────────────────────────────────────────┐
                │      RISK ENGINE (pur, déterministe)     │
                │  hazard × exposition × vulnérabilité      │
                │  = score par péril, PAS de proxy de zone  │
                └────────────────────┬─────────────────────┘
                                     ▼
        ┌───────────────┬───────────────┬────────────────────┐
        │ Property ID   │ Rapport       │  RAG Recommandations │
        │ (certification)│ Promoteur     │  (Mistral, dégradable)│
        └───────────────┴───────────────┴────────────────────┘
                                     ▼
                         ┌─────────────────────────────┐
                         │   API FastAPI (contrat figé)  │
                         │  /diagnostic  /diagnostic/zone │
                         └─────────────────────────────┘
```

---

## 3. Contrat de données unifié — `BuildingState`

Remplace `BuildingData` (TypedDict libre) par un contrat **Pydantic strict avec provenance explicite par champ**. Chaque valeur sait d'où elle vient et si elle est réelle ou absente (jamais simulée) :

```python
from pydantic import BaseModel
from enum import Enum
from typing import Optional

class SourceStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"       # source interrogée, pas de réponse/timeout
    NOT_APPLICABLE = "not_applicable" # source non pertinente pour ce point

class SourcedValue[T](BaseModel):
    value: Optional[T]
    source: str            # ex: "bdnb", "georisques", "rnb"
    status: SourceStatus
    fetched_at: str        # ISO timestamp

class BuildingState(BaseModel):
    rnb_id: SourcedValue[str]
    geometry_wkt: SourcedValue[str]        # depuis RNB-coeur (Lambert93 → WGS84)
    annee_construction: SourcedValue[int]  # BDNB
    materiaux: SourcedValue[dict]          # BDNB
    dpe_classe: SourcedValue[str]          # ADEME DPE, via rnb_id si possible
    altitude_m: SourcedValue[float]        # IGN Alti
    alea_inondation: SourcedValue[dict]    # Géorisques AZI
    alea_rga: SourcedValue[dict]           # Géorisques argiles
    alea_feu_foret: SourcedValue[dict]     # Géorisques
    alea_sismique: SourcedValue[dict]      # Géorisques zonage sismique
    prix_m2_local: SourcedValue[float]     # dvf_as_api
    climat_observe: SourcedValue[dict]     # Open-Meteo
    climat_projete_2050: SourcedValue[dict]# Copernicus CDS
```

**Règle absolue** : aucun champ n'est jamais rempli par un générateur de bruit ou une heuristique déguisée en donnée. Si une source échoue, `status=UNAVAILABLE` et `value=None` — le moteur de risque doit savoir gérer l'absence, pas la masquer.

---

## 4. Connecteurs à implémenter (dans l'ordre)

Chacun = 1 module, 1 test, 1 fixture offline. Contrat commun :

```python
class Connector(Protocol):
    async def fetch(self, rnb_id: str | None, lat: float, lon: float) -> SourcedValue: ...
    name: str
    timeout_s: float
    base_url: str  # doit être un domaine .fr, .gouv.fr, ou institution UE identifiée
```

| # | Connecteur | Source | Domaine | Notes |
|---|------------|--------|---------|-------|
| 1 | `rnb_connector.py` | RNB-coeur (public API) | data.rnb.beta.gouv.fr | Identité + géométrie bâtiment, remplace/complète BDNB pour la géométrie |
| 2 | `bdnb_connector.py` | API BDNB Open | api.bdnb.io | Matériaux, année, usage. **Vérifier si `rnb_id` est déjà renvoyé** avant de dupliquer l'appel RNB |
| 3 | `georisques_connector.py` | Géorisques API v1 | www.georisques.gouv.fr | AZI, RGA, sismique, feu de forêt — garder tel quel, déjà fonctionnel |
| 4 | `ign_alti_connector.py` | IGN Altimétrie | data.geopf.fr | Garder tel quel |
| 5 | `dvf_connector.py` | **remplace le CSV local désactivé** par `dvf_as_api` self-hosté (fork de `cquest/dvf_as_api`) | instance interne | Voir §5 |
| 6 | `dpe_connector.py` | **nouveau** — API DPE ADEME | data.ademe.fr | Enrichissement énergie/performance, jonction par adresse ou rnb_id |
| 7 | `openmeteo_connector.py` | Open-Meteo | api.open-meteo.com | Garder tel quel |
| 8 | `copernicus_connector.py` | Copernicus CDS | cds.climate.copernicus.eu | Garder tel quel, optionnel |

**Interdiction explicite** : aucun connecteur ne doit référencer Google Earth Engine, AWS Open Data (sauf dataset explicitement sous licence ouverte re-téléchargé et hébergé par vous), Microsoft Planetary Computer, ou tout service nécessitant une authentification à un cloud non-européen.

---

## 5. Déploiement souverain de `dvf_as_api`

1. Fork interne de `cquest/dvf_as_api` (licence à vérifier avant fork commercial — contacter l'auteur si besoin de clarification).
2. Self-host sur votre infra (pas `api.cquest.org` en prod — <cite>disponibilité non garantie, c'est un POC</cite>).
3. Alimenter la base PostgreSQL avec les fichiers DVF/DGFiP téléchargés depuis data.gouv.fr (mêmes fichiers que ceux prévus pour `DVF_ENABLED=true` dans la config actuelle).
4. Exposer un endpoint interne `GET /internal/dvf?lat=&lon=&dist=` consommé par `dvf_connector.py`.

---

## 6. Risk Engine — reconstruction

Objectif : **un score réel par péril**, pas un proxy de zone.

```python
class PerilScore(BaseModel):
    peril: str                 # "inondation", "rga", "feu_foret", "seisme", "submersion"
    intensite: float           # 0-100, dérivé du champ Géorisques réel (pas d'une zone murale)
    confiance: float           # 0-1, fonction du nombre de sources disponibles pour ce péril
    niveau: str                # bande D03 unique (5 niveaux), la SEULE nomenclature dans tout le système
    sources: list[str]         # traçabilité

def compute_peril_scores(state: BuildingState) -> list[PerilScore]:
    """
    Règle de conception : chaque péril a SA propre fonction de scoring,
    alimentée par les champs Géorisques qui lui correspondent réellement
    (pas de mapping zone murale -> péril).
    Si state.alea_X.status == UNAVAILABLE : confiance basse, niveau
    explicitement marqué "donnée manquante", jamais un score inventé.
    """
```

**Bandes unifiées (D03, 5 niveaux)** — utilisées PARTOUT (diagnostic bien, zone, rapport promoteur) :
`tres_faible < 20`, `faible 20–39`, `modere 40–59`, `eleve 60–79`, `critique ≥ 80`.
Toutes les chaînes de comparaison doivent être normalisées (ASCII, sans accents en interne, accents uniquement à l'affichage) pour éviter la classe de bug B6 de l'audit zone.

---

## 7. Grille / zone — reconstruction

Remplace `run_zone_risk_assessment` :

- **Périmètre réel** : polygone communal (via API découpage administratif IGN ou Etalab) au lieu d'une bbox rectangulaire ±0.04°.
- **Échantillonnage** : grille de points espacés (`spacing_km` paramétrable), chaque point résolu en `rnb_id` le plus proche s'il existe un bâtiment, sinon marqué `hors_bati`.
- **`collect_fn` toujours branché** — aucun mode simulé ne doit exister dans le code de production ; un mode `--offline-fixture` explicite pour les tests, jamais silencieux.
- **Concurrence réelle** : `max_concurrency` reçu du front, pas hardcodé.
- **Progression réelle** : Server-Sent Events (SSE) streamant `{point_traité, total, erreurs}` — supprime la barre de progression fake du front promoteurs.

---

## 8. API — contrat figé (à ne plus jamais casser)

```
POST /diagnostic                body: {adresse, formulaire?}
POST /diagnostic/zone            body: {bounds|polygon, spacing_km, max_points, land_only}
GET  /diagnostic/zone/stream     SSE — progression réelle
GET  /diagnostic/zone/prix       DVF réel via dvf_as_api
GET  /diagnostic/zone/annonces   annonces (couverture réelle documentée, pas "toute la France" si faux)
POST /property-id/generate
GET  /property-id/{id}
```

Chaque réponse contient un bloc `provenance` listant, pour chaque champ agrégé, la source et son statut — pour que le front puisse afficher honnêtement "donnée manquante" plutôt que de masquer silencieusement les points en échec (bug B7/points-en-échec-masqués de l'audit zone).

---

## 9. Ordre de construction recommandé (sprints)

1. **Sprint 0** — `BuildingState` + connecteurs RNB + BDNB + Géorisques (les 3 déjà partiellement fonctionnels), tests offline avec fixtures réelles enregistrées.
2. **Sprint 1** — Risk Engine par péril (5 bandes unifiées), suppression des proxies de zone.
3. **Sprint 2** — `dvf_as_api` self-hosté + `dpe_connector.py`, branchement réel dans `/diagnostic`.
4. **Sprint 3** — Reconstruction de la route `/diagnostic/zone` : polygone réel, `collect_fn` toujours branché, SSE.
5. **Sprint 4** — Rapport promoteur branché sur le nouveau moteur (plus de bug d'accents possible, un seul vocabulaire).
6. **Sprint 5** — Fronts : suppression des poids décoratifs, suppression des `alert()`, affichage honnête des points en erreur, attribution carte correcte.

---

## 10. Critères de "moteur propre" (Definition of Done)

- [ ] Aucun appel réseau vers un domaine hors France/UE dans tout le code de production
- [ ] Aucun mode simulé accessible en dehors d'un flag de test explicite
- [ ] Un seul vocabulaire de bandes de risque (5 niveaux D03) dans tout le système
- [ ] Chaque champ de sortie a une provenance et un statut traçables
- [ ] `pytest` passe depuis la racine, zéro doublette de fichiers
- [ ] La route zone répond avec de vraies données par point pour un échantillon testé manuellement (ex. Nice, 9 points)
- [ ] Le front n'affiche jamais un score sans indiquer sa confiance/provenance

---

## 11. Prompt court (à copier tel quel dans un agent de code)

> Reconstruis le module de diagnostic géo-risque de Typhoon en suivant strictement `typhoon_sovereign_geo_engine_SPEC.md`. Commence par le contrat `BuildingState` (§3) et les connecteurs RNB/BDNB/Géorisques (§4, lignes 1-3). N'implémente aucun mode simulé, aucune dépendance à un cloud non-européen, et n'introduis aucun nouveau vocabulaire de bandes de risque autre que les 5 niveaux D03 définis en §6. Écris un test offline avec fixture réelle pour chaque connecteur avant de passer au suivant. Ne touche pas au contrat `HouseGeometry` ni à `PropertyID`, qui restent inchangés.
