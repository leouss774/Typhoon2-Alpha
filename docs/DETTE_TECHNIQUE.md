# Audit de dette technique — Typhoon2-Alpha

**Date :** 6 août 2026
**Périmètre :** dépôt complet (backend FastAPI/LangGraph, frontends, moteur de règles, docs)
**Volumétrie :** ~17 400 lignes Python · 472 fichiers versionnés · 106 commits · 175 tests

---

## 1. Synthèse

Le projet est **fonctionnellement riche mais structurellement dispersé**. Trois constats dominent :

0. **Le dépôt est aveugle** : faute de `.gitattributes`, `git status` signale 351 fichiers modifiés alors que **2 le sont réellement**. Tant que ce point n'est pas corrigé, aucune revue de code n'est possible sur ce projet. Correctif : 15 minutes (§3.6).
1. **Deux moteurs de risque coexistent**, dont un — `typhon_risk_engine/` (2 000+ LOC, 10 modules, ~90 tests, règles YAML versionnées) — n'est **jamais importé** par l'application. C'est le poste de dette le plus lourd en valeur immobilisée.
2. **Quatre frontends parallèles** rendent le même produit (HTML monolithe, React/Vite, prototype `docs/`, viewer Vue 2). Toute évolution UI doit être portée 2 à 4 fois.
3. **Le socle d'exploitation est absent** : aucune CI, aucun Dockerfile, dépendances Python non figées, timeouts HTTP absents sur 7 connecteurs sur 9. Le projet n'est pas déployable de façon reproductible.

La bonne nouvelle : le noyau métier est **testé sérieusement** (175 tests, dont des tests de régression et de sensibilité sur le moteur de règles) et l'architecture agents/connecteurs/schemas est propre. La dette est concentrée sur le périmètre, l'outillage et la documentation — pas sur la qualité du code métier lui-même.

**Effort total estimé : 12 à 16 jours-homme**, dont **3 jours couvrent 70 % du risque**.

---

## 2. Classement priorisé

`Priorité = (Impact + Risque) × (6 − Effort)` — Impact et Risque notés 1-5, Effort 1-5 (1 = trivial).

| # | Item | Catégorie | I | R | E | **Prio** | Charge |
|---|------|-----------|---|---|---|----------|--------|
| 1 | Pas de `.gitattributes` → 351 fichiers « modifiés » fantômes (CRLF) | Process | 5 | 5 | 1 | **50** | 0,25 j |
| 2 | `requirements.txt` sans versions figées (21 paquets) | Dépendances | 3 | 5 | 1 | **40** | 0,5 j |
| 3 | Timeouts HTTP absents sur 7 connecteurs / 9 | Code | 3 | 5 | 2 | **32** | 0,5 j |
| 4 | Aucune CI (ni GitHub Actions, ni pre-commit) | Infra | 4 | 4 | 2 | **32** | 1 j |
| 5 | 40 `print()` coexistent avec le logger (37 modules sans logger) | Code | 3 | 3 | 1 | **30** | 0,5 j |
| 6 | `CORS allow_origins=["*"]` en dur | Infra | 1 | 5 | 1 | **30** | 0,25 j |
| 7 | `http://127.0.0.1:8765` en dur en 4 endroits | Code | 3 | 3 | 1 | **30** | 0,25 j |
| 8 | Secrets sur disque (`.env`, `.env.txt` orphelin) | Infra | 1 | 5 | 1 | **30** | 0,25 j |
| 9 | README décrit une arborescence qui n'existe plus | Doc | 4 | 3 | 2 | **28** | 0,5 j |
| 10 | `index.json` de 18,6 Mo versionné dans git | Infra | 3 | 3 | 2 | **24** | 0,5 j |
| 11 | 31 `except Exception` + 6 `except:` nus + 5 `pass` muets | Code | 3 | 4 | 3 | **21** | 1,5 j |
| 12 | Deux pipelines artisans (`app/artisans` + `app/matching`) | Archi | 4 | 3 | 3 | **21** | 2 j |
| 13 | 26 URLs en dur dans `georisques.py` (contredit `config.py`) | Code | 3 | 2 | 2 | **20** | 0,5 j |
| 14 | Deux versions de three.js (0.128 vs 0.152) | Dépendances | 2 | 3 | 2 | **20** | 0,5 j |
| 15 | `typhon_risk_engine/` orphelin — 2 000 LOC jamais appelées | Archi | 5 | 4 | 4 | **18** | 3 j |
| 16 | Pas de Dockerfile / IaC (le README en promet un) | Infra | 3 | 3 | 3 | **18** | 1 j |
| 17 | 0 test frontend, aucun ESLint à la racine `frontend/` | Test | 3 | 3 | 3 | **18** | 1 j |
| 18 | 18 modules backend sans aucun test | Test | 4 | 4 | 4 | **16** | 3 j |
| 19 | Chemin obsolète `D:\Talan\Typhoon-2` dans `config.py` | Doc | 2 | 1 | 1 | **15** | 0,1 j |
| 20 | `@app.on_event("startup")` déprécié (FastAPI lifespan) | Code | 1 | 2 | 1 | **15** | 0,1 j |
| 21 | 2 zips résiduels dans `backend/` (dont un de 1 Mo) | Infra | 1 | 2 | 1 | **15** | 0,1 j |
| 22 | Fichiers-dieu : `gltf_builder.py` 1 404 l., `Zone.tsx` 1 404 l., `index.html` 5 215 l. | Code | 4 | 3 | 4 | **14** | 3 j |
| 23 | `scene-engine.js` — 2 270 lignes non typées dans un projet TS | Code | 4 | 3 | 4 | **14** | 2 j |
| 24 | 4 frontends parallèles pour le même produit | Archi | 5 | 4 | 5 | **9** | 5 j+ |
| 25 | `bim-viewer` : Vue 2 (EOL), webpack 4, TS 3.9, axios 0.21 | Dépendances | 3 | 5 | 5 | **8** | 5 j+ |

