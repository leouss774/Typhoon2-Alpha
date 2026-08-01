# AUDIT — Projet Typhoon2-Alpha

**Date :** 1 août 2026
**Branche :** `feature/restructure` (19 fichiers supprimés du vieux frontend Next.js, non commités)
**Méthode :** lecture complète du backend (`backend/app`), des 4 fronts statiques, vérification des duplications par empreintes SHA-256, état git, exécution de `pytest`.
**Portée :** architecture, composants, état du MVP, structure, hygiène du dépôt, et plan de restructuration priorisé.

---

## 1bis. Restructuration exécutée (01/08/2026)

Arborescence réorganisée, modifications **staged** sur `feature/restructure` (non commitées) :

| Action | Détail |
|--------|--------|
| Supprimé | Doublette racine `typhon_risk_engine/` (71 fichiers) — **pytest passe de 11 à 3 erreurs de collecte** |
| Supprimé | `backend/recommendation_travaux-main/` (dépôt historique intégré dans `app/recommandations/`) |
| Supprimé | `frontend/jumeau_numerique/index.html.bak`, doublon `frontend/jumeau_numerique/typhoon_site.html`, photos racine (doublons), `backend/out/` |
| Retiré de git | Données runtime : `backend/data/property_ids/*`, `backend/typhon_risk_engine/out/*`, sorties matching (`rapport_artisans_matches.*`, `resultat_enrichi.json`) — gitignorés |
| Déplacé | `docs/` : PDF v2-1, `amelioration_recommandation.md`, `UX_AMELIORATIONS.md` |
| Déplacé | `frontend/site/typhoon_new_site.html` ; `frontend/property-id/` (sorti de `jumeau_numerique/`) |
| Déplacé | `backend/scripts/` : `*.ps1`, `adresses_paca_exemple.txt` ; `backend/data/reference/` : `annonces_*.csv` |
| Corrigé | `backend/.gitignore` : `backend/data/` → `data/` ; `.gitignore` racine enrichi (`property_ids/`, `engine/out/`) |

Structure finale : voir §3.7. Le blocage restant est uniquement **B1** (mistralai v1/v2).

---

## 1. Synthèse exécutive

Typhoon est une **plateforme de diagnostic climatique et d'assurabilité des bâtiments** (bâtiments résidentiels, périmètre MVP : région PACA). À partir d'une simple adresse, elle produit :

- un **diagnostic multi-exposition** (inondation, retrait-gonflement des argiles, feu de forêt, vent/cyclone, submersion marine, crues rapides…) ;
- une **projection climatique 2050** ;
- un **jumeau numérique 3D** du bâtiment (géométrie réelle extraite de la BDNB) ;
- des **recommandations de travaux** générées par RAG (Mistral + base de ~900 fiches de travaux) ;
- un **Property ID** certifié (numéro unique `TY-AAAA-NNNNNN`) ;
- un **matching d'artisans RGE** et un **rapport promoteur**.

**Qualité globale :** le produit est fonctionnel et l'architecture backend est saine (graphe LangGraph, connecteurs « fail-soft » jamais simulés, contrat de sortie du jumeau numérique bien typé). En revanche, **le dépôt est en état de transition non finalisé** : une doublette exacte du moteur de règles casse les tests, une dépendance incompatible empêche actuellement l'API de démarrer, et de nombreux fichiers dupliqués/obsolètes subsistent.

### Bloqueurs identifiés (à traiter en priorité)

| # | Sévérité | Problème | Fichiers |
|---|----------|----------|----------|
| B1 | **Critique** | `mistralai` 2.6.0 installé (global) mais le code utilise l'API v1 : `from mistralai import Mistral` échoue → **l'API FastAPI ne démarre pas** (`from app.main import app` → ImportError). | `backend/app/recommandations/mistral_client.py:19`, `backend/requirements.txt` (`>=1.5,<2.0`) |
| B2 | ~~Critique~~ **Corrigé** | ~~Doublette exacte du moteur de règles à la racine cassant `pytest`~~ → supprimée le 01/08/2026 (11 → 3 erreurs de collecte). | ~~racine `/typhon_risk_engine/`~~ |
| B3 | Élevé | 3 tests backend ne se collectent pas (même cause que B1). | `backend/tests/test_artisans.py`, `test_artisan_classification.py`, `test_artisan_site_finder.py` |

---

## 2. Architecture réelle

