# Typhoon — Diagnostic climatique & jumeau numérique du bâti

Typhoon construit un jumeau numérique d'un bien immobilier pour évaluer son exposition aux risques climatiques (inondation, sécheresse/RGA, mouvement de terrain, etc.) et générer des recommandations de travaux de résilience, appuyées sur une base documentaire de référence (RAG).

Ce dépôt implémente le système sous forme d'agents orchestrés avec **LangGraph**, exposés via un **backend** commun, et consommés par un **frontend dédié par cas d'usage**.

Statut : cadrage / MVP en cours de spécification (voir section Roadmap).

## Sommaire

- [Vision du produit](#vision-du-produit)
- [Architecture multi-agents](#architecture-multi-agents)
- [Structure du dépôt](#structure-du-dépôt)
- [Les agents](#les-agents)
- [Jumeau numérique 3D — contrat de sortie](#jumeau-numérique-3d--contrat-de-sortie)
- [Backend — communication inter-agents](#backend--communication-inter-agents)
- [Frontend — un client par cas d'usage](#frontend--un-client-par-cas-dusage)
- [Sources de données du diagnostic](#sources-de-données-du-diagnostic)
- [Base documentaire de l'agent RAG](#base-documentaire-de-lagent-rag)
- [Installation](#installation)
- [Variables d'environnement](#variables-denvironnement)
- [Roadmap / points ouverts](#roadmap--points-ouverts)
- [Glossaire](#glossaire)

## Vision du produit

Trois briques fonctionnelles :

1. **Collecte de données** — agrégation de sources publiques et privées sur le bâti, la localisation et le climat.
2. **Scoring de risque** — calcul d'un score de risque par aléa et par partie du bâtiment.
3. **Moteur de recommandations (RAG)** — génération de préconisations de travaux, appuyées sur une base documentaire de référence.
4. **Jumeau numérique 3D** — restitution du diagnostic sous forme d'une maison 3D navigable (Three.js), où chaque partie du bâtiment est colorée selon son niveau de risque et cliquable pour afficher le détail et les recommandations associées.

C'est cette restitution 3D qui porte l'essentiel de l'expérience utilisateur : l'utilisateur parcourt sa maison en 3D, visualise les risques par zone, et accède aux recommandations en cliquant sur chaque partie du bâtiment.

Trois familles d'utilisateurs cibles, chacune avec son propre parcours (voir [Frontend](#frontend--un-client-par-cas-dusage)) :

- **Assurance immobilière** — diagnostic + score de risque pour un devis personnalisé, et filtrage amont des clients à très haut risque.
- **Banque** — évaluation du risque climatique d'un bien financé, pour arbitrer ou différencier un dossier de prêt.
- **Agents et promoteurs immobiliers** — recherche de biens intégrant la résilience climatique, et génération d'arguments de vente.

## Architecture multi-agents

L'orchestration est modélisée comme un `StateGraph` LangGraph à quatre agents séquencés, le premier agent parallélisant lui-même ses appels externes. Ce séquencement reprend les étapes déjà affichées dans l'écran de traitement du prototype front (géocodage, Géorisques, projections climatiques, BDNB, fusion, recommandations, rendu 3D) :

```
                         ┌───────────────────────────┐
                         │   collector_agent (LangGraph node)  │
   START ───────────────▶│  fan-out / fan-in interne  │
                         │                             │
                         │  Appels LIVE (parallélisés) │
                         │  |- BDNB          -> api.bdnb.io (geocodage BDNB + adresse exacte)
                         │  |- Georisques v1 -> georisques.gouv.fr
                         │  |- IGN Altitude  -> data.geopf.fr
                         │  |- Open-Meteo    -> climate-api.open-meteo.com
                         │  `- CATNAT        -> georisques.gouv.fr
                         │                             │
                         │  Lookups locaux (instantanés)│
                         │  |- DVF        -> lookup/lookup.ts, lookup/departments.json
                         │  `- Copernicus -> cache NetCDF PACA telecharge via l'API CDS
                         └──────────────┬──────────────┘
                                        │  state.building_data (données du bâti + géométrie brute)
                                        ▼
                         ┌──────────────────────────────┐
                         │      scoring_agent            │
                         │  score de risque par aléa      │
                         │  et par partie du bâtiment     │
                         └──────────────┬────────────────┘
                                        │  state.risk_scores
                                        ▼
                         ┌──────────────────────────────┐
                         │      rag_agent                 │
                         │  retrieval sur base documentaire│
                         │  (MRN, BRGM, CEPRI, ADEME, ...) │
                         │  + génération des recommandations│
                         └──────────────┬────────────────┘
                                        │  state.recommendations
                                        ▼
                         ┌──────────────────────────────────┐
                         │      digital_twin_agent            │
                         │  assemble la géométrie 3D (forme,   │
                         │  étages, toit, cave/sous-sol,       │
                         │  jardin, garage) + les zones de      │
                         │  risque/recommandations             │
                         │  -> contrat JSON pour le rendu       │
                         │     Three.js du front                │
                         └──────────────┬────────────────────┘
                                        │  state.digital_twin
                                        ▼
                                       END
```

Principes retenus :

- Les agents communiquent exclusivement via un **état partagé** (`TyphoonState`, un `TypedDict` versionné), lu et enrichi à chaque nœud du graphe. C'est ce state, géré par le runtime LangGraph, qui sert de bus de communication entre agents — pas d'appel direct d'un agent vers un autre.
- Le nœud `collector_agent` reste responsable en interne de la parallélisation des 5 appels API live (via `asyncio.gather`) et des 2 lookups locaux, pour préserver les temps de réponse quasi instantanés décrits dans le cahier des charges.
- Le nœud `digital_twin_agent` est le dernier maillon : il ne recalcule rien, il **assemble** la sortie des trois agents précédents (géométrie du bâti issue de `building_data`, scores issus de `risk_scores`, recommandations issues de `recommendations`) dans le contrat JSON unique attendu par la scène Three.js du frontend (voir [Jumeau numérique 3D](#jumeau-numérique-3d--contrat-de-sortie)).
- Un `checkpointer` LangGraph (SQLite en local, Postgres en prod) persiste l'état du graphe par diagnostic, ce qui permet de rejouer, d'auditer ou de reprendre un diagnostic interrompu.
- Le graphe de diagnostic est **unique et partagé** entre les trois cas d'usage ; ce qui diffère par cas d'usage, ce sont les routes API exposées côté backend et l'écran présenté côté frontend (devis assurance, décision de prêt, argumentaire de vente).

## Structure du dépôt

```
typhoon/
├── README.md
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # entrypoint FastAPI
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── diagnostic.py       # POST /diagnostic (commun aux 3 cas d'usage)
│   │   │       ├── assurance.py        # endpoints spécifiques assurance (devis, seuil de refus)
│   │   │       ├── banque.py           # endpoints spécifiques banque (score prêt)
│   │   │       ├── immobilier.py       # endpoints agents/promoteurs (recherche, argumentaire)
│   │   │       └── health.py
│   │   │
│   │   ├── agents/                     # orchestration LangGraph
│   │   │   ├── graph.py                # définition du StateGraph et des edges
│   │   │   ├── state.py                # schéma TyphoonState (état partagé inter-agents)
│   │   │   ├── collector_agent.py      # agent de collecte (live APIs + lookups locaux)
│   │   │   ├── scoring_agent.py        # agent de scoring de risque
│   │   │   ├── rag_agent.py            # agent de recommandations (RAG)
│   │   │   └── digital_twin_agent.py   # agent jumeau numérique (assemble le contrat 3D)
│   │   │
│   │   ├── connectors/                 # clients des sources externes
│   │   │   ├── bdnb.py
│   │   │   ├── georisques.py
│   │   │   ├── ign_altitude.py
│   │   │   ├── open_meteo.py
│   │   │   ├── catnat.py
│   │   │   ├── copernicus.py           # cache climatique PACA (API CDS, remplace DRIAS)
│   │   │   └── lookup/
│   │   │       ├── lookup.py           # DVF
│   │   │       └── departments.json
│   │   │
│   │   ├── rag/
│   │   │   ├── ingestion.py            # pipeline d'ingestion documentaire (MRN, BRGM, CEPRI, ...)
│   │   │   ├── vectorstore.py          # wrapper base vectorielle
│   │   │   └── retriever.py
│   │   │
│   │   ├── scoring/
│   │   │   └── risk_model.py           # méthode de calcul du score par aléa / partie du bâtiment
│   │   │
│   │   ├── digital_twin/
│   │   │   ├── geometry_builder.py     # dérive la géométrie (forme, étages, toit, cave, jardin...)
│   │   │   └── contract.py             # sérialisation du contrat JSON consommé par Three.js
│   │   │
│   │   ├── schemas/                    # modèles Pydantic (contrats API)
│   │   │   ├── property.py
│   │   │   ├── diagnostic.py
│   │   │   ├── recommendation.py
│   │   │   └── house_geometry.py       # schéma de la géométrie du jumeau numérique
│   │   │
│   │   ├── core/
│   │   │   ├── config.py               # settings (clés API, endpoints, seuils)
│   │   │   └── logging.py
│   │   │
│   │   └── db/
│   │       ├── models.py               # persistance diagnostics / checkpoints LangGraph
│   │       └── session.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── assurance/                      # front simple — parcours assureur / assuré
│   │   ├── index.html                  # accueil, formulaire, écran de traitement, scène 3D, devis
│   │   └── scene/
│   │       └── house-scene.js          # construction paramétrique de la maison Three.js
│   ├── banque/                         # front simple — parcours banque
│   └── agents-immobiliers/             # front simple — parcours agent / promoteur
│
├── data/
│   └── rag_sources/                    # documents bruts avant ingestion (MRN, BRGM, CEPRI, ...)
│
└── docs/
    ├── Documentation_projet_Typhoon.pdf
    └── typhoon_site.html               # prototype front de référence (parcours assurance + scène 3D)
```

## Les agents

### Matching d'artisans

Après génération du diagnostic, le frontend peut rechercher des entreprises
correspondant aux travaux d'une zone via `POST /artisans/match`. Le service
utilise exclusivement des sources publiques :

- entreprises RGE : jeu de données ADEME ;
- métiers non couverts par RGE (géotechnique, structure, radon, drainage) :
  API officielle Recherche d'entreprises et annuaires professionnels.

Le score retourné est un score objectif de correspondance (qualification
valide, proximité, coordonnées disponibles ou ancienneté). Il ne constitue
pas une note de qualité/prix. Une indisponibilité d'une API artisan est isolée
et ne fait pas échouer le diagnostic climatique principal.

Exemple de requête :

```json
{
  "adresse": "12 rue des Lilas, 33000 Bordeaux",
  "limite": 5,
  "zones": [{
    "zone": "toiture",
    "risques": ["canicule"],
    "recommandations": [{"mesure": "Isolation des combles"}]
  }]
}
```

### `collector_agent`

Interroge en parallèle les 5 API live (BDNB, Géorisques v1, IGN Altitude, Open-Meteo, CATNAT) via `asyncio.gather`, ainsi que le lookup local DVF et le cache régional Copernicus (projections climatiques, alimenté une fois via l'API CDS puis lu localement), et agrège le tout dans `state.building_data`. Ce périmètre de sources est amené à s'étoffer (ex. données cadastrales).

Une première implémentation fonctionnelle (indépendante de LangGraph pour l'instant, en attendant de la brancher dans le `StateGraph` complet) vit dans `backend/app/agents/collector_agent.py`, avec un connecteur par source dans `backend/app/connectors/` et un script de test en ligne de commande (`backend/app/cli.py`). Voir [`docs/GUIDE_ORCHESTRATEUR_API.md`](./docs/GUIDE_ORCHESTRATEUR_API.md) pour comment obtenir l'accès à chaque source et lancer un diagnostic sur une adresse réelle.

### `scoring_agent`

Consomme `state.building_data` et calcule un score de risque par aléa (inondation, sécheresse/RGA, mouvement de terrain, etc.) et par partie du bâtiment, écrit dans `state.risk_scores`. La méthode de calcul précise reste à spécifier (voir Roadmap).

### `rag_agent`

Agent conversationnel Retrieval-Augmented Generation : interroge la base vectorielle constituée à partir des sources institutionnelles (MRN, BRGM, CEPRI, ADEME, France Assureurs, CCR, AQC, ANAH) pour générer des recommandations de travaux justifiées et sourcées, écrites dans `state.recommendations`.

### `digital_twin_agent`

Dernier maillon du graphe. Il ne collecte ni ne calcule de risque : il **traduit** le diagnostic en variables directement consommables par la scène Three.js du front, à savoir la géométrie de la maison (forme, nombre d'étages, forme du toit, présence d'une cave, d'un sous-sol, d'un garage, d'un jardin) croisée avec les scores et recommandations déjà produits par `scoring_agent` et `rag_agent`.

Deux modes d'alimentation de la géométrie, par ordre de priorité :

1. **Champs explicites du formulaire** (forme du bien, toit, cave, jardin) lorsqu'ils sont saisis par l'utilisateur.
2. **Inférence par défaut** à partir de `state.building_data` (ex. BDNB) lorsque le formulaire ne les couvre pas encore — c'est le cas du prototype actuel, où la géométrie est figée (voir [Roadmap](#roadmap--points-ouverts)).

Le résultat est écrit dans `state.digital_twin` et correspond au contrat détaillé ci-dessous.

## Jumeau numérique 3D — contrat de sortie

C'est le contrat consommé par `frontend/*/scene/house-scene.js` (Three.js) pour construire la maison et la colorer par zone. Il reprend et étend le contrat déjà présent dans le prototype (`MOCK_DATA` de `docs/typhoon_site.html`), en séparant clairement la **géométrie** (nouveau, produit par `digital_twin_agent`) des **zones de risque** (déjà spécifiées dans le diagnostic) :

```json
{
  "geometry": {
    "footprint_shape": "rectangulaire",
    "floors_count": 2,
    "roof_shape": "deux_pans",
    "has_basement": true,
    "has_cellar": false,
    "has_garage": true,
    "garage_position": "ouest",
    "has_garden": true,
    "garden_surface_m2": 250
  },
  "score_global": 58,
  "zones": {
    "fondations": {
      "risque": 78,
      "niveau": "eleve",
      "alea_principal": "Retrait-gonflement des argiles",
      "justification": "Sol argileux identifié en zone d'aléa fort...",
      "recommandations": [
        { "travaux": "Renforcement des fondations par micropieux", "cout_estime": "9000-16000€", "gain_resilience": 30 }
      ]
    },
    "murs_nord": { "...": "..." },
    "murs_sud": { "...": "..." },
    "murs_est": { "...": "..." },
    "murs_ouest": { "...": "..." },
    "toiture": { "...": "..." },
    "sous_sol": { "...": "..." }
  },
  "projection_2050": {
    "score_global": 81,
    "zones": { "...": "même structure que ci-dessus, projetée à horizon 2050" }
  }
}
```

Points d'attention pour l'implémentation :

- Le bloc `geometry` est nouveau : c'est celui qui manque aujourd'hui au prototype (`W`, `D`, `floorH`, toit 2 pans et garage y sont codés en dur dans `house-scene.js`). `digital_twin_agent` doit produire ces valeurs pour que la scène s'adapte à chaque bien plutôt que de rejouer toujours la même maison.
- Le bloc `zones` reprend exactement les 7 zones cliquables déjà modélisées côté front (`fondations`, `murs_nord`, `murs_sud`, `murs_est`, `murs_ouest`, `toiture`, `sous_sol`), chacune avec son `risque` (0-100, sert au dégradé de couleur), son `niveau`, l'`alea_principal`, une `justification` et ses `recommandations`.
- `projection_2050` permet le bouton de bascule temporelle déjà présent dans le prototype (`2025` / `2050`).
- Le schéma Pydantic correspondant vit dans `backend/app/schemas/house_geometry.py` (bloc `geometry`) et `diagnostic.py` (bloc `zones` / `projection_2050`).

## Backend — communication inter-agents

Le backend est un service **FastAPI** qui expose le graphe LangGraph comme un service de diagnostic :

- Une requête entrante (`POST /diagnostic`) instancie une exécution du graphe (`graph.ainvoke(initial_state, config={"thread_id": ...})`).
- Le `thread_id` sert de clé de checkpoint : il permet de retrouver, auditer ou reprendre l'état d'un diagnostic donné.
- Les quatre agents ne communiquent jamais directement entre eux : chacun lit et complète le même objet `TyphoonState`, ce qui garde le graphe traçable et testable nœud par nœud.
- La réponse de `POST /diagnostic` renvoie directement le bloc `state.digital_twin`, c'est-à-dire le contrat prêt à être consommé par la scène Three.js (voir [Jumeau numérique 3D](#jumeau-numérique-3d--contrat-de-sortie)).
- Les routes spécifiques à chaque cas d'usage (`assurance.py`, `banque.py`, `immobilier.py`) réutilisent le même diagnostic de base et n'ajoutent que la logique propre au cas d'usage (calcul de devis, seuil de refus de dossier, génération d'argumentaire de vente).

## Frontend — un client par cas d'usage

Un front minimal par cas d'usage, chacun consommant l'API du backend. Le parcours **assurance** dispose déjà d'un prototype de référence (`docs/typhoon_site.html`) qui sert de base à `frontend/assurance` :

- **`frontend/assurance`** — vitrine, formulaire du bien (adresse, structure, toiture, sous-sol/cave...), écran de traitement qui reflète les étapes du graphe LangGraph (géocodage, Géorisques, projections climatiques, BDNB, fusion, recommandations, rendu 3D), puis la **scène 3D du jumeau numérique** : maison Three.js navigable à la souris, zones colorées par niveau de risque et cliquables (panneau de détail + recommandations), bascule de projection temporelle 2025/2050, simulation de devis à partir des travaux sélectionnés, et un assistant conversationnel branché sur `rag_agent`.
- **`frontend/banque`** — saisie d'un bien à financer, affichage du score de risque climatique pour instruction du dossier de prêt ; peut réutiliser la même scène 3D en lecture seule.
- **`frontend/agents-immobiliers`** — recherche de biens/parcelles avec critère de résilience climatique, génération d'un argumentaire de vente basé sur le score et les travaux réalisés/recommandés.

Ces fronts restent volontairement simples à ce stade (un écran de saisie, un écran de résultat, la scène 3D) ; ils seront étoffés une fois le MVP validé. La construction de la scène 3D est paramétrique : `house-scene.js` doit lire le bloc `geometry` du contrat plutôt que les dimensions codées en dur du prototype actuel.

## Sources de données du diagnostic

| Source | Type | Rôle |
|---|---|---|
| BDNB | Live — `api.bdnb.io` | Caractéristiques physiques du bâti (structure, matériaux, année de construction). |
| Géorisques v1 | Live — `georisques.gouv.fr` | Référentiel officiel des risques naturels et technologiques par adresse. |
| IGN Altitude | Live — `data.geopf.fr` | Altimétrie, notamment pour l'exposition au risque d'inondation. |
| Open-Meteo (Climate API) | Live — `climate-api.open-meteo.com` | Projections et historiques climatiques. |
| CATNAT | Live — `georisques.gouv.fr` | Historique des arrêtés de catastrophe naturelle sur la commune. |
| DVF | Lookup local | Transactions immobilières, contexte du bien. |
| Copernicus (CDS) | Lookup local (alimenté via API CDS) | Indicateurs climatiques régionalisés (canicule, sécheresse, précipitations extrêmes...), remplace DRIAS. |

## Base documentaire de l'agent RAG

| Organisme | Contenu | Priorité |
|---|---|---|
| MRN — Mission des Risques Naturels | Référentiels de réduction de la vulnérabilité de l'habitat (inondation, sécheresse) | Prioritaire — source la plus directement exploitable |
| BRGM | Renforcement des fondations, RGA / retrait-gonflement des argiles | Prioritaire — volet sécheresse/RGA |
| CEPRI | Adaptation des logements aux inondations | Prioritaire — volet inondation |
| CCR | Modélisation de l'impact des catastrophes naturelles | Complémentaire — argumentaire ROI |
| ANAH | Aides financières (MaPrimeRénov', subventions locales) | Complémentaire — argumentaire financier |
| ADEME | Guides de rénovation énergétique et adaptation | Base de connaissances générale |
| France Assureurs | Position et données sectorielles sur les risques climatiques | Cadrage sectoriel |
| AQC | Fiches Pathologie et bonnes pratiques (programme PACTE) | Détail technique |

Ordre d'ingestion recommandé : MRN, puis BRGM et CEPRI, puis le reste des sources.

## Installation

Prérequis : Python 3.11+, Node 18+, une base vectorielle locale ou hébergée (ex. Chroma, Qdrant), un LLM accessible via API (ex. Anthropic, OpenAI).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload

# Frontend (par cas d'usage, exemple assurance)
cd frontend/assurance
npm install
npm run dev
```

`backend/requirements.txt` (dépendances principales) :

```
fastapi
uvicorn[standard]
pydantic>=2
langgraph
langchain
langchain-anthropic
langchain-community
httpx
chromadb
python-dotenv
sqlalchemy
```

## Variables d'environnement

Extrait de `.env.example` :

```
# LLM
ANTHROPIC_API_KEY=

# Base vectorielle (RAG)
VECTORSTORE_PATH=./data/vectorstore

# Sources externes
BDNB_API_KEY=
GEORISQUES_BASE_URL=https://georisques.gouv.fr
IGN_ALTITUDE_BASE_URL=https://data.geopf.fr
OPEN_METEO_BASE_URL=https://climate-api.open-meteo.com

# Persistance / checkpoints LangGraph
DATABASE_URL=sqlite:///./typhoon.db
```

## Roadmap / points ouverts

Pour un plan resserré sur 2 semaines (périmètre PACA uniquement, cas d'usage assurance seul), voir [`docs/ROADMAP_MVP_PACA.md`](docs/ROADMAP_MVP_PACA.md).

Le prototype front actuel (`docs/typhoon_site.html`) sert de cible fonctionnelle mais fonctionne aujourd'hui sur une géométrie figée et des données mockées (`MOCK_DATA`) ; il reste à le brancher sur le backend réel :

- Faire produire par `digital_twin_agent` la géométrie réelle du bien (forme, étages, toit, cave/sous-sol, garage, jardin) en remplacement des dimensions codées en dur (`W`, `D`, `floorH`, toit 2 pans systématique) de `house-scene.js`.
- Étendre le formulaire du prototype avec les champs de géométrie manquants (forme du toit, présence d'un jardin, forme du bâti) qui alimenteront directement `digital_twin_agent`.
- Étoffer les sources du diagnostic de base (ex. données cadastrales).
- Prioriser l'ingestion documentaire de l'agent RAG : MRN, puis BRGM et CEPRI.
- Spécifier précisément la méthode de calcul du score de risque par partie du bâtiment et par aléa.
- Cadrer le format du formulaire de saisie côté assureur (champs obligatoires, informations complémentaires).
- Définir les règles métier permettant à l'assureur/la banque d'écarter un client selon un seuil de risque.
- Brancher l'assistant conversationnel du prototype (actuellement des réponses simulées) sur `rag_agent`.
- Relier le module de devis/certification du prototype (calcul de prime, gain de résilience) à un service de tarification côté backend.

## Glossaire

| Terme | Définition |
|---|---|
| RAG | Retrieval-Augmented Generation : un agent conversationnel cherche l'information dans une base documentaire fiable avant de générer sa réponse. |
| RGA | Retrait-Gonflement des Argiles : phénomène lié à la sécheresse provoquant des fissures sur le bâti. |
| DVF | Demandes de Valeurs Foncières : base publique des transactions immobilières. |
| Copernicus | Service climatique européen (Copernicus Climate Change Service) ; sa Climate Data Store (CDS) fournit ici les indicateurs climatiques régionalisés, en remplacement de DRIAS. |
| BDNB | Base de Données Nationale des Bâtiments. |
| CATNAT | Régime « Catastrophes Naturelles » : historique des arrêtés officiels. |
| Jumeau numérique | Représentation numérique structurée d'un bien, découpée par partie du logement, avec un score de risque par partie. |
