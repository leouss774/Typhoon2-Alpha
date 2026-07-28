# Agent de valorisation, décision de crédit et suivi immobilier

Implémentation Python (stdlib uniquement, aucune dépendance externe) du
pipeline discuté : à partir des sorties de votre **agent de risque** et de
votre **agent de recommandation**, ce projet calcule une valorisation
ajustée au risque, projette la valeur du bien sur la durée du prêt (avec et
sans travaux), calcule le LTV glissant, produit une décision de crédit
argumentée, et un plan de suivi périodique.

## Structure

```
credit_immo_agent/
├── agents/
│   ├── valuation_agent.py       # pondération du risque + décote de valeur
│   ├── projection_agent.py      # projection de la valeur dans le temps
│   ├── credit_decision_agent.py # amortissement, LTV glissant, décision
│   └── monitoring_agent.py      # plan de suivi périodique
├── data/
│   ├── exemple_risque.json          # exemple de sortie de votre agent de risque
│   ├── exemple_recommandations.json # exemple de sortie de votre agent de recommandation
│   └── exemple_dossier.json         # données du dossier de crédit (à fournir)
├── orchestrator.py               # relie tous les agents, point d'entrée CLI
└── README.md
```

## Utilisation

Aucune dépendance à installer (Python 3.8+, bibliothèque standard uniquement).

```bash
python orchestrator.py \
  --risque data/exemple_risque.json \
  --recommandations data/exemple_recommandations.json \
  --dossier data/exemple_dossier.json
```

Pour écrire le résultat dans un fichier plutôt que sur stdout :

```bash
python orchestrator.py --sortie resultat.json
```

### Utiliser vos propres données

Remplacez les trois fichiers JSON par les sorties réelles de vos agents. Le
format attendu est documenté dans chaque fichier d'exemple et dans le prompt
système fourni séparément (`prompt_agent_credit_immobilier.md`).

Champs **obligatoires** dans le dossier de crédit — l'orchestrateur refuse de
produire un résultat s'ils manquent :
- `valeur_marche_bien`
- `montant_emprunte`
- `duree_annees`

Champs optionnels avec valeur par défaut documentée dans la sortie
(`hypotheses`) si absents :
- `taux_annuel_propose` (défaut : 3,4 %)
- `tendance_marche_annuelle` (défaut : 0 %)

## Hypothèses et paramètres à ajuster

Tous les paramètres suivants sont des **valeurs par défaut de démonstration**,
pas des paramètres validés par une politique de risque bancaire réelle. Ils
sont centralisés pour être facilement modifiables :

| Paramètre | Emplacement | Valeur par défaut |
|---|---|---|
| Pondération des zones de risque | `agents/valuation_agent.py::POIDS_ZONES` | fondations 30 %, toiture 20 %, sous-sol 15 %, murs 35 % réparti |
| Facteur de sévérité (score → décote) | `agents/valuation_agent.py::FACTEUR_SEVERITE` | 0.5 |
| Seuils de décision LTV | `agents/credit_decision_agent.py` | 80 % (accord), 100 % (refus) |
| Seuil de prime de risque | `agents/credit_decision_agent.py::SEUIL_SCORE_PRIME_RISQUE` | 60 |
| Mapping aléa → zone (pour le scénario "avec travaux") | `agents/projection_agent.py::appliquer_travaux` | simplifié, à affiner |
| Seuils du plan de suivi | `agents/monitoring_agent.py::PlanDeSuivi` | alerte 90 %, réexpertise 100 % |

**Le mapping aléa → zone est une simplification** : il associe chaque aléa
(rga, inondation, tempête, incendie) à une seule zone principale pour
illustrer le mécanisme. Si votre agent de risque fournit une correspondance
plus fine aléa/zone, remplacez ce mapping en conséquence.

## Connecteurs réels (agent de suivi)

