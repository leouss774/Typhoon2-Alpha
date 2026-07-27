# Module Recommandations — Vulnérabilité climatique des maisons individuelles

## 1. Rôle du module dans le système multi-agent

```
[Agent Analyse de risque]           [Agent Recommandations]              [Agent Jumeau numérique 3D]
   géocodage + APIs        --->      référentiel + RAG        --->        rendu par zone de la maison
(Copernicus, Géorisques,             (ce module)                          (risques + travaux par pièce)
 DRIAS, BDNB...)
        |
        v
  JSON maison
  (adresse, matériaux, coordonnées BDNB,
   risques, zones/parties touchées)
```

Ce module reçoit le JSON produit par l'agent d'analyse de risque et retourne un JSON enrichi de
recommandations, sourcées et tracées, exploitable par l'agent 3D.

## 2. Principe général

Le module est construit en **deux temps distincts**, volontairement séparés :

1. **Phase de curation (Agent 1, ponctuel)** : transformer des documents hétérogènes (PDF, pages
   web, guides techniques) en un référentiel structuré, sourcé, validé par un humain.
2. **Phase d'exploitation (Agent 2, en production)** : un agent RAG qui interroge uniquement ce
   référentiel validé pour répondre aux requêtes du système (JSON maison en entrée).

L'Agent 1 ne tourne pas en continu. Il sert à construire la base de connaissance une fois (puis à
chaque mise à jour des sources). Seul l'Agent 2 est appelé en production par le reste du système.

**Pourquoi cette séparation ?** Faire du RAG directement sur les PDF bruts est risqué sur ce sujet :
coûts, taux d'aide, obligations réglementaires sont des données sensibles où une hallucination est
inacceptable. En passant par une étape de curation stricte, contrôlée et relue, on s'assure que la
base indexée ne contient que des faits tracés jusqu'à leur source — l'agent final ne peut pas
"inventer" un chiffre puisqu'il ne peut piocher que dans des fiches déjà validées.

## 3. Registre des sources

Avant toute extraction, chaque source est enregistrée dans le fichier
`data/sources_registry.csv`. Ce registre peut être rempli de deux façons :

- **Automatiquement** avec `populate_registry.py` (voir Guide de démarrage §3 bis) :
  le script analyse le début de chaque document avec Mistral pour suggérer
  l'organisme, le lien et la catégorie de chaque source.
- **Manuellement** en éditant directement le CSV.

Le registre suit cette structure :

| ID | Organisme / éditeur | Lien ou document | Catégorie supposée | Fiabilité | Usage prévu |
|----|---------------------|-------------------|---------------------|-----------|-------------|
| S01 | FFB | ffbatiment.fr — NF DTU / normes | Réglementaire / technique | Officiel (fédération professionnelle) | Règles techniques |
| S02 | Thivillier SARL | Techniques renforcement bâti existant | Technique (commercial) | Piste seulement | Idées de mesures à vérifier ailleurs |
| S03 | Numbr | Normes BTP | Généraliste (commercial) | Piste seulement | Contexte |
| S04 | ADEME | librairie.ademe.fr | Officiel / technique | Officiel | Guides, rénovation, matériaux |
| S05 | CSTB | cstb.fr | Scientifique/technique | Officiel | DTU, avis techniques |
| S06 | BRGM | brgm.fr | Scientifique | Officiel | RGA, sols, risques géologiques |
| S07 | FFB | Bilan 2024 / prévisions 2025 | Conjoncture | Officiel (fédération) | Contexte coûts filière |
| S08 | Batiprix | Logiciel de chiffrage | Commercial | Piste seulement | Ordres de grandeur coûts, jamais seul suffisant |
| S09 | LaPrimeEnergie.fr | Programme Habiter Mieux | **Commercial (intermédiaire)** | Piste seulement — **à remplacer par france-renov.gouv.fr / anah.fr** | Aides |
| S10-S11 | (2 PDF locaux) | Travaux construction existante ; Guide entretien bâtiments durables (ADEME 2023) | Technique | À vérifier | Règles techniques, entretien |

