# RE-AUDIT #2 — Typhoon2-Alpha `feature/restructure` (après vos corrections, 02/08/2026)

> Re-clone frais de la branche, comparaison directe avec le premier re-audit. La plupart des points Sprint A/B sont réglés. **Une régression critique nouvelle a été détectée** (§1), invisible dans le premier passage car le fichier concerné n'existait pas encore à ce moment-là.

---

## 0. Résumé

**Sprint A (nettoyage) : fait, proprement.**
**Sprint B (recommandations Mistral) : fait, très bien fait.**
**Nouveau problème critique introduit entre les deux passages : deux connecteurs de géocodage coexistent, et celui utilisé par `/diagnostic/adresse` pointe vers une API décommissionnée.**

---

## 1. 🔴 Critique nouveau — `/diagnostic/adresse` appelle une API de géocodage morte

Deux connecteurs de géocodage existent maintenant dans le repo :

| Fichier | Source | Statut |
|---|---|---|
| `app/connectors/geocodage_connector.py` | `api-adresse.data.gouv.fr` (ancienne API Adresse / BAN) | **Décommissionnée fin janvier 2026** — d'après le commentaire que vous avez vous-même écrit dans l'autre fichier |
| `app/connectors/geocoding.py` (nouveau) | `data.geopf.fr/geocodage` (Géoplateforme IGN, successeur officiel) | Actuel, correct, avec `geocode_address`, `reverse_geocode`, `search_municipalities` |

**Le problème** : `backend/app/api/routes/diagnostic.py` importe toujours l'ancien connecteur :
```python
from app.connectors.geocodage_connector import AdresseNonTrouveeError, geocoder_adresse
```
Le nouveau `geocoding.py` (IGN) a bien été créé et est déjà branché sur son propre routeur (`app/api/routes/geocoding.py`, monté sur `/api/...` dans `main.py`) — probablement pour l'autocomplétion d'adresse côté front. **Mais personne n'a mis à jour `/diagnostic/adresse` pour utiliser ce nouveau connecteur.**

**Conséquence concrète** : `GET /diagnostic/adresse` appelle aujourd'hui une API qui, selon votre propre documentation interne, ne répond plus depuis fin janvier 2026. Tous les rapports générés par ce endpoint échouent probablement en 502/422 en production réelle (je ne peux pas le confirmer par un appel réseau live depuis mon environnement, mais le commentaire du code est sans ambiguïté sur la date de décommissionnement).

**Pourquoi ce n'est pas apparu dans les tests** : `test_adresse_georisques.py` mocke `app.connectors.geocodage_connector.httpx.AsyncClient` directement — les tests ne font jamais de vrai appel réseau, donc ils passent qu'importe si l'API réelle derrière est morte ou vivante. C'est un angle mort classique du mock : le test valide la logique interne, pas la validité de l'URL appelée.

**Action immédiate, avant tout autre sprint** :
```python
# diagnostic.py — remplacer
from app.connectors.geocodage_connector import AdresseNonTrouveeError, geocoder_adresse
# par
from app.connectors.geocoding import GeocodingError, geocode_address
```
et adapter les deux call sites (`geo = await geocoder_adresse(q)` → `geo = await geocode_address(client, q)`, `geo.score`/`geo.label`/`geo.code_insee` → `geo.score`/`geo.label`/`geo.citycode`). Une fois fait, **supprimer `geocodage_connector.py`** (pas de raison de garder un connecteur mort dans le repo — même risque que la doublette `typhon_risk_engine`, à ne pas laisser trainer une seconde fois).

Puis mettre à jour le test : remplacer les mocks `geocodage_connector` par des mocks sur `geocoding.py`, et ajouter un test qui vérifie explicitement que `/diagnostic/adresse` n'importe plus jamais `geocodage_connector`.

---

## 2. Sprint A — vérifié, résolu

| Point | Statut réel |
|---|---|
| `load_index()` appelé deux fois | ✅ Un seul appel, dans un `try/except`, commentaire clair expliquant le choix fail-soft |
| Imports dupliqués dans `main.py` | ✅ Fusionnés en une ligne |
| `typhon_risk_engine` sans statut clair | ✅ `README.md` ajouté, statut "EN MIGRATION — NE PAS UTILISER EN PRODUCTION", source de vérité explicitement pointée vers `risk_model.py` |
| Front promoteurs orphelin sans avertissement | ✅ Bannière rouge "Module en reconstruction" ajoutée, avec lien de repli vers le diagnostic adresse |

