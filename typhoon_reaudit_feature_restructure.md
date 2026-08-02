# RE-AUDIT — Typhoon2-Alpha `feature/restructure` (branche réelle, inspectée le 02/08/2026)

> Méthode : clone réel de `feature/restructure`, lecture directe des fichiers cités. Ce document remplace les hypothèses des plans précédents par ce qui existe **vraiment** dans le code aujourd'hui.

---

## 0. Résumé exécutif

**Bonne nouvelle : le plan `adresse → Géorisques → RisqueReport` a été implémenté, et bien implémenté.** `GET /diagnostic/adresse` existe, fonctionne selon le principe fail-soft attendu, avec des tests unitaires mockés couvrant le nominal, l'échec de géocodage, et les erreurs partielles Géorisques. C'est un vrai progrès mesurable depuis les deux audits précédents.

**Mais trois choses n'ont pas suivi, et une régression est apparue :**

1. **Le module `/diagnostic/zone` a disparu entièrement** (route, `zone_scoring.py`, tout) — ce qui est cohérent avec la recommandation de ne pas construire sur des fondations simulées, **mais personne n'a débranché le front `promoteurs/index.html`**, qui appelle toujours `http://localhost:8765/api/v1/zone/assess`. Avant, cette route n'existait pas côté back (B1 historique) ; maintenant, même la route native `/diagnostic/zone` a disparu. Le front promoteurs est **totalement mort**, pas juste mal câblé.
2. **La doublette `backend/typhon_risk_engine/`** identifiée dans le premier audit est **toujours présente** au même endroit, avec son propre moteur de règles (`engine.py`, `rules/*.yaml`) séparé de `app/scoring/risk_model.py`. Non résolu.
3. **`load_index()` toujours appelé deux fois au démarrage** dans `main.py` — bug identique à celui du premier audit, pas corrigé, plus un import dupliqué (`from app.api.routes import artisans, diagnostic, health` suivi de `from app.api.routes import diagnostic, health, property_id...`).
4. **Aucune recommandation Mistral n'est branchée sur le flux `/diagnostic/adresse`** — le module RAG/Mistral existe (`app/recommandations/`), mais il est câblé sur le pipeline `digital_twin` complet (LangGraph), pas sur le nouveau rapport Géorisques léger. C'est la demande explicite du tour précédent, pas encore faite.

---

## 1. Ce qui a été corrigé depuis les audits précédents

| Constat original | Statut réel aujourd'hui |
|---|---|
| B1 — `mistralai` non pinné correctement | ✅ Corrigé : `mistralai>=2.0.0,<3.0.0` dans `requirements.txt`, cohérent avec l'usage SDK 2.x dans `mistral_client.py` |
| Pas de flux adresse unique → Géorisques | ✅ Fait : `GET /diagnostic/adresse`, géocodage BAN + Géorisques multi-endpoints + `RisqueReport` normalisé |
| Tests zone simulés qui ne testent rien | ✅ Remplacé par `test_adresse_georisques.py` : mocks propres, cas nominal + adresse absurde + erreurs partielles + bandes D03 |
| Vocabulaire de bandes incohérent (4 vs 5) | ✅ Un seul enum `NiveauRisque` à 5 niveaux, utilisé dans `risque_report.py`, avec fonction `niveau_from_score` centralisée |
| Fail-soft "jamais de donnée inventée" | ✅ Respecté dans `georisques.py` : chaque `_alea_*` renvoie `present=None` + `erreur` explicite si la source a échoué, jamais une valeur calculée sur du vide |

---

## 2. Ce qui n'a pas été fait / a régressé

### 2.1 🔴 Critique — Front promoteurs totalement orphelin

`frontend/promoteurs/index.html:354` pointe toujours vers `http://localhost:8765`, `:734` appelle `/api/v1/zone/assess`. **Aucune route de ce nom n'a jamais existé côté back**, et maintenant `/diagnostic/zone` (qui existait, même simulé) a aussi disparu. Ce front est un artefact mort qui va induire en erreur quiconque l'ouvre en pensant qu'il fonctionne.