Le dossier `connectors/` contient deux connecteurs qui appellent de vraies API
publiques françaises, aucune dépendance externe (juste `urllib` de la stdlib) :

- **`connectors/dvf_connector.py`** — interroge `http://api.cquest.org/dvf`
  (API communautaire Etalab/DGFiP) pour obtenir le prix médian au m² actuel
  autour d'un point, et le comparer à un prix de référence.
- **`connectors/georisques_connector.py`** — interroge l'API officielle
  `https://georisques.gouv.fr/api/v1` pour l'exposition RGA et les arrêtés
  de catastrophe naturelle (CatNat), et détecte toute dégradation par
  rapport à une situation de référence.

`agents/monitoring_agent.py::executer_cycle_suivi_reel()` orchestre les deux
et recalcule le LTV actualisé. **Aucune donnée n'est jamais devinée en cas de
panne d'API** : si une source est indisponible, le champ correspondant est
marqué `"statut": "indisponible"` avec le message d'erreur, jamais une valeur
supposée.

### ⚠️ Ces connecteurs n'ont pas pu être testés en conditions réelles ici

Mon environnement d'exécution ne peut atteindre que quelques domaines
whitelistés (PyPI, npm, GitHub...) — ni `georisques.gouv.fr` ni
`api.cquest.org` n'en font partie. J'ai donc :
1. Vérifié les endpoints par recherche (documentation officielle Géorisques,
   dépôt GitHub `cquest/dvf_as_api`, retours d'utilisateurs sur le forum
   data.gouv.fr) — ils sont corrects à la date de rédaction.
2. Testé toute la **logique** avec des réponses simulées (voir
   `tests/test_monitoring_reel.py`, qui passe).
3. Tenté un vrai appel depuis ce bac à sable : il échoue avec une erreur 403
   qui vient de mon proxy réseau, pas de Géorisques — la preuve que la
   limite est ici, pas dans le code.

**Avant tout usage réel : lancez `connectors/dvf_connector.py` et
`connectors/georisques_connector.py` depuis votre propre machine/serveur**
pour confirmer que les endpoints répondent toujours comme documenté (ces
API communautaires ou publiques évoluent sans préavis contractuel).

## Limites connues (à corriger avant tout usage réel)

- La projection du risque suppose une évolution **linéaire homothétique** de
  toutes les zones vers le score global 2050 fourni ; une projection par
  zone serait plus fidèle si votre agent de risque la fournit.
- L'API DVF communautaire (`api.cquest.org`) n'a **aucun SLA garanti** — pour
  un usage bancaire réel, envisagez d'héberger votre propre instance à partir
  des fichiers bruts DVF (data.gouv.fr).
- Géorisques applique un anti-robot qui a bloqué des clients non-navigateur
  par le passé — contactez l'équipe Géorisques via data.gouv.fr pour un accès
  automatisé stable si vous industrialisez ce connecteur.
- Le facteur de sévérité de 50 % est délibérément visible et isolé pour
  pouvoir être challengé et recalibré avec des données réelles de
  sinistralité, pas pris comme une vérité métier.
- Aucune persistance (base de données) n'est incluse : chaque exécution est
  stateless. Pour un vrai suivi dans le temps, il faut stocker les résultats
  (par exemple en PostGIS + une table de suivi par dossier) et appeler
  `executer_cycle_suivi_reel()` périodiquement (cron/Airflow) plutôt qu'à la demande.

## Prochaines étapes suggérées

1. Remplacer les JSON d'exemple par vos vraies sorties d'agents et valider
   que le format correspond.
2. Faire challenger `FACTEUR_SEVERITE` et `POIDS_ZONES` par un expert risque.
3. Ajouter les connecteurs réels (Géorisques, DVF) dans `monitoring_agent.py`.
4. Ajouter une couche de persistance pour suivre un dossier dans la durée.
5. Faire valider le format de sortie par votre juriste/compliance (RGPD art. 22).
