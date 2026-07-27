# Guide de démarrage — Agent Recommandations

## Étape 0 — Prérequis
- Python 3.10+
- Une clé API Mistral (console.mistral.ai)

## Étape 1 — Installer les dépendances

```bash
cd recommandations-agent
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
venv/bin/pip install -r requirements.txt
```

> **Note** : sur les systèmes récents (Debian/Ubuntu 24+), la commande est `python3`, pas `python`,
> et il est impératif d'utiliser un environnement virtuel. Le `.gitignore` inclut déjà `venv/`.

## Étape 2 — Configurer la clé API

Crée un fichier `.env` à la racine du projet :
```
MISTRAL_API_KEY=ta_cle_ici
```

> Le fichier `.env` est ignoré par git (déjà dans `.gitignore`).

## Étape 3 — Déposer tes documents sources

Mets tes PDF (ou .txt/.md) dans le dossier `documents/`. Par exemple les deux PDF locaux
mentionnés et tout autre document que tu veux inclure.

## Étape 3 bis — Enregistrer les sources (automatique ou manuel)

Chaque fichier dans `documents/` doit être référencé dans `data/sources_registry.csv` pour que
l'Agent 1 puisse associer chaque fiche extraite à son organisme et son lien d'origine.

### Option A : Auto-remplissage avec LLM (recommandé)

Le script `populate_registry.py` analyse le début de chaque document avec Mistral et suggère
l'organisme, le lien et la catégorie de chaque source :

```bash
# Voir ce qui serait ajouté sans rien modifier
venv/bin/python populate_registry.py --dry-run

# Ajouter les nouvelles entrées
venv/bin/python populate_registry.py
```

Le script détecte automatiquement les fichiers déjà présents dans le registre et ne les
réanalyse pas (sauf avec l'option `--overwrite`).

**Ce que Mistral analyse** : les 4000 premiers caractères de chaque document (titre, en-tête,
mentions d'organisme, etc.) pour deviner les métadonnées.

**Vérifie toujours les suggestions** dans le CSV après le passage du script — l'IA peut se
tromper !

### Option B : Saisie manuelle

Ouvre `data/sources_registry.csv` et ajoute une ligne par fichier avec :
- `source_id` : identifiant unique (S01, S02, etc.)
- `organisme` : nom de l'éditeur (ADEME, BRGM, CSTB...)
- `fichier` : **nom exact** du fichier (doit correspondre à ce qu'il y a dans `documents/`)
- `lien` : URL ou "fichier local"
- `categorie` : parmi `reglementaire_technique`, `officiel_technique`, `scientifique`,
  `scientifique_technique`, `technique`, `commercial`, `piste_commerciale_uniquement`,
  `non_classee`

## Étape 4 — Lancer l'extraction (Agent 1)

```bash
venv/bin/python agent1_extract.py
```

Ce script :
- lit chaque document, le découpe en morceaux (chunks),
- envoie chaque morceau à Mistral avec des consignes strictes de non-invention,
- collecte les fiches produites dans `data/referentiel.json`,
- marque automatiquement chaque fiche `validated` (si elle a une source + une citation exacte
  exploitable) ou `info_insuffisante` (rejetée de l'index).

Ça peut prendre plusieurs minutes selon le nombre/taille des documents (1 appel API par chunk).

Vérifie le résultat :
```bash
venv/bin/python -c "import json; d=json.load(open('data/referentiel.json')); print(len(d['fiches']), 'fiches, dont', sum(1 for f in d['fiches'] if f['statut_validation']=='validated'), 'validees')"
```

## Étape 5 — Construire l'index vectoriel

```bash
venv/bin/python build_index.py
```

Calcule les embeddings Mistral (`mistral-embed`) uniquement pour les fiches `validated`, et les
sauvegarde dans `data/index.json`.

## Étape 6 — Tester l'Agent 2 sur une maison

```bash
venv/bin/python agent2_rag.py --input maison_exemple.json --output data/resultat.json
```

Remplace `maison_exemple.json` par le vrai JSON produit par l'agent de ton collègue (analyse de
risque) dès qu'il est disponible — le format attendu est décrit dans `maison_exemple.json`.

Le résultat dans `data/resultat.json` contient, pour chaque zone de la maison, les risques et les
recommandations sourcées — c'est ce JSON que ton collègue 3 (jumeau numérique 3D) consommera.

## Étape 7 — Itérer

- Si une zone/risque ne retourne aucune recommandation, c'est probablement que le référentiel ne
  contient pas encore de fiche sur ce sujet précis → ajoute la source correspondante et relance
  les étapes 3 bis à 6.
- Si tu ajoutes de nouveaux documents, relance `populate_registry.py`, puis `agent1_extract.py`
  (il régénère tout le référentiel) et `build_index.py`.
- `config.py` centralise les réglages (modèle utilisé, taille des chunks, top_k de recherche) si
  tu veux ajuster.

## Résumé du pipeline

```
documents/*.*  --populate_registry.py-->  data/sources_registry.csv
     |
     v
     --agent1_extract.py-->  data/referentiel.json  --build_index.py-->  data/index.json
                                                                                 |
maison_exemple.json -----------------------------> agent2_rag.py ---------------+--> data/resultat.json
```
