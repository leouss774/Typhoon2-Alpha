## Contexte

On a un système multi-agent d'analyse de vulnérabilité climatique de maisons individuelles.
Deux parties existent déjà séparément :

1. **Agent Analyse de risque** (ton code) : géocodage + appels parallélisés à des APIs
   (Copernicus, Géorisques, DRIAS, BDNB...) + calcul déterministe du score de risque.
2. **Agent Recommandations** (fourni en pièce jointe, dossier `recommandations-agent/`) :
   RAG sur un référentiel documentaire (normes, guides ADEME/CSTB/BRGM...), produit des
   recommandations de travaux sourcées à partir d'un JSON "maison".

Le tout tourne sur **LangGraph** pour l'orchestration et **FastAPI** pour exposer le backend au
front.

## Ce qu'il faut faire

Intègre `recommandations-agent/` comme un **nouveau nœud du graphe LangGraph**, placé juste après
le(s) nœud(s) d'analyse de risque, de façon à ce que sa sortie soit directement branchée sur
l'entrée du nœud recommandations, sans transformation manuelle de schéma.

### 1. Copier le repo dans le projet

Décompresse `recommandations-agent/` dans le repo backend (ex: `backend/app/recommandations/` ou
Pas besoin de relancer l'extraction, le
référentiel est déjà construit.

### 2. Refactorer `agent2_rag.py` en fonction importable

Le script est actuellement un CLI (`argparse`, écrit sur disque). Pour l'utiliser comme nœud
LangGraph, il faut l'exposer comme une fonction pure appelable :

```python
def generate_recommendations(house: dict, index: list) -> dict:
    ...
    return result  # même structure que aujourd'hui data/resultat.json
```

Point important : **l'index (`data/index.json`) doit être chargé une seule fois au démarrage de
l'app FastAPI** (dans un `lifespan`/`startup` event), pas rechargé à chaque requête depuis le
disque — sinon chaque appel relit un JSON qui peut être gros. Garde-le en mémoire (variable globale
ou état d'app FastAPI), et passe-le en paramètre à `generate_recommendations`.

Les appels Mistral (`chat_json`, `embed_texts`) sont synchrones. Dans un contexte FastAPI/async,
soit tu les exécutes dans un threadpool (`run_in_executor` ou `asyncio.to_thread`), soit tu passes
sur le client Mistral async s'il est disponible dans le SDK — à voir selon ce qui est le plus
simple à intégrer dans l'existant.

### 3. Ajouter le nœud au graphe LangGraph

Ajoute un nœud `recommandations` après le(s) nœud(s) de calcul du score de risque, qui prend en
entrée le state produit par l'analyse et appelle `generate_recommendations`.

### 4. Aligner les noms de champs — contrat JSON exact attendu

**C'est le point critique.** L'agent recommandations attend en entrée exactement ce schéma :

```json
{
  "adresse": "12 rue des Lilas, 33000 Bordeaux",
  "bien": {
    "type": "maison individuelle",
    "annee_construction": 1975,
    "materiaux": {"murs": "parpaing", "toiture": "tuiles"},
    "coordonnees": {"lat": 44.8378, "lon": -0.5792}
  },
  "zones": [
    {"zone": "fondations", "risques": ["retrait_gonflement_argiles"]},
    {"zone": "toiture", "risques": ["tempete", "grele"]}
  ]
}
```

garde ta sortie à toi et adapte mon code en conséquence.

Attention en particulier à :
- **`risques`** : les valeurs doivent être normalisées en minuscules avec underscores et
  correspondre au vocabulaire utilisé dans le référentiel (`retrait_gonflement_argiles`,
  `inondation`, `tempete`, `grele`, `canicule`, `secheresse`, `feu_vegetation`, `submersion`,
  `ruissellement`). Si l'agent d'analyse utilise d'autres libellés (ex: "RGA", "submersion marine"),
  il faut soit harmoniser le vocabulaire des deux côtés, soit ajouter un mapping de normalisation.
- **`zone`** : idem, aligne les noms de zones/composants de la maison (`fondations`, `toiture`,
  `facade`, `menuiseries`, `sous_sol`...) avec ce que produit l'analyse (BDNB donne peut-être
  d'autres libellés à mapper).

### 5. Sortie du nœud recommandations

Le state final du graphe doit contenir la sortie de `generate_recommendations`, structurée par
zone (risques + recommandations sourcées), c'est ce format qui sera consommé par l'agent 3
(jumeau numérique 3D) :

Par exemple :
```json
{
  "adresse": "...",
  "bien": {...},
  "zones": [
    {
      "zone": "toiture",
      "risques": ["tempete", "grele"],
      "recommandations": [
        {
          "mesure": "...",
          "type": "recommandation_source|obligation_locale|regle_consolidee|estimation_cout|info_aide",
          "cout_estime": {...} ou null,
          "aide": {...} ou null,
          "sources": [{"fiche_id": "...", "source_id": "...", "extrait_exact": "..."}]
        }
      ]
    }
  ]
}
```
A changer en fonction ed la sortie de ton noeud analyse.