---

## 3. Détail par catégorie

### 3.1 Dette d'architecture

**#15 — `typhon_risk_engine/` est un moteur orphelin.**
`grep -rn "risk_engine" backend/app/` ne renvoie **rien**. Le sous-projet contient pourtant `engine.py`, `normalizer.py`, `confidence.py`, `rules_loader.py`, `transforms.py`, `canonical.py`, `questionnaire.py`, `collector_hardening.py`, un CLI, des règles YAML, ~90 tests (dont `test_nice_regression.py`, `test_sensitivity.py`, `test_rules_integrity.py`) et un outil d'analyse de sensibilité des pondérations. En production, c'est `app/scoring/risk_model.py` (690 lignes, sans notion de confiance ni de pondération provisoire) qui décide.

*Justification métier :* vous maintenez, testez et faites évoluer deux définitions concurrentes du risque. Le moteur non branché est le plus rigoureux — c'est celui qui trace les pondérations provisoires non calibrées, ce qu'un assureur exigera. Chaque semaine de retard creuse l'écart entre les deux.

**#12 — Deux pipelines de matching artisans.**
`backend/app/api/routes/artisans.py` importe simultanément `app.artisans.service`, `app.matching.generate_rapport_artisans`, `app.matching.match_artisans_rge` et `app.matching.service`. Deux modèles de données, deux chemins de classification, un seul point d'entrée HTTP.

**#24 — Quatre frontends.**
`frontend/jumeau_numerique/` (HTML monolithe : 5 215 + 1 032 lignes), `frontend/src/` (React 19 + Vite), `docs/typhoon_site.html` (1 898 lignes, données `MOCK_DATA`), `frontend/bim-viewer/` (Vue 2 vendored, 163 fichiers). Le README lui-même documente `frontend/promoteurs/` et `frontend/artisans/` qui **n'existent plus**.

### 3.2 Dette de dépendances

**#2 — Aucune version figée côté Python.** `requirements.txt` liste 21 paquets — `fastapi`, `uvicorn`, `langgraph`, `langchain`, `langchain-anthropic`, `chromadb`, `pandas`, `xarray`, `netCDF4`… — sans borne. Seuls `pydantic>=2`, `mistralai>=2.0.0,<3.0.0` et `numpy>=1.26.0` sont contraints. Un `pip install -r` aujourd'hui et dans deux semaines ne produisent pas le même environnement — et `langchain` publie des breaking changes en version mineure.

**#25 — `bim-viewer` est un dépôt tiers gelé.** Vue 2.6 (fin de support décembre 2023), `@vue/cli-service` 4.5, webpack 4, TypeScript 3.9, `axios` 0.21 (CVE connues sur SSRF/prototype pollution), `element-ui` (Vue 2 uniquement). 163 fichiers versionnés, three.js dupliqué en `public/three/js/libs/` dont un `web-ifc-api.js` de 47 504 lignes.

