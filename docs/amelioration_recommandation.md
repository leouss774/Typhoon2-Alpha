# Amélioration du module Recommandation
diagnostique et suggestions apres analyse du code backend (agents, RAG, scoring) et frontend (jumeau_numerique/index.html, typhoon_site.html).

---

## Table des matieres

1. [Performance : l'agent est trop lent](#1-performance)
2. [Concision : les recommandations sont trop longues](#2-concision)
3. [UI : l'affichage n'est pas joli](#3-ui)
4. [Plan de mise en oeuvre recommande](#4-plan)

---

## 1. Performance

### 1.1 Probleme identifie

Le noeud `recommandations_agent` (backend/app/agents/recommandations_agent.py) appelle `generate_recommendations` (backend/app/recommandations/service.py) qui boucle sur chaque **zone** puis chaque **risque** de maniere sequentielle.

Pour chaque couple (zone, risque) :
- 1 appel `embed_texts()` (Mistral embeddings)
- 1 appel `chat_json()` (Mistral chat via `mistral-large-latest`)
- Puis `time.sleep(THROTTLE_SECONDS)` de **3 secondes**

Avec 3 zones et 2 risques par zone : `3 x 2 x (embed + chat + 3s throttle + retries) = 12 appels API + ~18s de throttling`.

**Total estime : 30 a 50 secondes** juste pour le noeud recommandations.

### 1.2 Solutions proposees

#### A. Grouper tous les risques d'une zone dans un seul prompt Mistral (fort impact)

Actuellement, `service.py` appelle `chat_json` **par risque** :

```python
for risque in risques:
    query = f"Risque {risque} sur la zone {zone_name}..."
    ...
    result = chat_json(SYSTEM_PROMPT, user_prompt)
    zone_reco["recommandations"].extend(result.get("recommandations", []))
```

**Nouveau comportement** : un seul appel par zone, qui traite tous ses risques en une fois :

```python
risques_str = ", ".join(risques)
user_prompt = f"""ZONE TRAITEE: {zone_name}
RISQUES A TRAITER: {risques_str}
...
Reponds avec un JSON ou chaque recommandation a un champ "risque_concerne" precisant a quel risque elle se rapporte.
"""
result = chat_json(SYSTEM_PROMPT, user_prompt)
zone_reco["recommandations"].extend(result.get("recommandations", []))
```

**Gain** : Nombre d'appels chat divise par le nombre moyen de risques par zone (2-3x). **~-60% de temps.**

#### B. Reduire le THROTTLE_SECONDS (impact moyen)

Dans `backend/app/recommandations/mistral_client.py` :

```python
THROTTLE_SECONDS = 3  # actuel
```

Passer a `0.3` ou `0` et laisser le retry backoff (`_backoff_seconds`) gerer les rares 429.

```python
THROTTLE_SECONDS = 0.3
```

**Gain** : ~-40% du temps de throttling. **-10 a 15s.**

#### C. Paralléliser les zones avec asyncio.gather (fort impact)

Actuellement la boucle est synchrone (via `asyncio.to_thread` mais executee dans une seule thread). On peut lancer les appels pour toutes les zones en parallele :

```python
import asyncio

async def _process_zone(zone_info, index):
    # ... logique existante extraite dans une fonction async ...
    return zone_reco

tasks = [_process_zone(z, index) for z in house.get("zones", [])]
zones_out = await asyncio.gather(*tasks)
```

**Gain** : Temps total reduit au temps de la zone la plus longue. **-50% pour 3 zones.**

#### D. Utiliser mistral-small-latest pour les recommandations (impact fort)

Le modele `mistral-large-latest` est volontairement lent et cher pour garantir la qualite. Pour des recommandations de travaux, `mistral-small-latest` est largement suffisant et **2-3x plus rapide**.

```python
CHAT_MODEL = "mistral-small-latest"  # au lieu de "mistral-large-latest"
```

**Gain** : **-50 a 60%** du temps de reponse chat.

#### Embedding

Vérifier que les embeddings des fiches de l'index ne sont pas recalcules a chaque diagnostic. ils doivent etre precalculés et  gardés en memoire.

Deja partiellement fait (le `_index_cache` est module-level), mais verifier que les vecteurs sont bien charges et pas recalculés.

---

## 2. Concision

### 2.1 Probleme identifie

Le `SYSTEM_PROMPT` (backend/app/recommandations/service.py) demande des explications longues :

```
"explication" : 3 a 5 phrases en langage clair qui disent
(a) concretement quoi faire, (b) pourquoi cette mesure reduit
precisement CE risque sur CETTE zone, (c) toute precision utile...
```

Avec `max_tokens = 4000`, chaque recommandation produit un paragraphe de 5-8 lignes, ce qui submerge l'utilisateur.

### 2.2 Solutions proposees

#### A. Reduire la consigne de longueur (impact immediat)

Modifier le SYSTEM_PROMPT :

**Avant :**
```
"explication" : 3 a 5 phrases en langage clair qui disent (a)...
```

**Apres :**
```
"explication" : **1 a 2 phrases maximum**, concises et factuelles.
Dis (a) quoi faire concrètement et (b) pourquoi ça reduit le risque,
sans detail superflu. L'utilisateur est proprietaire, pas expert.
```

#### B. Reduire max_tokens (impact immediat)

```python
CHAT_MAX_TOKENS = 1000  # au lieu de 4000
```

Cela force le modele a etre concis et evite les digressions.

#### C. Structurer en deux niveaux (impact frontend)

Le backend pourrait stocker deux champs :

```json
{
  "mesure": "Traitement hydrofuge de la facade",
  "resume": "Application d'un hydrofuge sur les murs exterieurs pour prevenir l'infiltration d'eau de pluie.",
  "detail": "Faire appel a un professionnel pour appliquer un traitement hydrofuge... (3-5 phrases)",
  "cout_estime": {...},
  ...
}
```

Le frontend affiche d'abord le `resume`, avec un lien "Voir plus de details" qui affiche le `detail`.

#### D. Filtrer les champs superflus par defaut

Les champs `sources` (avec `fiche_id`, `source_id`, `extrait_exact`) et `aide.conditions` sont tres longs et rarement utiles en premiere lecture. Les masquer par defaut et les afficher dans un tooltip ou une section pliee.

---

## 3. UI

### 3.1 Probleme identifie

Le panneau `#info-panel` de 320px de large affiche toutes les recommandations en texte brut. Chaque recommandation contient :
- un badge de type
- le titre (mesure)
- l'explication complete (3-5 phrases)
- les metadonnees de cout
- le bloc d'aide
- les sources citees

C'est un mur de texte indigeste dans un espace etroit.

### 3.2 Solutions proposees

#### A. Cartes compactes avec accordeon

Chaque recommandation devient une carte cliquable (accordeon) :

```
+--------------------------------------------------------------------------------+
| Fondations                                                  Risque eleve    |
| Score : 42/100                                                              |
|                                                                              |
| [ Retrait-gonflement des argiles ]                                          |
|                                                                              |
|  > Reparation des fissures de facade                         Est. 3 500 - 5 000 EUR |
|    (cliquer pour voir les details)                                           |
|                                                                              |
|  > Drains perimetriques                                     Est. 8 000 - 12 000 EUR |
|    (cliquer pour voir les details)                                           |
+--------------------------------------------------------------------------------+
```

Chaque recommandation est repliee par defaut. Au clic, elle se devoile pour montrer l'explication courte, les aides et les sources en petit.

#### B. Onglets par zone

En haut du panneau, un barre d'onglets horizontale (Fondations / Toiture / Facade / Sous-sol) qui filtre les recommandations par zone. Chaque onglet affiche le nombre de recommandations et la priorite de la zone.

```
[ Fondations (3) | Toiture (2) | Facade (1) | Sous-sol (0) ]
```

L'onglet actif est surligne avec la couleur de la marque (brand). Les zones sans recommandation apparaissent en grise.

#### C. Indicateur de cout total

En-tete synthetique :

```
Cout total estime : 12 500 - 18 000 EUR
Couverture par les aides : 2 500 - 4 000 EUR
Reste a charge estime : 10 000 - 14 000 EUR
```

Avec eventuellement une barre de progression visuelle.

#### D. Badges de priorite/impact visuels

Chaque recommandation recoit un badge colorie indiquant le niveau de priorite :

- **Priorite haute** : fond rouge clair, texte rouge fonce (utiliser `#FDE7E2` / `#DC4B39`)
- **Priorite moyenne** : fond orange clair, texte orange fonce (utiliser `#FBEED9` / `#D98A2B`)
- **Priorite faible** : fond vert clair, texte vert fonce (utiliser `#E4F5EC` / `#1F9D6C`)

La priorite est deduite du niveau de risque de la zone combine a l'impact de la recommandation.

#### E. Typographie amelioree

- Titres des recommandations en **gras** et legèrement plus grands (15-16px)
- Explications en taille normale (13px) avec un interlignage confortable (1.5)
- Metadonnees (cout, source) en plus petit (11-12px) et couleur `muted`
- Utiliser la font `Inter` pour le corps et `Source Serif 4` pour les titres (deja definies dans le design system)

#### F. Separation visuelle claire

- Chaque recommandation separee par une ligne fine (`1px solid var(--border)`)
- La zone courante affichee dans un entete distinct avec le niveau de risque
- Les recommandations groupées par risque sous un sous-titre

#### G. Modele d'affichage propose (wireframe)

```
+------------------------------------------------------------------+
| [Fondations] [Toiture] [Facade] [Sous-sol]                        |
+------------------------------------------------------------------+
|                                                                    |
|  Fondations                               Risque : eleve          |
|  Score : 42/100                                                    |
|                                                                    |
|  Cout total estime : 12 500 - 18 000 EUR                          |
|  Reste a charge : 10 000 - 14 000 EUR                             |
|                                                                    |
|  --- Retrait-gonflement des argiles ---                            |
|                                                                    |
|  > Reparation des fissures de facade                               |
|    Priorite haute                           3 500 - 5 000 EUR     |
|    ✅ Eligeible MaPrimeRenov                                       |
|    Application d'un enduit elastique... [Voir plus]                |
|  ----------------------------------------------------------------- |
|  > Drains perimetriques                                            |
|    Priorite haute                           8 000 - 12 000 EUR    |
|    Installation de drains... [Voir plus]                           |
|                                                                    |
+------------------------------------------------------------------+
```

---

## 4. Plan de mise en oeuvre recommande

Les taches sont classees par priorite et impact. Chaque tache est independante et peut etre realisee separement.

### Phase 1 : Performance (gain immediat)

| Tache | Fichier | Effort | Gain |
|-------|---------|--------|------|
| 1. Reduire THROTTLE_SECONDS a 0.3 | `mistral_client.py` | 1 min | -15s |
| 2. Grouper les risques par zone dans un seul prompt | `service.py` | 30 min | -40% |
| 3. Passer a mistral-small-latest | `mistral_client.py` | 1 min | -50% |
| 4. Paralléliser les zones avec asyncio.gather | `service.py` + `recommandations_agent.py` | 45 min | -50% |

### Phase 2 : Concision (gain rapide)

| Tache | Fichier | Effort |
|-------|---------|--------|
| 5. Reduire la consigne a 1-2 phrases | `service.py` (SYSTEM_PROMPT) | 5 min |
| 6. Reduire CHAT_MAX_TOKENS a 1000 | `mistral_client.py` | 1 min |

### Phase 3 : UI (qualite perçue)

| Tache | Fichier | Effort |
|-------|---------|--------|
| 7. Cartes compactes avec accordeon | `index.html` (CSS + JS) | 2h |
| 8. Onglets par zone | `index.html` | 1h |
| 9. Badges de priorite visuels | `index.html` + backend (calcul priorite) | 1h |
| 10. Indicateur de cout total | `index.html` | 30 min |

### Estimation totale

- **Phase 1** : ~1h15 de dev -> **diagnostic 30-60% plus rapide**
- **Phase 2** : ~5 min -> **recommandations 3x plus courtes**
- **Phase 3** : ~4h30 -> **UI beaucoup plus professionnelle**

---

## Annexes

### Flux actuel (appels API)

```
Diagnostic 1 utilisateur
  |
  +-- zone: fondations
  |     +-- risque: retrait_gonflement_argiles
  |     |     +-- embed_texts("Risque retrait... fondations...")  [3s]
  |     |     +-- chat_json(recommandations)                      [3s + ~3s reponse]
  |     +-- risque: inondation
  |           +-- embed_texts("Risque inondation... fondations...") [3s]
  |           +-- chat_json(recommandations)                        [3s + ~3s reponse]
  |
  +-- zone: toiture
  |     +-- risque: tempete
  |     |     +-- embed_texts(...)  [3s]
  |     |     +-- chat_json(...)    [3s]
  |     +-- risque: grele
  |           +-- embed_texts(...)  [3s]
  |           +-- chat_json(...)    [3s]
  |
  +-- zone: facade
        +-- risque: tempete
        |     +-- embed_texts(...)  [3s]
        |     +-- chat_json(...)    [3s]
        +-- risque: canicule
              +-- embed_texts(...)  [3s]
              +-- chat_json(...)    [3s]

Total : 12 appels API, ~9x 3s throttling = ~27s de latence ajoutee seule,
         sans compter le temps de reponse Mistral (1-3s par appel).
```

### Flux apres optimisations proposees

```
Diagnostic 1 utilisateur
  |
  +-- zone: fondations (1 appel groupe)
  |     +-- embed_texts("Risques retrait+inondation sur fondations...")  [0s throttle]
  |     +-- chat_json(recommandations pour les 2 risques)                [0s throttle]
  |
  +-- zone: toiture (1 appel groupe)
  |     +-- [execute en parallele avec fondations]
  |     +-- embed_texts("Risques tempete+grele sur toiture...")
  |     +-- chat_json(...)
  |
  +-- zone: facade (1 appel groupe)
        +-- [execute en parallele]
        +-- embed_texts(...)
        +-- chat_json(...)

Total : 3 appels chat (au lieu de 6), 3 appels embed (au lieu de 6),
        throttling quasi-supprime, parallelise.
        -> temps estime : 5-10s au lieu de 30-50s.
```