C'est du travail propre — la bannière cite même le document d'audit précédent par son nom, ce qui est une bonne pratique de traçabilité pour la suite.

---

## 3. Sprint B — vérifié, bien fait, une nuance

`RecommandationsIA` + `recommander()` dans `adresse_recommandations.py` respectent scrupuleusement les règles demandées :
- Le prompt utilisateur (`_build_user_prompt`) **filtre explicitement** `catnat_historique`, `erreurs_partielles`, `avertissement` — ne transmet que les champs utiles (aléas, niveaux, zonage). C'est plus strict que ce que j'avais proposé, et c'est une bonne chose.
- Consigne explicite au modèle : *"Ne mentionne JAMAIS de scores numériques exacts issus du rapport"* et *"Ne génère AUCUNE information absente du rapport"* — directement dans le system prompt, pas seulement dans un commentaire. Bien.
- Fail-soft réel à trois niveaux : clé API absente → `None` immédiat sans log ERROR ; `mistralai` non installé → `None` avec warning ; erreur/timeout Mistral → `None` avec warning. Aucun chemin ne remonte d'exception jusqu'au handler FastAPI.
- Appel synchrone wrappé dans `asyncio.to_thread` — ne bloque pas la boucle événementielle, cohérent avec le SDK `mistralai` 2.x qui est sync.

**Petite nuance, pas bloquante** : `max_retries=2` dans `chat_json(...)` — si chaque retry attend un timeout complet côté Mistral, `/diagnostic/adresse` peut mettre plusieurs secondes à répondre même en cas d'échec total, alors que le rapport factuel est déjà prêt bien avant. Vous l'aviez vous-même noté dans le plan initial ("appel non bloquant, le rapport factuel s'affiche immédiatement") — actuellement l'implémentation attend la résolution de `recommander()` avant de renvoyer la réponse HTTP (`report.recommandations = await recommander(report)` avant le `return`), donc ce n'est pas encore vraiment non-bloquant du point de vue du client HTTP, même si ça ne bloque pas la boucle asyncio globale du serveur. À corriger si la latence perçue devient un problème : streaming SSE, ou renvoyer le rapport tout de suite et les recommandations via un second appel/polling.

---

## 4. Ce qui reste, dans l'ordre

### Sprint A2 — urgence avant tout déploiement
1. Basculer `/diagnostic/adresse` sur `geocoding.py` (IGN Géoplateforme), supprimer `geocodage_connector.py`.
2. Mettre à jour `test_adresse_georisques.py` en conséquence.
3. Ajouter un test d'intégration (même léger, avec un vrai appel réseau optionnel derrière un flag `--run-network-tests`) pour éviter qu'un connecteur mort passe à nouveau inaperçu derrière des mocks parfaits.

### Sprint B2 — latence perçue (mineur)
4. Découpler la réponse HTTP du rapport factuel de l'attente Mistral : soit renvoyer immédiatement avec `recommandations: "en_cours"` puis un endpoint de polling, soit accepter la latence actuelle si elle reste sous ~3-4s en pratique (à mesurer).

### Sprint C — toujours en attente (déjà identifié précédemment)
5. Le mode zone reste à reconstruire. **Point positif inattendu** : le front `promoteurs/index.html` appelle déjà `/diagnostic/zone` avec le bon contrat (`bounds`, `spacing_km`, `max_points`, `land_only`) — quelqu'un a corrigé la forme de la requête même si la route backend n'existe pas encore. Quand vous reconstruisez `/diagnostic/zone-lite`, le front est donc déjà prêt côté contrat, juste à renommer l'URL appelée ou à exposer la route sous ce nom exact.
6. Rate limiting toujours absent sur `georisques.py` — pas encore un problème en usage adresse-unique, mais à ajouter avant Sprint C (le mode zone va démultiplier les appels).

---

## 5. Prompt court (agent de code)

> Priorité unique et immédiate : dans `backend/app/api/routes/diagnostic.py`, remplace l'import de `app.connectors.geocodage_connector` (API décommissionnée fin janvier 2026) par `app.connectors.geocoding` (Géoplateforme IGN, déjà utilisé par `app/api/routes/geocoding.py`). Adapte les accès aux champs (`GeocodeResult.citycode` au lieu de `GeocodageResult.code_insee`). Supprime ensuite `geocodage_connector.py` du repo. Mets à jour `backend/tests/test_adresse_georisques.py` pour mocker `app.connectors.geocoding` au lieu de l'ancien module, et ajoute un test qui échoue si `diagnostic.py` importe encore `geocodage_connector` (par exemple via un test d'introspection sur les imports du module).