**#14 — three.js divergent.** `frontend/package.json` → `^0.128.0` ; `frontend/bim-viewer/package.json` → `^0.152.0`. Deux moteurs 3D, deux API.

### 3.3 Dette de tests

175 tests existent — c'est solide. Mais la répartition est déséquilibrée : `typhon_risk_engine/` (non déployé) est bien mieux couvert que `app/` (déployé).

**#18 — 18 modules `app/` sur 57 sans aucun test**, dont les plus critiques :

| Module | LOC | Rôle |
|---|---|---|
| `matching/generate_rapport_artisans.py` | 614 | génération du rapport artisans |
| `connectors/dvf_lookup.py` | 402 | valorisation foncière |
| `agents/interpretation_agent.py` | 402 | interprétation LLM |
| `matching/match_artisans_rge.py` | 352 | appariement RGE |
| `property_id/generator.py` | 213 | identifiant de bien |
| `recommandations/rag_engine.py` | 164 | moteur RAG |
| `digital_twin/diagnostic_builder.py` | 175 | assemblage du contrat 3D |

**#17 — Frontend non testé.** Aucun `*.test.*` / `*.spec.*` dans `frontend/src/`. Aucun ESLint ni Prettier à la racine `frontend/` (le seul `.eslintrc.js` appartient à `bim-viewer`).

### 3.4 Dette de code

**#3 — Timeouts HTTP.** `config.py` définit `http_timeout_seconds: float = 15.0`, mais le grep des connecteurs donne : `bdnb.py` 0, `geocoding.py` 0, `open_meteo.py` 0, `ign_altitude.py` 0, `copernicus.py` 0, `annonces_lookup.py` 0, `georisques.py` 1, `dvf_lookup.py` 1. Un `data.geopf.fr` qui ne répond pas fait pendre une requête `/diagnostic` indéfiniment.

**#11 — Gestion d'erreurs trop large.** 31 `except Exception` + 6 `except:` nus dans `app/` et `typhon_risk_engine/`, dont 5 suivis d'un `pass`/`continue` muet. Une erreur de programmation (typo, `AttributeError`) est indiscernable d'une source externe indisponible.

**#5 — Logging à deux vitesses.** `core/logging.py` est bien conçu et **réellement adopté : 20 modules sur 57** appellent `get_logger(__name__)`. Mais **40 `print()`** subsistent en parallèle dans `app/`. Ces sorties échappent au niveau de log, au formatage horodaté et à toute redirection : en production derrière uvicorn, elles polluent stdout sans être filtrables. C'est une finition, pas une refonte — le socle est déjà là.

**#13 — URLs en dur, contrairement à la doctrine affichée.** Le docstring de `config.py` affirme : *« Rien n'est code en dur dans les connecteurs : ce fichier est le seul endroit a modifier si une URL change. »* En pratique : 26 URLs littérales dans `georisques.py`, 11 dans `matching/generate_rapport_artisans.py`, 11 dans `artisans/service.py`.

**#7 — Endpoint API en dur.** `http://127.0.0.1:8765` apparaît dans `frontend/src/zone/config.ts:9`, `frontend/api-config.js:7`, `frontend/jumeau_numerique/index.html:1392`, `frontend/jumeau_numerique/zone.html:425`. Aucun déploiement possible sans édition manuelle.

**#22/#23 — Fichiers-dieu.** `gltf_builder.py` (1 404), `Zone.tsx` (1 404), `footprint.py` (737), `risk_model.py` (690), `georisques.py` (604), `scene-engine.js` (2 270 lignes, **en JS non typé** dans un projet TypeScript), `jumeau_numerique/index.html` (5 215 lignes HTML+JS+CSS mêlés).

### 3.5 Dette de documentation

**#9 — Le README (458 lignes) décrit un projet différent du dépôt réel.** La section « Structure du dépôt » liste :

| Documenté | Réalité |
|---|---|
| `docker-compose.yml` | ❌ absent |
| `api/routes/assurance.py`, `banque.py`, `immobilier.py` | ❌ absents |
| `agents/rag_agent.py` | ❌ absent |
| `connectors/catnat.py`, `connectors/lookup/` | ❌ absents |
| `frontend/promoteurs/index.html` | ❌ absent |
| `frontend/artisans/index.html` | ❌ absent |
| `backend/.env.example` | ❌ absent (seul `.env.example` racine existe) |