### 2.1 Pipeline d'agrégation : graphe LangGraph à **5 nœuds**

```
adresse ─► collector_agent ─► scoring_agent ─► recommandations_agent ─► interpretation_agent ─► digital_twin_agent ─► PropertyID
             (connecteurs)     (moteur règles)    (RAG Mistral)           (synthèse)           (géométrie 3D)
```

- `backend/app/agents/graph.py` : `StateGraph` + checkpointer `MemorySaver` (exécution en mémoire, pas de persistance conversationnelle).
- `backend/app/agents/state.py` : `TyphoonState` (TypedDict, `total=False`).
- Le nœud `recommandations` et `interpretation` **dégradent gracieusement sans `MISTRAL_API_KEY`** (sorties vides au lieu d'échouer).
- **Écart doc/code :** le README racine décrit un pipeline à 4 agents ; le graphe réel en compte 5 (`interpretation_agent` absent du README).

### 2.2 Surface d'API (FastAPI, `backend/app/main.py`)

| Route | Méthode | Rôle |
|-------|---------|------|
| `/health` | GET | Sonde de vie |
| `/diagnostic` | POST | Diagnostic complet (body `DiagnosticRequest` : `adresse` + `formulaire` optionnel) |
| `/diagnostic/fast` | POST | Variante accélérée utilisée par le front principal |
| `/api/v1/artisans/matching` | POST | Matching artisans v1 (`adresse`, `zones`, `limite` 1–20, défaut 5) |
| `/artisans/match` | POST | **Route legacy** d'un second pipeline de matching (voir §3.6) |
| `/property-id/generate` | POST | Génère un Property ID depuis les sorties du graphe |
| `/property-id/{id}` | GET | Récupère un Property ID stocké |
| `/property-id` | GET | Liste les Property IDs |

- CORS ouvert pour l'usage en `file://` ; les fronts statiques **appellent le port 8765 en dur** (`http://127.0.0.1:8765`).
- **Défaut mineur :** `main.py` lignes 22–23 contiennent deux imports dupliqués de `app.api.routes`.

### 2.3 Contrats de données

- `backend/app/schemas/building_data.py` : `BuildingData` (TypedDict) — sortie du collecteur (adresse, altitude, bdnb, georisques, climat, dvf_local, drias_local, erreurs, genere_le). Volontairement non-Pydantic : les réponses tierces (BDNB, Géorisques) ont une forme variable.
- `backend/app/schemas/house_geometry.py` : `HouseGeometry`, `Footprint`, `Ouvertures`, `GeometryBuildReport` (Pydantic) — contrat de sortie du jumeau numérique consommé tel quel par le front Three.js.
- `backend/app/property_id/schemas.py` : `PropertyID`, `BuildingInfo`, `Scores`, `RiskSummary`, `TimelineEvent`, `FutureModules`, certification.

### 2.4 Configuration

- `backend/app/core/config.py` : `BASE_DIR = backend/`, URLs par défaut (BDNB `api.bdnb.io`, Géorisques `www.georisques.gouv.fr/api/v1`, géocodage IGN `data.geopf.fr/geocodage/search`, `HTTP_TIMEOUT_SECONDS=15`).
- `backend/.env.example` : `DVF_ENABLED=false`, `COPERNICUS_ENABLED=false`, `MISTRAL_API_KEY` (optionnel), `HTTP_TIMEOUT_SECONDS`.
- `backend/requirements.txt` : fastapi, uvicorn, langgraph, langchain, chromadb, `mistralai>=1.5.0,<2.0.0`, numpy, pandas, cdsapi, xarray, netCDF4, pytest.
  - **Commentaires obsolètes :** langgraph et chromadb y sont marqués « prochaine étape » alors que tous deux sont déjà utilisés.
- `pytest.ini` : `asyncio_mode=auto`, `pythonpath=backend`.
- Python global : **3.14.6**, **aucun venv dans le dépôt** (le README recommande pourtant un venv).

---

## 3. Composants détaillés

### 3.1 Collecteur (`backend/app/agents/collector_agent.py`, `app/connectors/`)

Connecteurs live, tous **fail-soft** : toute source indisponible alimente `building_data["erreurs"]` avec une erreur explicite, **jamais une valeur inventée**.

| Source | Fournisseur | Notes |
|--------|-------------|-------|
| Géocodage | IGN Geoplateforme (`data.geopf.fr/geocodage/search`) | Successeur du BAN |
| Bâtiment | BDNB (`api.bdnb.io`) | géométrie, année, matériaux ; géocodeur BDNB séparé |
| Aléas | Géorisques (`www.georisques.gouv.fr/api/v1`) | route AZI ajustée via `code_insee` |
| Altitude | IGN Altimétrie | auto-découverte de la ressource, fallback `ign_rge_alti_wld` |
| Climat | Open-Meteo | 2 modèles (`EC_Earth3P_HR`, `MRI_AGCM3_2_S`), fenêtres 2015–2024 et 2041–2050 |
| Climat | Copernicus CDS | optionnel (`COPERNICUS_ENABLED=false`) |
| DVF | Fichiers locaux par département | `DVF_ENABLED=false` ; `app/dvf_lookup` |
| DRIAS | Fichiers locaux | `app/drias_lookup` |

- **Incohérence signalée :** `app/scoring/zone_scoring.py` construit en mode dev un `building_data` **minimal simulé sans appels API**, ce qui contredit le principe « aucune donnée simulée » du collecteur.
- `backend/app/cli.py` : script de test de l'orchestrateur en 3 modes (adresse unique, interactif, batch `--batch adresses_paca.txt`), avec garde PACA `--force`.

### 3.2 Moteur de règles (`backend/typhon_risk_engine/`)

Moteur déterministe à base de règles YAML (scénarios, P01…), `engine.py`, `canonical.py`, `METHODOLOGIE.md`, 10 fichiers de tests. **Doublonné à l'identique à la racine** (voir B2).

### 3.3 Scoring (`backend/app/scoring/`)

- `risk_model.py` : **7 zones** `ZONE_NAMES = ["fondations","murs_nord","murs_sud","murs_est","murs_ouest","toiture","sous_sol"]`, décisions de conception documentées (D01–D06), formule F/V `R = 100 × (F/100)^0.5 × (V/100)^0.5`.
- `zone_scoring.py` : scoring par zone, projection 2050 ; **mode simulé en dev** (voir §3.1).
- `promoteur_report.py` : rapport promoteur (3 champs), règles déterministes sans LLM.

### 3.4 Recommandations RAG (`backend/app/recommandations/`)

- `mistral_client.py` : SDK v1 (`Mistral`), `mistral-small-latest`, `mistral-embed`, timeout 300 s, throttle 0,3 s, `max_tokens=1000`, retry backoff (5 tentatives). **→ incompatible avec mistralai 2.6.0 installé (B1).**
- `rag_engine.py` : `SYSTEM_PROMPT` imposant d'utiliser **uniquement les fiches fournies**, liste vide plutôt que d'inventer. Index ~19 Mo, ~900 fiches, chargé au démarrage (`load_index()`).
- `mapping.py` : `ZONE_TO_RECO` (murs_* → « facade »), `_infer_risques` (retypage du vocabulaire risque français en vocabulaire fermé). **Zone « menuiseries » jamais alimentée** (trou probable).
- Ce module est le **refactor** de l'ancien dépôt `backend/recommendation_travaux-main/` (encore présent dans le dépôt).

### 3.5 Jumeau numérique & Property ID

- `app/digital_twin/` : `diagnostic_builder.py` (heuristiques `_apply_mvp_defaults` : `has_basement` = année < 1949, `has_cellar/garage/garden` = False — **valeurs par défaut inventées**, assumées MVP), `geometry_builder.py` (extrusion, ouvertures depuis le DPE BDNB quand disponible), `footprint.py` (empreinte réelle depuis `geom_groupe` BDNB : enveloppe convexe / rotating calipers maison, **sans shapely** ; classification de forme `rectangulaire/en_L/en_T/en_U/en_croix/multipolygone/irreguliere`).
- `app/property_id/` : `generator.py` (ID `TY-{année}-{seq 6}` thread-safe, persistance JSON via `PropertyIDFileStore` dans `backend/data/property_ids/`), `certification/` (certificat niveau/score/statut), routes dédiées.

### 3.6 Matching d'artisans — **deux pipelines parallèles**

| | `app/artisans/` (route `/api/v1/artisans`) | `app/matching/` (route legacy `/artisans/match`) |
|---|---|---|
| Classification | Mistral (`classer_avec_mistral`) ou règle (`decision_regle`) | règles/cache (`cache.py`) |
| Enrichissement | `site_finder.enrichir_coordonnees` | — |
| Sources | ADEME RGE + annuaire entreprises | ADEME RGE + `recherche-entreprises.api.gouv.fr` |
| Sortie | matching structuré | matching + `generate_rapport_artisans` |

Redondance fonctionnelle : **à unifier** (voir plan §6, action R6).

### 3.7 Frontends (statiques, aucune build)

| Fichier | Lignes | Rôle |
|---------|-------:|------|
| `frontend/jumeau_numerique/index.html` | 6 232 | **App principale 3D** : scène Three.js (CDN), `POST {apiBase}/diagnostic/fast`, `api-base` par défaut `http://127.0.0.1:8765`, écran Property ID côté client, overlay carte de zone, devis, bouton données démo/mock |
| `frontend/property-id/index.html` | 1 744 | Écran Property ID |
| `frontend/artisans/index.html` | 862 | Matching artisans |
| `frontend/promoteurs/index.html` | 777 | Prospection promoteurs |
| `frontend/site/typhoon_new_site.html` | 2 140 | Site de présentation |
| `docs/typhoon_site.html` | 1 898 | Prototype « site » (copie unique conservée) |

Le **vieux frontend Next.js** (`frontend/app/*`, 19 fichiers, 2 904 lignes) est **staged pour suppression** sur `feature/restructure` mais pas encore commité — abandon assumé au profit des fronts statiques.

---

## 4. État du MVP (périmètre PACA)

| Fonctionnalité | Statut | Commentaire |
|----------------|--------|-------------|
| Diagnostic multi-aléas (PACA) | ✅ | Connecteurs live + graphe 5 nœuds |
| Jumeau numérique 3D (géométrie BDNB) | ✅ | Empreinte réelle, ouvertures DPE |
| Recommandations RAG (Mistral) | ✅ (dégradable) | Sans clé API : sorties vides |
| Projection climatique 2050 | ✅ | Open-Meteo 2 modèles |
| Property ID + certification | ✅ | Stockage JSON local |
| Matching artisans RGE | ⚠️ | 2 implémentations, route legacy conservée |
| Rapport promoteur | ✅ | Règles déterministes |
| DVF local | ⚠️ | Désactivé par défaut (`DVF_ENABLED=false`) |
| Copernicus CDS | ⚠️ | Désactivé par défaut |
| Fronts statiques | ✅ | Utilisables en `file://`, port 8765 en dur |

**Fonctionnel aujourd'hui :** la plupart des cas d'usage démo PACA. **Mais l'API ne démarre pas dans l'environnement actuel** à cause de B1.

---

## 5. Inventaire des problèmes

### 5.1 Bloqueurs
1. **B1 — mistralai v2 vs code v1** (critique) : `mistralai 2.6.0` installé globalement ; `mistral_client.py` fait `from mistralai import Mistral` (API v1, retirée en v2). Conséquence : `from app.main import app` → ImportError ; 3 tests en erreur ; **l'API est injoignable**. Le pin `requirements.txt` (`<2.0.0`) n'a pas été respecté par l'installation.
2. **B2 — doublette du moteur de règles** (critique pour les tests) : `typhon_risk_engine/` à la racine == `backend/typhon_risk_engine/` (empreintes SHA-256 identiques sur les fichiers échantillonnés : README, engine, canonical, P01.yaml, tests). `pytest` depuis la racine → 10 erreurs « import file mismatch ». **148 tests collectés, 11 erreurs au total.**

### 5.2 Duplications & code mort
- ~~Doublette `typhon_risk_engine` (B2)~~ → **supprimée** (01/08/2026).
- ~~`backend/recommendation_travaux-main/`~~ → **supprimé** (01/08/2026).
- ~~`typhoon_site.html` en double + variante racine~~ → **unifié** : `docs/typhoon_site.html` unique, `typhoon_new_site.html` → `frontend/site/`.
- ~~`frontend/jumeau_numerique/index.html.bak`~~ → **supprimé**.
- Matching artisans en double (§3.6) : `app/artisans/` (v1) vs `app/matching/` (legacy). **Reste à unifier.**
- Vieux frontend Next.js en attente de suppression (staged, **à committer**).

### 5.3 Hygiène & documentation
- Imports dupliqués dans `main.py` (l. 22–23).
- README racine obsolète : pipeline à 4 agents (réel : 5), installation encore en cours de réécriture (diff non commité), commentaires `requirements.txt` périmés (« langgraph prochaine étape » alors qu'il est utilisé).
- `docs/GUIDE_ORCHESTRATEUR_API.md` : précis mais antérieur à `interpretation_agent`.
- Zone « menuiseries » non alimentée dans `mapping.py`.
- Mode simulé de `zone_scoring` en contradiction avec le principe « aucune donnée simulée ».
- ~~Artefacts en racine (photos, PDF, sorties `backend/out/`)~~ → **nettoyés** (01/08/2026).
- Front principal : données démo/mock embarquées + `api-base` en dur (`127.0.0.1:8765`).

---

## 6. Plan de restructuration priorisé

### Phase 1 — Urgent (redonner un état fonctionnel)
| # | Action | Justification | Statut |
|---|--------|---------------|--------|
| 1 | **Résoudre B1** : créer le venv `backend/.venv` et installer `pip install -r requirements.txt` (mistralai 1.x), OU migrer `mistral_client.py` et `app/artisans/classification.py` vers l'API v2 (`MistralClient`) | L'API doit démarrer | **à faire** |
| 2 | **Supprimer la doublette** racine `typhon_risk_engine/` | Restaure `pytest` (B2, B3) | ✅ 01/08/2026 |
| 3 | **Committer la suppression du frontend Next.js** (déjà staged) | Finalise la restructuration en cours | **à faire** |

### Phase 2 — Nettoyage des doublons
| # | Action | Statut |
|---|--------|--------|
| 4 | Supprimer `frontend/jumeau_numerique/index.html.bak` | ✅ 01/08/2026 |
| 5 | Unifier `typhoon_site.html` (source unique `docs/`) et statuer sur `typhoon_new_site.html` | ✅ 01/08/2026 |
| 6 | **Unifier le matching artisans** : garder `app/artisans/` (v1) comme référence, déprécier puis supprimer `app/matching/` + route `/artisans/match` | **à faire** |
| 7 | Exclure `recommendation_travaux-main/` du dépôt | ✅ 01/08/2026 |
| 8 | Déplacer/supprimer les artefacts racine (photos, PDF) ; gitignorer `backend/out/` | ✅ 01/08/2026 |

### Phase 3 — Hygiène code & docs
| # | Action |
|---|--------|
| 9 | Dédupliquer les imports de `main.py` (l. 22–23) |
| 10 | Corriger `requirements.txt` (pins réels, retirer les commentaires « prochaine étape ») |
| 11 | Mettre à jour le README racine : graphe 5 agents, installation (diff en cours), contrats |
| 12 | Documenter explicitement (ou brancher sur les connecteurs) le mode simulé de `zone_scoring` et les heuristiques `_apply_mvp_defaults` (les marquer « MVP » dans la sortie) |
| 13 | Alimenter la zone « menuiseries » dans `mapping.py` |
| 14 | Standardiser le run : venv documenté, port 8765, note CORS `file://` |

### Phase 4 — Tests & fronts
| # | Action |
|---|--------|
| 15 | Rétablir la collecte complète (60 + tests moteur) et ajouter des tests pour recommandations / interpretation / property_id |
| 16 | Extraire les assets partagés des 4 fronts statiques ; centraliser `api-base` (variable + fallback) ; flaguer clairement le mode démo du front principal |

**Critères de « dépôt propre »** : `pytest` passe depuis la racine, `from app.main import app` importe, un seul pipeline de matching, aucun hash dupliqué de fichier source, README à jour.

---

## 7. Fichiers clés (aide à la navigation)

| Fichier | Rôle |
|---------|------|
| `backend/app/main.py` | Point d'entrée FastAPI (imports dupliqués l. 22–23) |
| `backend/app/agents/graph.py` | Graphe LangGraph 5 nœuds + MemorySaver |
| `backend/app/recommandations/mistral_client.py` | Client Mistral v1 (**bloquant B1**) |
| `backend/app/scoring/zone_scoring.py` | Mode simulé dev |
| `backend/app/artisans/service.py` vs `backend/app/matching/service.py` | Matching en double (§3.6) |
| `backend/typhon_risk_engine/` | Moteur de règles YAML (copie unique) |
| `frontend/jumeau_numerique/index.html` | Front 3D principal (6 232 l., `/diagnostic/fast`, port 8765) |
| `frontend/property-id/`, `frontend/artisans/`, `frontend/promoteurs/`, `frontend/site/` | Fronts par cas d'usage |
| `AUDIT.md` | Ce document |
