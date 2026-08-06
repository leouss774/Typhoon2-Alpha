# AUDIT DÉTAILLÉ — MVP « Zone Risk » (promoteurs)

> Date : 01/08/2026 — Périmètre : `frontend/promoteurs/index.html` + backend `POST /diagnostic/zone`
> (`app/api/routes/diagnostic.py`, `app/scoring/zone_scoring.py`, `app/scoring/promoteur_report.py`)

## 0. Résumé exécutif

Le MVP « Zone Risk » est un **front autonome déconnecté du backend**. L'infrastructure back de qualité existe (`/diagnostic/zone`, `run_zone_risk_assessment`, collecteurs réels, rapport promoteur, connectors DVF/annonces), mais **rien n'est câblé** :

- URL d'appel inexistante (`/api/v1/zone/assess`) + **mauvais port** (8765 vs 8000) + **corps incompatible** (`zone` vs `bounds`) → le bouton « Lancer l'évaluation » ne peut jamais fonctionner.
- Le backend, lui, tourne sur des **données 100 % simulées** (bruit déterministe lat/lon) alors que la docstring de la route prétend utiliser « les VRAIES données ».
- Le « Rapport Promoteur » (Person 3) est écrit, testé, mais **jamais branché** à la route → section morte dans le front.
- Les points de la carte sont **tous orange** (`niveau_global` jamais renvoyé par le back).
- Incohérence sémantique : le moteur utilise 5 bandes D03 (Risk Engine), la zone en utilise 4 avec un vocabulaire « critique » différent.

**Le MVP ne peut pas s'afficher aujourd'hui. Réparer la connectique est un prérequis (≈ 1 journée).** Ensuite, l'itération porte sur : vraies données par point, périls calculés (pas des proxies de zones), polygones réels, DVF/annonces, projection 2050.

---

## 1. Architecture actuelle

```
frontend/promoteurs/index.html (777 l, MapLibre 4.7.1, backend dur : localhost:8765)
   │  POST /api/v1/zone/assess   ← route INEXISTANTE
   ▼
backend/app/api/routes/diagnostic.py:202  POST /diagnostic/zone   (contrat bounds)
   ▼
app/scoring/zone_scoring.py:365  run_zone_risk_assessment(bounds, spacing, max_points, land_only, collect_fn=None)
   │  collect_fn NON PASSÉ → _building_data_minimal() = SIMULATION
   ▼
compute_risk_scores() (risk_model.py:639)  → 7 zones (fondations, murs_*, toiture, sous_sol), score_global pondéré
   ▼
Agrégation par péril (proxies de zones) → rating_zone_to_dict()
   (sans rapport_promoteur, sans niveau_global, sans durée)
```

## 2. Constats bloquants — le MVP est déconnecté

| # | Sévérité | Constat | Preuve |
|---|----------|---------|--------|
| B1 | 🔴 Critique | Le front appelle `POST /api/v1/zone/assess` qui **n'existe pas**. Route réelle : `/diagnostic/zone` | `promoteurs/index.html:734` vs `diagnostic.py:202` |
| B2 | 🔴 Critique | ~~**Port faux** : `BACKEND_URL = 'http://localhost:8765'` mais uvicorn démarre sur **8000**~~ → **RÉVOQUÉ (02/08/2026)** : l'uvicorn est lancé avec `--port 8765` (README « port 8765 obligatoire », conventions repo) ; 8765 était correct, le port de `main.py:8` reflétait seulement la docstring d'une commande sans `--port`. Suivre le port réellement lancé, pas la docstring. | `promoteurs/index.html:354`, `main.py:8` |
| B3 | 🔴 Critique | **Corps incompatible** : front envoie `{zone:{lat_min,…}, max_concurrency, include_samples}` ; le back attend `{bounds:[4 floats], spacing_km, max_points, land_only}`. Pydantic ignore silencieusement les champs inconnus → 422 ou échec | `promoteurs/index.html:737-744` vs `diagnostic.py:179-199` |
| B4 | 🔴 Critique | « VRAIES données » est **faux** : la route n'appelle jamais `collect_fn` → `_building_data_minimal` (simulation). Le chemin réel (`collect()` gère "lat,lon") existe mais reste mort | `diagnostic.py:207-208` vs `diagnostic.py:223-228`, `zone_scoring.py:249-295`, `collector_agent.py:65` |
| B5 | 🟠 Important | **`rapport_promoteur` jamais généré** : module complet + 4 tests OK, mais ni la route ni `rating_zone_to_dict` ne l'appellent → section 4 du front jamais affichée | `promoteur_report.py:257`, `zone_scoring.py:547-577`, `promoteurs/index.html:700` |
| B6 | 🟠 Important | **Bug d'accents latent** : `_rating_from_mean` renvoie `"Eleve"/"Modere"` (sans accents) ; `promoteur_report` compare `"élevé"/"modéré"` (accents) → même branché, toutes les branches échoueraient → toujours « Faible » | `zone_scoring.py:489-497` vs `promoteur_report.py:85,94,103,144,…` |
| B7 | 🟠 Important | **Tous les points de la carte sont orange** : le front lit `p.score.niveau_global`, jamais renvoyé par `_result_to_point_dict` → fallback `'modere'` | `promoteurs/index.html:680`, `zone_scoring.py:522-533` |
| B8 | 🟡 Moyen | `duree_evaluation_s` attendu par le front, jamais renvoyé → toujours « — » | `promoteurs/index.html:614` |
| B9 | 🟡 Moyen | `land_only` accepté mais **inutilisé** dans `_collecter_point` | `zone_scoring.py:317-358` |