**Décision à prendre, pas de mi-mesure** :
- (a) Retirer `frontend/promoteurs/index.html` du dépôt tant que le mode zone n'est pas reconstruit, ou
- (b) Le rebrancher immédiatement sur un futur `/diagnostic/zone-lite` qui interroge `/diagnostic/adresse` sur une grille de points (voir §4)

### 2.2 🔴 Critique — Doublette `typhon_risk_engine` toujours présente

`backend/typhon_risk_engine/risk_engine/` contient un moteur de règles YAML complet (P01–P14, `_common.yaml`) parallèle à `app/scoring/risk_model.py`. Aucune trace d'import croisé trouvée — deux moteurs de scoring vivent côte à côte sans qu'on sache lequel est la source de vérité. C'est le même risque qu'au premier audit : quelqu'un modifie l'un en pensant affecter le comportement réel, alors que l'API tourne sur l'autre.

**Action** : trancher — soit `typhon_risk_engine` est le futur remplaçant de `risk_model.py` (migration en cours, à documenter comme telle), soit c'est un résidu mort à supprimer. Actuellement aucun README/commentaire ne tranche.

### 2.3 🟠 Important — `main.py` : doublon `load_index()` + imports dupliqués

```python
from app.api.routes import artisans, diagnostic, health
from app.api.routes import diagnostic, health, property_id as property_id_router
...
load_index()  # appel direct
...
try:
    load_index()  # rappelé dans le try/except juste après
except Exception as exc:
    logger.warning(...)
```
Le premier appel n'est protégé par aucun `try/except` — s'il échoue, l'app ne démarre pas du tout, alors que le second appel (identique) est fail-soft. Résultat : le comportement réel dépend de l'ordre d'exécution, pas d'une intention claire. À fusionner en un seul appel protégé.

### 2.4 🟠 Important — Pas de recommandations Mistral sur `/diagnostic/adresse`

`RisqueReport` (schéma) n'a pas de champ `recommandations`. Le module `app/recommandations/` existe, mais son contrat d'entrée (`{"adresse", "bien", "zones": [...]}`, cf. docstring de `service.py`) est celui du pipeline `digital_twin` complet, pas celui du `RisqueReport` léger. Il faut soit :
- adapter `mapping.py` pour accepter un `RisqueReport` en entrée (probablement le plus simple, réutilise `mistral_client.py`/`rag_engine.py` existants), soit
- écrire un prompt dédié plus simple, spécifique au rapport adresse (ce que je proposais dans le plan précédent, §4 bis)

La deuxième option est plus cohérente avec le principe "le rapport adresse est un produit léger et rapide, séparé du diagnostic complet" — à trancher selon le temps disponible.

### 2.5 🟡 Moyen — Choix d'architecture Géorisques : multi-endpoints vs endpoint agrégé

Le plan précédent recommandait `resultats_rapport_risque` comme source principale (moins de code, comportement proche du rapport officiel). L'implémentation réelle interroge **7 endpoints distincts en parallèle implicite** (`gaspar/risques`, `catnat`, `azi`, `cavites`, `zonage_sismique`, `radon`, `mvt`) et calcule ses propres scores heuristiques par aléa.

**Ce n'est pas un bug — c'est un choix différent, avec un vrai avantage** : le rapport donne un score par aléa avec sa propre logique de gravité (ex. `inondation` pondère les CatNat historiques), plutôt que de dépendre du texte déjà agrégé par Géorisques. C'est plus de code à maintenir, mais plus de contrôle et de traçabilité par aléa — cohérent avec le principe D04 (traçabilité) déjà présent dans `risk_model.py`.