*Justification métier :* un nouvel arrivant suit la section « Installation », ne trouve rien, et perd une demi-journée. Le README ne mentionne ni `typhon_risk_engine/`, ni `property_id/`, ni `bim-viewer/` — trois sous-systèmes réels.

**#19 — `config.py` référence `D:\Talan\Typhoon-2`**, alors que le projet vit désormais sur `Desktop\Typhoon2-Alpha`. Le commentaire renvoie à une contrainte d'espace disque qui n'a plus cours.

### 3.6 Dette d'infrastructure

**#4 — Aucune CI.** Pas de `.github/workflows` à la racine (le seul workflow appartient à `bim-viewer`, hérité du dépôt d'origine). 175 tests existent mais rien ne garantit qu'ils passent avant un merge.

**#1 — `git status` affiche 351 fichiers modifiés… dont 2 le sont réellement.**
C'est le poste le plus urgent du rapport, et le plus discret.

```
git status --porcelain          → 351 fichiers modifiés
git diff --numstat README.md    → 458 ajouts / 458 suppressions  (le fichier entier)
git diff --ignore-all-space -- backend/app  → 2 fichiers seulement :
      8  3  backend/app/core/config.py
      6  1  backend/app/recommandations/config.py
```

**Cause :** aucun `.gitattributes` dans le dépôt et `core.autocrlf` non configuré. Le projet est édité sous Windows (CRLF) contre un index en LF : git considère chaque ligne de chaque fichier comme réécrite.

**Conséquences concrètes :**
- `git status` et `git diff` sont **inexploitables** — le vrai travail (2 fichiers de config) est noyé sous 349 faux positifs
- Le prochain commit produira un diff de ~100 000 lignes, **impossible à relire en revue**
- `git blame` sera écrasé sur l'ensemble du dépôt, et toute la traçabilité avec
- Les conflits de merge deviendront systématiques et illisibles dès qu'une deuxième personne rejoint

**Correctif (~15 minutes, à faire avant tout autre chantier de ce rapport) :**

```bash
# 1. Sauvegarder les 2 vraies modifications
git diff --ignore-all-space -- backend/app > /tmp/vraies_modifs.patch

# 2. Créer .gitattributes à la racine
printf '* text=auto eol=lf\n*.ps1 text eol=crlf\n*.png binary\n*.jpg binary\n*.pdf binary\n*.zip binary\n' > .gitattributes

# 3. Renormaliser l'index
git add --renormalize .
git commit -m "chore: normalise les fins de ligne via .gitattributes"

# 4. Vérifier — doit renvoyer 2, pas 351
git status --porcelain | wc -l
```

**#10 — `backend/app/recommandations/data/index.json` : 18,6 Mo versionnés.** Chaque modification de l'index ajoute ~18 Mo à l'historique, définitivement. Le clone s'alourdit pour tout le monde.

**#8 — Secrets sur disque.** `backend/.env` et `backend/recommendation_travaux-main/.env.txt` (dossier ne contenant plus que ce fichier). Le `.gitignore` porte le commentaire : *« l'Explorateur Windows ajoute parfois .txt en enregistrant un .env : déjà arrivé deux fois sur ce projet »*. Le filet est en place, mais l'incident s'est produit deux fois — donc il se reproduira.

**#21 — Résidus binaires :** `backend/benchmark.zip` (100 Ko), `backend/c130d951e08d5438e3079c9d69a7101.zip` (1 Mo, nom de hash sans provenance).

---

## 4. Plan de remédiation en 3 phases

Conçu pour s'intercaler dans le flux de développement — aucune phase ne gèle les fonctionnalités.

### Phase 1 — Stabiliser (semaine 1, ~3 j)

*Objectif : rendre le projet reproductible et arrêter l'hémorragie de risque.*

