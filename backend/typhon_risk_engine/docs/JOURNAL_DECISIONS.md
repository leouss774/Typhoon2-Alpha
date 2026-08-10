# Journal des décisions et hypothèses provisoires

Version règles 1.0.0 · 28 juillet 2026

## A. Décisions tranchées et implémentées

| # | Décision | Où c'est implémenté | Statut |
|---|---|---|---|
| D01 | Courbes monétaires, rôles EXPO et variables de valorisation exclus | aucune règle ne les référence ; test `test_no_global_score_and_no_money` | **ferme** |
| D02 | `alea_argile` publiée consommée directement, sans réappliquer BRGM | `rules/P02.yaml` ; test `test_clay_class_not_double_counted_with_brgm_method` | **ferme** |
| D03 | CatNat et booléens communaux : poids nul dans `F` | `normalizer._commune_context`, `_catnat_context` ; test dédié | **ferme** |
| D04 | Valeurs par défaut exclues | `CanonicalVariable.__post_init__` force `DEFAULT_VALUE` | **ferme** |
| D05 | Projections prospectives jamais dans `F`, `V`, `R` | `CURRENT_HORIZONS` ; `usable` refuse `PROSPECTIVE` | **ferme** |
| D06 | P06, P07, P10 publient `V` seul, avec libellé obligatoire | `hazard_available: false` ; test dédié | **ferme** |
| D07 | P07 activable automatiquement dès qu'un lookup neige versionné existe | `rules/P07.yaml → hazard_activation_interface` | **prêt** |
| D08 | P10 sans Météorage, aucun proxy | `rules/P10.yaml` | **ferme** |
| D09 | P06 sans climatologie grêle validée | `rules/P06.yaml` | **ferme** |
| D10 | P04 décomposé en 4 sous-périls indépendants, jamais agrégés | `P04-CAV`, `P04-GLI`, `P04-BLO`, `P04-TAS` ; test dédié | **ferme** |
| D11 | μD de RISK-UE non implémentée ; table utilisée en classement ordinal seul | `rules/P03.yaml`, notes de `wall_material` | **ferme** |
| D12 | `R = 100 × (F/100)^0,5 × (V/100)^0,5`, exposants en YAML | `rules/_common.yaml → combination` | **provisoire** |
| D13 | `Vmin = 10` | `_common.yaml` | **provisoire** |
| D14 | Réduction par protections plafonnée à 50 % | `_common.yaml → protection_cap` | **provisoire** |
| D15 | Protections agissent uniquement sur `V` | rôle `protection` dans le bloc vulnérabilité seul | **ferme** |
| D16 | `INDÉTERMINÉ` si dominante absente **ou** > 50 % du poids manquant | `engine._score_block` | **ferme** |
| D17 | Renormalisation seulement si dominante présente et seuil respecté | idem | **ferme** |
| D18 | Confiance indépendante du risque | `confidence.py` ; `independent_of_risk: true` | **ferme** |
| D19 | Aucun score global multi-périls | `global_score: null` | **ferme** |
| D20 | Calcul entièrement déterministe, aucun LLM | test de reproductibilité bit à bit | **ferme** |

## B. Décisions prises en cours d'implémentation

| # | Décision | Motif |
|---|---|---|
| D21 | `results = 0` sur cavités **n'active pas** `accept_no_feature` | sans rayon ni couverture journalisés, un zéro est ininterprétable. Publier un aléa nul serait une invention |
| D22 | P04 décomposé en identifiants `P04-XXX` plutôt qu'en un péril à quatre blocs | garantit structurellement l'impossibilité d'une agrégation accidentelle |
| D23 | Classification de risque sur l'**entier arrondi**, pas le flottant brut | bug réel : les bandes entières contiguës laissaient un trou entre 79 et 80. Levée d'exception si un score sort de toutes les bandes |
| D24 | `site.drainage_defect` (P02) et `site.overhanging_trees` (P05) déclarés en `protection` avec `max_reduction: 0` | ce sont des facteurs **aggravants**. Une protection ne peut que réduire `V`. Les faire peser exigerait une source cas-témoin absente du corpus. Conservés pour traçabilité et affichage |
| D25 | Un `F` indéterminé dont les variables manquantes sont **répondables** produit `NEEDS_USER_INPUT`, pas `INDETERMINATE` | distingue le blocage technique du blocage levable par l'habitant. Concerne P08 et P11 |
| D26 | Priorité BDNB : `materiaux_structure_mur_exterieur` > `mat_mur_txt` quand ce dernier vaut `INDETERMINE` | un champ générique de remplissage ne doit pas écraser une description structurelle précise |
| D27 | Chauffage et ECS restent deux variables distinctes | PAC électrique en chauffage + chaudière gaz en ECS n'est pas une contradiction : deux sources d'ignition à évaluer séparément |
| D28 | Champs nominatifs (`l_denomination_proprietaire`, `l_siren`, `numero_immat_principal`, `identifiant_dpe`) supprimés du schéma normalisé | aucun rapport physique avec le risque ; testé sur la fixture et sur la sortie |
| D29 | Typologie maison / collectif dérivée et exposée en avertissement, **sans** `NOT_APPLICABLE` sur P02 | le corpus de vulnérabilité est calibré maison individuelle. Signaler l'écart plutôt que refuser le calcul, l'aléa restant valide |
| D30 | Les fixtures de test construites portent `_synthetic: true` | aucune confusion possible avec des données réelles |

## C. Hypothèses provisoires assumées — à recalibrer

| Hypothèse | Valeur | Ce qui manque pour la fixer |
|---|---|---|
| Exposants de combinaison | 0,5 / 0,5 | données de sinistres |
| `Vmin` | 10 | justification empirique du plancher |
| Plafond de protection | 50 % | taux de réduction observés par équipement |
| Seuil de publication | 50 % du poids | convention |
| Bandes de classe de risque | 0-19 / 20-39 / 40-59 / 60-79 / 80-100 | convention de lecture interne, ni officielle ni actuarielle |
| Rampe jours secs P02 | 10 → 40 jours | **aucune étude du corpus ne publie ce seuil** |
| Indices de typologie sismique | classement ordinal dérivé de RISK-UE | conversion accélération → EMS-98 |
| Paliers d'année de construction P03 | 1969 / 1992 / 2011 | les **dates** sont réglementaires et publiées ; les **valeurs d'indice** sont provisoires |
| Tous les poids de P08 et P11 | — | base de sinistres segmentée. Ce sont les deux périls les plus sensibles à la perturbation |

## D. Ce qui reste ouvert

1. **Calibration** : aucun péril n'est calibré. Priorité absolue : un extrait de sinistres assureur anonymisé et segmenté.
2. **Effets de site sismiques** : classe de sol EC8 absente.
3. **Corpus maison individuelle** : aucun corpus de vulnérabilité collectif identifié.
4. **P06 et P10** : bloqués par indisponibilité de données, pas par la méthode.
5. **Rayon et couverture des requêtes ponctuelles Géorisques** : non journalisés, ce qui stérilise P04-CAV.
6. **Frontières de bande** : un score de 59,6 contre 60,2 change la classe affichée. Envisager d'afficher le score brut à côté de la classe, ou une zone de recouvrement.