**Sources à ajouter (voir recommandations ci-dessus dans la conversation)** : georisques.gouv.fr
(PPR téléchargeables), ERRIAL, DDRM départementaux, PLU/PLUi, argiles.fr, planseisme.fr, Légifrance
(Code de la construction et de l'habitation), france-renov.gouv.fr / anah.fr, Météo France.

Les catégories disponibles sont : `reglementaire_technique`, `officiel_technique`,
`officiel`, `scientifique`, `scientifique_technique`, `technique`, `commercial`,
`piste_commerciale_uniquement`, `non_classee`.

Chaque source obtient un statut de fiabilité : `officiel`, `scientifique_technique`,
`piste_commerciale_uniquement`. Ce statut conditionne ce que l'Agent 1 a le droit d'en extraire
(voir §5, règle sur les sources commerciales).

## 4. Schéma du référentiel (sortie de l'Agent 1)

Chaque ligne du référentiel est une **fiche de règle**, au format JSON, avec les champs suivants :

```json
{
  "id": "REF-0001",
  "type": "recommandation_source | obligation_locale | regle_consolidee | estimation_cout | info_aide | info_insuffisante",
  "alea": "retrait_gonflement_argiles",
  "territoire": {"echelle": "national | departemental | communal", "code": null},
  "zone_maison": "fondations",
  "conditions_application": "maison sur fondations superficielles, sol argileux zone moyenne/forte",
  "mesure": "description de la mesure de prévention/protection/diagnostic",
  "limites_prerequis": "texte",
  "cout": {
    "montant_min": null, "montant_max": null, "devise": null, "unite": null,
    "date_estimation": null, "zone_geo": null, "hypotheses": null
  },
  "aide": {
    "dispositif": null, "conditions": null, "statut": "potential_eligibility_only"
  },
  "sources": [
    {"source_id": "S06", "titre": "...", "organisme": "BRGM", "date_ou_version": "...",
     "section_page": "...", "extrait_exact": "citation courte exacte"}
  ],
  "statut_validation": "draft | validated | rejected | contradictory",
  "extraction": {"agent": "agent1_extracteur", "prompt_version": "v1.0", "date": "AAAA-MM-JJ"}
}
```

Points clés :
- Un fait sans source explicite ne peut porter que le type `info_insuffisante`.
- Un coût ou un taux d'aide sans les métadonnées complètes (devise, date, zone, hypothèses) est
  rejeté ou requalifié en `info_insuffisante`.
- `statut_validation` est obligatoire. **Seules les fiches `validated` sont indexées** dans la base
  RAG utilisée en production (§6).

## 5. Agent 1 — Extracteur / constructeur du référentiel

Rôle : lire les documents, extraire les faits, produire des fiches conformes au schéma ci-dessus.
Il ne prend aucune décision technique, réglementaire ou financière — il documente ce que disent les
sources, avec traçabilité complète.

Règles imposées (résumé, prompt complet conservé en annexe versionnée) :
- Aucune connaissance externe aux documents fournis, aucune invention.
- Citation courte exacte obligatoire pour chaque fait retenu.
- Distinction stricte entre fait documenté, recommandation de source, obligation locale, règle
  consolidée, estimation de coût, info sur aide, info insuffisante.
- Une obligation n'est retenue que si une source officielle et applicable le dit explicitement (avec
  territoire et conditions).
- Coûts et pourcentages jamais produits sans source explicite, datée, applicable, détaillée.
- Une source commerciale seule ne suffit jamais à établir une règle, un coût ou une éligibilité —
  elle reste une piste à confirmer par une source officielle/technique.
- Contradictions entre sources signalées explicitement (`statut_validation: contradictory`), jamais
  arbitrées seules par l'agent.

Sortie : lot de fiches `draft`, à relire manuellement.

## 6. Validation humaine et indexation

Étape non automatisée, indispensable : un relecteur passe chaque fiche `draft` en `validated` ou
`rejected` (ou `contradictory` si un arbitrage externe est nécessaire). C'est un vrai *gate* du
pipeline, pas une formalité.

Seules les fiches `validated` sont ensuite indexées (embeddings + métadonnées filtrable : `alea`,
`zone_maison`, `territoire`, `type`) dans la base vectorielle utilisée par l'Agent 2.