**Point d'attention réel** : aucune limite de débit n'est appliquée sur ces 7 appels (`georisques.py` n'a pas de semaphore/rate-limit). Pour un usage adresse-unique c'est sans risque immédiat (bien sous les 5 appels/s documentés par endpoint), mais si `/diagnostic/adresse` est un jour appelé en boucle sur une grille de points (mode zone), ce pattern saturera vite l'IP. À garder en tête pour §4.

---

## 3. Vérifications que je n'ai pas pu faire (à faire vous-même ou à me redemander)

- **Exécution réelle de `pytest`** : le clone a réussi, mais `pip install` a timeout sur `files.pythonhosted.org` dans mon environnement sandboxé — je n'ai donc **pas confirmé que la suite de tests passe actuellement**, seulement lu son contenu. À vérifier en local : `cd backend && pytest`.
- **Contenu réel de `frontend/promoteurs/index.html` au-delà des lignes citées** — je n'ai pas relu tout le fichier, seulement confirmé que l'URL et l'endpoint cassés sont toujours là.
- **`backend/data/`, `backend/scripts/`** — non inspectés, hors périmètre de cette passe.

---

## 4. Plan révisé — prochaines actions, dans l'ordre

### Sprint A — Nettoyage immédiat (< 1 jour, zéro risque)
1. Fusionner les deux appels `load_index()` en main.py, un seul bloc try/except.
2. Nettoyer les imports dupliqués dans `main.py`.
3. Trancher le sort de `backend/typhon_risk_engine/` : migration documentée ou suppression. Pas de statu quo.
4. Retirer ou désactiver explicitement `frontend/promoteurs/index.html` (bannière "en reconstruction" au minimum) tant que le mode zone n'existe pas.

### Sprint B — Recommandations Mistral sur `/diagnostic/adresse`
5. Étendre `RisqueReport` avec `recommandations: RecommandationsIA | None`.
6. Écrire `app/recommandations/adresse_recommandations.py` (prompt dédié, entrée = `RisqueReport.model_dump()` uniquement, jamais les données Géorisques brutes — même principe que le plan précédent §4 bis).
7. Appel Mistral non bloquant : le rapport factuel s'affiche immédiatement, les recommandations arrivent en complément (front : état "chargement" séparé).
8. Fail-soft strict : timeout/erreur Mistral → `recommandations=None`, jamais de blocage du rapport principal.

### Sprint C — Reconstruire un mode zone minimal, sans répéter l'erreur initiale
9. Ne PAS relancer `/diagnostic/adresse` par point de grille tel quel (pas de rate-limit, 7 appels Géorisques par point = trop lourd à l'échelle).
10. Construire un `zone_lite` qui : (a) regroupe les points par `code_insee` (la plupart des aléas Géorisques sont communaux, pas parcellaires), (b) appelle Géorisques **une fois par commune**, pas une fois par point, (c) réutilise `RisqueReport`/`AleaDetail` tel quel pour rester cohérent avec le rapport adresse unique.
11. Rebrancher `frontend/promoteurs/index.html` seulement une fois ce backend réel disponible — jamais avant.

### Sprint D — Rate limiting propre
12. Ajouter un semaphore/limiteur explicite dans `georisques_connector` (même léger) avant que le mode zone n'existe, pour éviter une régression silencieuse quand le trafic augmente.

---

## 5. Prompt court (agent de code)

> Priorité 1 (Sprint A) : dans `backend/app/main.py`, fusionne les deux appels à `load_index()` en un seul bloc `try/except` protégé, et supprime l'import dupliqué de `diagnostic`/`health`. Tranche explicitement le statut de `backend/typhon_risk_engine/` (ajoute un `README` disant "en migration, ne pas utiliser en prod" ou supprime le dossier — pas de statu quo). Ajoute une bannière "en reconstruction" en haut de `frontend/promoteurs/index.html` puisque `/api/v1/zone/assess` n'existe pas et n'a jamais existé côté backend.
>
> Priorité 2 (Sprint B) : étends `RisqueReport` (`app/schemas/risque_report.py`) avec un champ `recommandations: RecommandationsIA | None`. Crée `app/recommandations/adresse_recommandations.py` : le prompt Mistral ne doit recevoir QUE `RisqueReport.model_dump()`, jamais les données Géorisques brutes. Toute erreur ou timeout Mistral doit résulter en `recommandations=None` sans jamais bloquer la réponse de `/diagnostic/adresse`. Ajoute un test qui mocke un échec Mistral et vérifie que le rapport factuel est quand même renvoyé intact.
