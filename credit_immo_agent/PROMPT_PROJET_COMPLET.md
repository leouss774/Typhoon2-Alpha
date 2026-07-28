# Prompt complet — Projet credit_agent (backend Python + workflow n8n vérifié)

## Contexte

Ce prompt décrit l'état réel du projet à ce stade, pour qu'un développeur ou
un agent de code (Claude Code, etc.) puisse reprendre le travail sans
reperdre le contexte de cette conversation. Il couvre trois éléments qui
doivent rester cohérents entre eux :

1. **Les agents backend déjà développés** (`collector_agent` implémenté,
   `scoring_agent`/`rag_agent` à implémenter, `digital_twin_agent`
   partiellement implémenté).
2. **Le workflow n8n `credit_agent`** déjà construit et exporté
   (`n8n/credit_agent_workflow.json`), qui joue le rôle du 5ème agent
   (décision de crédit) directement dans n8n plutôt qu'en Python.
3. **Le vérificateur automatique** (`verify_n8n_workflow.py`) qui valide la
   structure du workflow n8n avant toute mise en production.

## État actuel du pipeline

```
backend/app/agents/collector_agent.py   → building_data          [IMPLÉMENTÉ]
backend/app/agents/scoring_agent.py     → risk_scores             [À FAIRE]
backend/app/agents/rag_agent.py         → recommendations         [À FAIRE]
backend/app/digital_twin/geometry_builder.py → digital_twin (partiel) [PARTIEL]
                                                    ↓
n8n/credit_agent_workflow.json (déjà construit et vérifié)
  Interface Crédit (formTrigger)
       → credit_agent (agent LangChain, Mistral Large, temp 0.1)
            outils : geocode_adresse (api-adresse.data.gouv.fr — officiel, fiable)
                     dvf_comparables (api.cquest.org/dvf — communautaire, PAS de SLA)
       → Rapport de crédit (form, sortie HTML complète avec graphiques QuickChart)
```

**Point d'intégration actuellement manquant** : le workflow n8n ne fait
**pas encore d'appel automatique** vers `collector_agent`, `scoring_agent`
ou `rag_agent`. L'utilisateur doit aujourd'hui **copier-coller manuellement**
les JSON `building_data`, `risk_scores`, `recommendations`, `digital_twin`
dans les champs texte du formulaire. C'est fonctionnel mais pas automatisé
de bout en bout.

## Ce que le projet doit faire (instructions pour la suite)

### 1. Finir les agents backend manquants

- `scoring_agent.py` doit produire un JSON conforme au schéma déjà validé :
  ```json
  {
    "score_global": 52,
    "zones": {
      "fondations": { "risque": 55, "niveau": "modere", "alea_principal": "...", "justification": "..." },
      "murs_nord": { "...": "..." }, "murs_sud": {}, "murs_est": {}, "murs_ouest": {},
      "toiture": {}, "sous_sol": {}
    },
    "projection_2050": { "score_global": 63, "zones": { "fondations": { "risque": 68, "niveau": "eleve" }, "...": "..." } }
  }
  ```
  Il doit dériver ces scores à partir de `building_data.georisques`,
  `building_data.climat_open_meteo` et `building_data.climat_copernicus`
  produits par `collector_agent` — ne pas dupliquer de logique de collecte.

- `rag_agent.py` doit produire :
  ```json
  {
    "fondations": [ { "travaux": "...", "cout_estime": "8000-16000€", "gain_resilience": 30 } ],
    "murs_nord": [], "murs_sud": [], "murs_est": [], "murs_ouest": [], "toiture": [], "sous_sol": []
  }
  ```
  via RAG sur la base documentaire (MRN, BRGM, CEPRI). Chaque zone peut avoir
  **plusieurs** travaux — le `credit_agent` (n8n) sait déjà composer
  plusieurs `gain_resilience` de façon multiplicative, pas additive.

### 2. Automatiser l'appel aux agents depuis n8n (au lieu du copier-coller)

Remplacer les 4 champs texte JSON du formulaire `Interface Crédit` par un
appel HTTP automatique :

```
Interface Crédit (adresse + montant + durée + taux)
     ↓
[Nœud HTTP Request] → POST vers l'endpoint FastAPI de collector_agent
     ↓ building_data
[Nœud HTTP Request] → POST vers l'endpoint FastAPI de scoring_agent (avec building_data)
     ↓ risk_scores
[Nœud HTTP Request] → POST vers l'endpoint FastAPI de rag_agent (avec risk_scores)
     ↓ recommendations
     ↓ (les trois JSON sont fusionnés dans le payload envoyé à credit_agent)
credit_agent (inchangé)
     ↓
Rapport de crédit (inchangé)
```

Cela suppose que `collector_agent`, `scoring_agent`, `rag_agent` soient
exposés en HTTP (FastAPI) — si ce n'est pas encore le cas, l'ajouter avant
de modifier le workflow n8n. Ne pas dupliquer cette logique de collecte
côté n8n (pas de nouvel appel direct à Géorisques/DVF depuis n8n en dehors
de `dvf_comparables`, qui sert de repli uniquement si `building_data` est
absent).