**Preuve empirique** (TestClient hors-ligne, Nice 9 points, 0,04 s) : réponse sans `rapport_promoteur`, sans `niveau_global`, sans `duree_evaluation_s`, `rating_global='Eleve'` sans accents, `V=50.0` constant sur les 7 zones.

## 3. Problèmes de fond (données / modèle)

- **Périls = proxies de zones, pas des scores réels** : inondation→sous_sol, RGA→fondations, tempête→moyenne des 4 murs, incendie→toiture, séisme→mix (`zone_scoring.py:500-519`). Aucun vrai score par péril n'existe dans `risk_model`.
- **`V=50.0` constant** : sans BDNB ni données de vulnérabilité, seul l'aléa simulé fait varier les points → carte peu différenciée (toutes les zones « modere » 46-56 dans le test).
- **Vocabulaire incohérent** : 4 bandes en zone (`faible<20, modere 20-44, eleve 45-69, critique>=70`, `zone_scoring.py:442-445`) vs 5 bandes D03 alignées Risk Engine dans `_niveau` (`risk_model.py:100-117`). Le « niveau » du diagnostic d'un bien et le « rating » de zone ne parlent pas le même langage.
- **Poids « par péril » du front décoratifs** (30/25/20/15/10 %, `promoteurs/index.html:627-633`) ≠ pondération réelle `_score_global` (fondations .25 / murs .40 / sous_sol .20 / toiture .15, `risk_model.py:628-636`).
- **« Zone » = boîte rectangulaire** : commune = point central ±0,04° ; « Dessiner » = 2 clics (bbox) ; « Parcelle » = `alert()` placeholder non implémenté. Aucun périmètre communal/polygone réel (`promoteurs/index.html:521-566`).
- **Aucune projection 2050 en mode zone** (contrairement au diagnostic bien) — la docstring le confirme (Copernicus « désactivé pour ce mode grille »).

## 4. Problèmes front (UX / technique)

- `alert()` pour les instructions de dessin, les erreurs réseau et le reset (`:516,527,755`).
- **Barre de progression simulée** (fake progress 0→90 % sur timer), non liée au backend réel (`:568-604`).
- Points en échec **silencieusement masqués** (filtre `:675`) ; `sample-info` ne compte que les affichés → un point mort invisible pour l'utilisateur.
- **Attribution carte absente** : style CartoDB dark-matter nécessite une attribution (« © OpenMapTiles © OpenStreetMap contributors ») — risque licence.
- Pas de bouton de rechargement des résultats hors « Nouvelle évaluation » ; pas d'état vide explicite.
- Mode « land_only » : le label front est « Terrain nu », mais aucun impact visible (flag mort côté back).
- Aucun test, aucun build, pas de séparation CSS/JS.

## 5. Problèmes backend / qualité