Le prompt et les logs de l'Agent 1 sont conservés (versionnés) même si l'agent n'est plus exécuté en
production — nécessaire pour retracer l'origine de chaque fiche en cas de révision.

## 7. Agent 2 — Agent RAG final (production)

Entrée : le JSON produit par l'agent d'analyse de risque (adresse, infos bien, risques, zones
touchées).

Fonctionnement :
1. Pour chaque risque/zone du JSON d'entrée, filtrer le référentiel validé par `alea`, `zone_maison`
   et `territoire` correspondants (matching sur une taxonomie commune partagée avec l'agent
   d'analyse — à formaliser pour éviter tout décalage de vocabulaire).
2. Récupération des fiches pertinentes (RAG), génération de la recommandation en ne s'appuyant que
   sur le contenu récupéré (pas de connaissance externe).
3. Report des mêmes distinctions de statut que dans le référentiel (recommandation vs obligation vs
   estimation de coût vs indication d'aide `potential_eligibility_only`).

Sortie : JSON enrichi, avec pour chaque zone de la maison les risques associés et les
recommandations sourcées — structure directement exploitable par l'agent 3D (parcours de la maison
zone par zone, affichage risque + travaux + source).

```json
{
  "adresse": "...",
  "bien": { "...": "repris du JSON d'entrée" },
  "zones": [
    {
      "zone": "toiture",
      "risques": ["tempete", "grele"],
      "recommandations": [
        {
          "mesure": "...",
          "type": "recommandation_source | obligation_locale | regle_consolidee",
          "cout_estime": {"...": "ou null si insuffisant"},
          "aide": {"...": "ou null"},
          "sources": [{"source_id": "S05", "titre": "...", "extrait_exact": "..."}]
        }
      ]
    }
  ]
}
```

## 8. Points de vigilance

- Alignement du vocabulaire risques/zones avec le JSON du collègue 1 (agent d'analyse) : à
  formaliser en taxonomie partagée avant de coder les filtres du RAG.
- Ne pas confondre "piste commerciale" et "source validante" : toute fiche issue uniquement d'une
  source commerciale doit rester `info_insuffisante` tant qu'aucune source officielle ne la
  confirme.
- Mise à jour du référentiel : prévoir une procédure de ré-extraction quand une source officielle
  est mise à jour (ex. arrêté RGA de janvier 2026, PPR révisés).
- Les PPR à ajouter (georisques.gouv.fr) sont la source la plus directement actionnable pour les
  obligations locales — prioritaires pour la prochaine itération d'extraction.

## 9. Outils utilitaires

### `populate_registry.py`

Peuple automatiquement `data/sources_registry.csv` en analysant chaque document avec
Mistral. Utilise `chat_json()` pour suggérer l'organisme, le lien et la catégorie de chaque
source. Options :

- `--dry-run` : affiche ce qui serait ajouté sans modifier le CSV
- `--overwrite` : réanalyse même les fichiers déjà présents (remplace les anciennes entrées)

### `utils/load_registry()` (dans `utils/__init__.py`)

Fonction partagée qui charge `sources_registry.csv` et retourne un dictionnaire
`{fichier: row}`. Utilisée à la fois par `agent1_extract.py` et `populate_registry.py`.

### Fichiers générés (ignorés par git)

| Fichier | Généré par | Description |
|---------|------------|-------------|
| `data/referentiel.json` | `agent1_extract.py` | Fiches extraites des documents |
| `data/index.json` | `build_index.py` | Index vectoriel (embeddings) |
| `data/resultat.json` | `agent2_rag.py` | Résultat final de recommandations |

## 10. Prochaines étapes

1. Compléter le registre des sources (PPR, DDRM, PLU, argiles.fr, planseisme.fr, Légifrance,
   france-renov.gouv.fr/anah.fr) — utiliser `populate_registry.py` pour ça.
2. Formaliser la taxonomie commune risques/zones avec l'agent d'analyse.
3. Faire tourner l'Agent 1 sur le lot de sources validé, relecture humaine des fiches `draft`.
4. Indexer les fiches `validated` dans la base vectorielle.
5. Développer l'Agent 2 (RAG) et valider son JSON de sortie avec le collègue en charge du jumeau
   numérique 3D.