### 3. Toujours faire tourner le vérificateur avant toute modification du workflow n8n

```bash
python verify_n8n_workflow.py n8n/credit_agent_workflow.json
```

Ce script contrôle, sans jamais exécuter le workflow réellement :
- présence des nœuds obligatoires (formulaire d'entrée, agent, modèle,
  au moins un outil, formulaire de sortie)
- que `montant_emprunte` et `duree_annees` sont bien marqués obligatoires
  dans le formulaire
- que le `systemMessage` de l'agent contient les contraintes clés (aide à la
  décision, RGPD, composition multiplicative des `gain_resilience`, etc.)
- que les nœuds sont bien connectés entre eux (formulaire → agent → sortie,
  modèle et outils bien rattachés à l'agent)
- signale les URLs d'outils connues comme non garanties (ex. `api.cquest.org`)

Avec `--ping-urls`, il teste aussi la joignabilité réseau réelle des URLs —
**à lancer depuis votre propre machine**, pas depuis un environnement
sandboxé qui pourrait bloquer ces domaines par défaut.

**Toute modification du workflow n8n doit être suivie d'un nouveau passage
du vérificateur avant d'être considérée comme prête.** Si le vérificateur
retourne au moins une erreur (pas juste un avertissement), le workflow ne
doit pas être activé en production.

### 4. Point de vigilance déjà identifié : `dvf_comparables`

Le vérificateur signale (avertissement, pas erreur) que l'outil
`dvf_comparables` pointe vers `api.cquest.org/dvf`, une API communautaire
sans garantie de disponibilité — confirmé par un nœud en erreur observé
directement dans une exécution réelle du workflow. Deux options, à trancher
avant mise en production réelle (pas bloquant pour un POC) :
- Ajouter un `retryOnFail`/`continueOnFail` sur ce nœud dans n8n pour que
  l'agent puisse continuer même si `dvf_comparables` échoue (il basculera
  sur une confiance faible ou demandera la valeur, conformément au
  systemMessage déjà écrit).
- Héberger sa propre instance de l'API DVF à partir des données brutes
  data.gouv.fr, pour ne plus dépendre de la disponibilité d'un tiers.

## Contraintes non négociables (rappel, déjà encodées dans le systemMessage n8n)

- Jamais de donnée inventée : `montant_emprunte`/`duree_annees` obligatoires,
  `valeur_marche_bien` estimée via DVF uniquement si possible, sinon demandée.
- Chaque décision doit être explicable avec les chiffres exacts qui l'ont
  déclenchée.
- Toujours rappeler qu'il s'agit d'une aide à la décision, jamais un
  engagement de crédit (article 22 du RGPD sur les décisions automatisées).
- Composition **multiplicative**, jamais additive, des `gain_resilience`
  d'une même zone.
- Séparer clairement scénario "avec travaux" et "sans travaux", jamais
  fusionnés silencieusement.

## Fichiers du projet à ce stade

```
credit_immo_agent/
├── agents/                          # implémentation Python de référence
│   ├── valuation_agent.py
│   ├── projection_agent.py
│   ├── credit_decision_agent.py
│   └── monitoring_agent.py
├── connectors/                      # connecteurs réels (DVF, Géorisques)
│   ├── dvf_connector.py
│   └── georisques_connector.py
├── n8n/
│   └── credit_agent_workflow.json   # le workflow n8n réel fourni
├── verify_n8n_workflow.py           # vérificateur automatique du workflow
├── data/                            # exemples de JSON par agent
├── tests/                           # tests unitaires (pipeline + vérificateur)
├── orchestrator.py                  # équivalent Python du workflow n8n
├── prompt_agent_credit_immobilier.md
├── prompt_credit_agent_projet_complet.md
└── README.md
```

Note importante : **il existe maintenant deux implémentations parallèles**
de la même logique de décision — le `orchestrator.py` Python et l'agent
`credit_agent` dans n8n (piloté par LLM). Elles doivent rester alignées sur
les mêmes formules et seuils (poids des zones, facteur de sévérité 0.5,
seuils LTV 80%/100%) si les deux sont utilisées en parallèle — sinon elles
donneront des décisions différentes pour le même dossier, ce qui serait un
problème de gouvernance de modèle en soi.

## Prochaine étape concrète recommandée

1. Lancer `python verify_n8n_workflow.py n8n/credit_agent_workflow.json`
   pour confirmer l'état actuel (0 erreur, 1 avertissement connu).
2. Implémenter `scoring_agent.py` et `rag_agent.py` selon les schémas
   ci-dessus.
3. Exposer les 3 agents amont en HTTP (FastAPI) s'ils ne le sont pas déjà.
4. Modifier `n8n/credit_agent_workflow.json` pour appeler ces endpoints
   automatiquement au lieu du copier-coller manuel.
5. Relancer le vérificateur après chaque modification du workflow.