- **Docstrings contradictoires** : le module `zone_scoring` dit « sans appels API externes » ; la route dit « VRAIES données ». Le produit ment aux utilisateurs (`zone_scoring.py:1-12` vs `diagnostic.py:206-217`).
- `_niveau_alerte` inutilisé (`zone_scoring.py:121-126`) ; `score_pondere == score_moyen` (champ mort, `:477-478`).
- `_result_to_point_dict` sert à peu près à rien : le front n'utilise que `score_global` + `niveau_global` (absent).
- Route ne transmet pas `max_concurrency` (front l'envoie, hardcodé à 5 côté back).
- **`load_index()` appelé 2× au startup** (`main.py:52` et `:57`) — doublon.
- Le CSV annonces : **≈102 lignes, quasi 100 % Paris** (`annonces_maisons_france.csv`) alors que `annonces_lookup.py:113-114` prétend « couvre déjà toute la France » ; **non filtré par bounds** ; `climat_score` des marqueurs = **score simulé** (`annonces_lookup.py:92`, `score_point_climat`).
- DVF **désactivé par défaut** (`config.py:66`, `dvf_enabled=False`) ; CSV départementaux non versionnés → `/diagnostic/zone/prix` répond `disponible=False` sur ce poste.
- Le front promoteurs **n'utilise ni annonces ni prix DVF** (le back les a : `/diagnostic/zone/prix`, `/diagnostic/zone/annonces`).

## 6. Testabilité

- `test_run_zone_small` (`test_scoring.py:255-280`) définit un `fake_collect` **qu'il ne passe jamais** → il teste en réalité la simulation ; docstring fausse.
- `test_run_zone_land_only` (`:283-300`) : `assert rating.land_only is True` est trivial (ne teste aucun effet métier).
- **Aucun test de la route `/diagnostic/zone`** (contrat complet, rapport promoteur, niveau_global, erreurs par point). Le pipeline E2E de `test_api_diagnostic_offline.py` ne couvre que `/diagnostic`.
- Les 4 tests `promoteur_report` passent car ils injectent des ratings accentués à la main — ils ne détectent pas le bug B6.

## 7. Backlog d'itération (recommandé)

### Phase 0 — Réparer (brancher, ~1 jour)

1. Front : `BACKEND_URL` → port réel ; appeler `/diagnostic/zone` avec `{bounds:[lat_min,lon_min,lat_max,lon_max], spacing_km, max_points, land_only}`. (Ou aliasser `/api/v1/zone/assess` si tu veux garder l'URL.)
2. Back : brancher `generer_rapport_promoteur` dans `run_zone_diagnostic` + ajouter `rapport_promoteur` au dict, **et corriger les accents** (normaliser `rating_global` en ASCII ou comparer insensiblement aux accents).
3. Back : renvoyer `niveau_global` (depuis `_niveau(score_global)`) + `duree_evaluation_s` dans le contrat.
4. Front : colorer les dots par `niveau_global` réel ; afficher les points en erreur (gris + tooltip).
5. Supprimer le mode « Parcelle » (ou l'implémenter) ; remplacer `alert()` ; retirer les poids décoratifs par péril.

### Phase 1 — Données réelles

6. Brancher `collect_fn=collect` (optionnel) avec repli simulation par point + cache par coordonnées (TTL) ; réduire `max_points`/`spacing` par défaut pour rester < 30-60 s.
7. Calculer de **vrais scores par péril** à partir des libellés Géorisques (`risques_detail`) au lieu des proxies de zones.
8. Zones réelles : périmètres communaux/polygones (BAN), dessin libre, recherche commune par API adresse.

### Phase 2 — Produit promoteur

9. Activer DVF (README de téléchargement + flag), afficher prix au m² sur la carte.
10. Intégrer les annonces (avec vrais scores) dans ce front (comme le fait `jumeau_numerique`).
11. Onglet « 2050 » : heatmap de projection (`projection_2050`) — réutilisable tel quel depuis `compute_risk_scores`.
12. Couches réglementaires : PPRN, cavités, argiles (Géorisques a les flux).

### Phase 3 — Fiabilité / qualité

13. Tests E2E `/diagnostic/zone` (contrat figé : clés, `niveau_global`, `rapport_promoteur`, points en erreur) + fix des 2 tests `test_run_zone_*` tronqués.
14. Unifier les bandes (4 vs 5) : décider si la zone suit D03/Risk Engine.
15. Vraie progression streaming (SSE/WebSocket) au lieu de la barre simulée.

---

## 8. Fichiers référencés

| Fichier | Rôle |
|---------|------|
| `frontend/promoteurs/index.html` | Front « Zone Risk » (MapLibre) |
| `backend/app/api/routes/diagnostic.py` | Routes `/diagnostic`, `/diagnostic/zone`, `/diagnostic/zone/prix`, `/diagnostic/zone/annonces` |
| `backend/app/scoring/zone_scoring.py` | Grille, scoring par point, agrégation, `rating_zone_to_dict` |
| `backend/app/scoring/risk_model.py` | `compute_risk_scores`, `_score_global`, `_niveau` (D03 5 bandes) |
| `backend/app/scoring/promoteur_report.py` | Rapport promoteur (3 champs, règles déterministes) |
| `backend/app/agents/collector_agent.py` | `collect()` — chemin « vraies données » (gère "lat,lon") |
| `backend/app/connectors/annonces_lookup.py` | Annonces CSV + `score_point_climat` |
| `backend/app/connectors/dvf_lookup.py` | Prix DVF (désactivé par défaut) |
| `backend/app/core/config.py` | `dvf_enabled`, chemins lookup |
| `backend/app/main.py` | Port uvicorn (8000), CORS ouvert, `load_index()` ×2 |
| `backend/tests/test_scoring.py` | Tests zone + promoteur_report |