1. **`.gitattributes` + `git add --renormalize`** — à faire **en premier**, avant tout autre commit : tant que `git status` ment sur 351 fichiers, aucune revue de code n'est possible (#1)
2. `pip freeze` → figer les 21 dépendances Python (#2)
3. Câbler `settings.http_timeout_seconds` dans les 7 connecteurs qui l'ignorent (#3)
4. CI GitHub Actions minimale : `pytest` + `tsc --noEmit` + `vite build` sur chaque PR (#4)
5. Remplacer les 40 `print()` par `get_logger(__name__)` — le logger est déjà adopté dans 20 modules (#5)
6. `CORS_ORIGINS` en variable d'environnement, `["*"]` réservé au dev (#6)
7. `VITE_API_BASE_URL` pour les 4 occurrences de `127.0.0.1:8765` (#7)
8. `git-secrets` ou hook pre-commit ; supprimer `recommendation_travaux-main/` et les 2 zips (#8, #21)

> **Ces 3 jours neutralisent ~70 % du risque de production.**

### Phase 2 — Clarifier (semaines 2-4, ~5 j)

*Objectif : une seule vérité par domaine métier.*

9. **Trancher sur `typhon_risk_engine/`** (#15) — la décision structurante du projet. Trois options :
   - **(a)** le brancher derrière `app/scoring/` et retirer `risk_model.py` → recommandé si la traçabilité des pondérations doit être présentée à un assureur
   - **(b)** en extraire les apports (confiance, pondérations provisoires) vers `risk_model.py`, puis archiver
   - **(c)** l'archiver tel quel dans une branche → à ne choisir que si le périmètre assurantiel est abandonné

   → Écrire une ADR (`/engineering:architecture`) avant de coder.
10. Fusionner `app/artisans` et `app/matching` derrière une interface unique (#12)
11. Réécrire le README à partir du dépôt réel, section « Structure » en premier (#9)
12. Rapatrier les 48 URLs en dur dans `config.py`, ou corriger le docstring (#13)
13. `index.json` hors git → artefact téléchargé au build ou git-lfs (#10)
14. Remplacer les `except Exception` muets par des exceptions typées + log (#11)
15. Dockerfile backend + `docker-compose.yml` (celui que le README promet déjà) (#16)

### Phase 3 — Consolider (continu, ~6 j)

*Objectif : empêcher la dette de revenir.*

16. Tests sur les 7 modules non couverts les plus lourds, en priorité `generate_rapport_artisans.py` et `dvf_lookup.py` (#18)
17. ESLint + Prettier + Vitest à la racine `frontend/`, seuil de couverture dans la CI (#17)
18. Migrer `scene-engine.js` (2 270 l.) vers TypeScript, module par module (#23)
19. Découper `gltf_builder.py` et `Zone.tsx` en suivant les frontières métier existantes (#22)
20. **Décider du sort de `bim-viewer`** (#25) — Vue 2 est en fin de vie : soit le sortir en dépendance npm externe, soit le remplacer par un composant IFC React. Ne pas le maintenir en l'état dans le dépôt.
21. Convergence des frontends : figer `frontend/src/` (React) comme cible unique, geler `jumeau_numerique/`, archiver `docs/typhoon_site.html` (#24)

---

## 5. Ce qui est déjà bien fait

À préserver lors de la remédiation :

- **175 tests** dont des tests de régression réels (`test_nice_regression.py`) et une analyse de sensibilité des pondérations — rare et précieux sur un moteur de scoring
- **Séparation agents / connecteurs / schemas / scoring** claire et lisible
- **`core/logging.py`** bien pensé (intention documentée, bruit HTTP muselé) — il ne manque que son adoption
- **Commentaires métier riches** : `config.py` explique *pourquoi* RapidAPI a été retiré (facturé dès la première requête), `main.py` explique *pourquoi* le CORS est ouvert (front en `file://`). Cette culture du « pourquoi » est un actif — elle rend l'audit possible.
- **`.gitignore` défensif**, écrit à partir d'incidents réels
- **Tests hors-ligne** (`test_api_diagnostic_offline.py`, `test_collector_offline.py`) : la suite ne dépend pas des API publiques

---

## 6. Métriques de suivi suggérées

| Indicateur | Aujourd'hui | Cible 3 mois |
|---|---|---|
| Faux positifs dans `git status` | 349 / 351 | 0 |
| Dépendances Python non figées | 18 / 21 | 0 |
| Connecteurs sans timeout | 7 / 9 | 0 |
| `print()` en production | 40 | 0 |
| Modules `app/` sans test | 18 / 57 | < 8 |
| Moteurs de risque | 2 | 1 |
| Frontends actifs | 4 | 1 |
| Taille du plus gros fichier versionné | 18,6 Mo | < 1 Mo |
| Couverture CI | 0 % | PR bloquantes |
