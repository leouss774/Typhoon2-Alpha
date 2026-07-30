# Phase 1.1 — Audit corrigé du Risk Engine Typhon

**Version** 1.1 · **Date** 28 juillet 2026 · **Run de référence** 73 avenue Simone Veil, 06200 Nice (INSEE 06088)

Ce document **corrige** `PHASE1_AUDIT_RISK_ENGINE_TYPHON.md` à la lumière du JSON réellement produit par le collector. Il ne le remplace pas : la méthode, les seuils publiés et l'analyse par péril de la Phase 1 restent valides. Ce qui change, c'est le verdict de **disponibilité**.

> **Note liminaire sur l'environnement.** Le code du collector n'est pas présent dans cet environnement de travail : seuls le référentiel, le data dictionary, les documents de Phase 1 et le JSON réel de Nice l'étaient. Les correctifs du collector sont donc livrés sous forme d'**adaptateurs testables sans réseau** (`risk_engine/collector_hardening.py`) accompagnés d'une liste d'actions à appliquer au dépôt du collector, et non sous forme de modifications directes de ce collector.

---

## 0. Le principe qui a changé le verdict

L'audit de Phase 1 s'appuyait sur le data dictionary. Le data dictionary décrit une **cible**, pas un état. Confronté au JSON réel, l'écart est massif dans les deux sens.

Ordre de vérité appliqué désormais :

1. le JSON réellement produit ;
2. les fixtures et tests qui prouvent qu'un champ est collecté ;
3. le data dictionary — **jamais** suffisant à lui seul.

Rapport de disponibilité automatique sur le run de Nice (`out/availability_report_nice.json`, 127 champs inventoriés) :

| Source | Couverture des promesses du data dictionary |
|---|---|
| BDNB | **100 %** |
| Géorisques | **100 %** |
| Open-Meteo (variables journalières) | **0 %** |
| Distances WFS (`distanceToWaterway`, `distanceToForest`, `distanceFireStation`) | **0 %** |

---

## 1. Disponible dans le JSON réel

Ces variables sont présentes, exploitables, et effectivement consommées par le moteur.

| Variable canonique | Chemin réel | Portée | Rang | Usage |
|---|---|---|---|---|
| `hazard.seismic.zone` | `georisques.zonage_sismique.data[0].code_zone` = `"4"` | commune | 3 | **Dominante F de P03** |
| `hazard.clay.exposure_class` | `bdnb.batiment.alea_argile` = `"Moyen"` | groupe de bâtiments | 1 | **Dominante F de P02** |
| `building.structure.wall_material` | `materiaux_structure_mur_exterieur` = `"murs en béton banché"` | groupe | 4 | Dominante V de P03 |
| `building.year_built` | `annee_construction` = 2017 | groupe | 4 | V de P03, F de P11 |
| `building.levels` / `building.height` | `nb_niveau` = 17 / `hauteur_mean` = 49 m | groupe | 4 | V de P03, typologie |
| `building.heating.generator` | `type_generateur_chauffage` = `"pac air/air"` | groupe | 4 | F de P08 |
| `building.dhw.generator` | `type_generateur_ecs` = `"chaudière gaz standard"` | groupe | 4 | F de P08 |
| `site.altitude` | `altitude_m` = 14,67 | parcelle | 1 | F de P14 (non dominante) |
| `meta.geocoding.score` | `adresse.score_geocodage` = 0,982 | logement | 1 | Confiance |
| `hazard.landslide.cavities_count` | `georisques.cavites.results` = 0 | voisinage | 2 | **`NO_FEATURE_FOUND`, non exploité** |

### Trois découvertes qui corrigent l'audit de Phase 1

**a) La séparation de P04 est possible.** L'audit concluait au caractère bloquant du code `12` « Mouvement de terrain ». C'était faux. `risques_detail[]` renvoie des **sous-codes** : `121` affaissements anthropiques, `123` chutes de blocs, `124` glissement, `127` tassements différentiels — et de même `113` crue torrentielle, `114` ruissellement, `117` submersion marine, `126` recul du trait de côte. P04 est donc décomposé en **quatre sous-périls indépendants** (`P04-CAV`, `P04-GLI`, `P04-BLO`, `P04-TAS`), jamais agrégés. Ces codes restent néanmoins du **contexte communal à poids nul** : ils indiquent la présence du phénomène sur la commune, ni son intensité, ni son atteinte au bâtiment.

**b) BDNB livre bien plus que le data dictionary ne l'annonçait**, notamment `alea_argile` à l'échelle du bâtiment, la structure des murs, et deux systèmes thermiques distincts.

**c) BDNB décrit un groupe, pas un logement.** L'adresse saisie est le n° 73, l'adresse principale BDNB est le n° 67, et le groupe contient **11 adresses** (67 à 87) partageant un `batiment_groupe_id`. Toutes les variables BDNB portent donc `scope = building_group`. Le moteur émet un `entity_match` de niveau `building_group` et le fait redescendre dans la confiance.

---

## 2. Prévu mais non opérationnel

Annoncé au data dictionary, **absent du JSON réel**. Traité en `NOT_COLLECTED` ou `SOURCE_ERROR` — jamais en absence de phénomène.

| Variable | Cause réelle | Conséquence sur le moteur |
|---|---|---|
| `temperature_2m_min` | non demandée dans le paramètre `daily` | **P11 bloqué** (jours de gel) |
| `wind_speed_10m_max` | non demandée | **P05 bloqué** |
| `relative_humidity_2m_mean` | non demandée | **P09 bloqué** (FWI incalculable) |
| `soil_moisture_0_to_10cm_mean` | non demandée | P02 affaibli, P09 bloqué |
| `distanceToWaterway` / `ToForest` / `FireStation` | module WFS non raccordé | **P01, P09, P14 bloqués** |
| `HAND`, `TWI`, pente numérique | non implémentés | **P01 et P04-GLI bloqués** |
| `zones_inondables` (AZI) | **HTTP 404** sur l'endpoint | **P01 `SOURCE_ERROR`** |
| Open-Meteo dans son ensemble | **HTTP 429** sur ce run | toutes variables climatiques en `SOURCE_ERROR` |
| CatNat, pages 2 à 9 | pagination non suivie | 4 enregistrements sur 83 — signalé, poids nul de toute façon |

L'URL Open-Meteo observée ne demande que `temperature_2m_max` et `precipitation_sum`, alors que le data dictionary en annonçait neuf. C'est **l'écart le plus coûteux de tout le pipeline**, et le moins cher à corriger : une ligne de configuration.

### Sur le FWI

`fwi_computable()` refuse le calcul et documente pourquoi. Van Wagner exige température, **humidité relative**, **vent** et précipitations — deux des quatre manquent. Même complètes, trois conditions supplémentaires resteraient à satisfaire : convention horaire (observation de milieu d'après-midi), initialisation de FFMC/DMC/DC, politique documentée pour les jours manquants. Aucun `historical_fwi_proxy` n'entre dans `F`.

### Sur la sémantique du vent

`wind_speed_10m_max` est une **vitesse maximale à 10 m**, pas une rafale. `check_wind_semantics()` refuse cet étiquetage. La confusion changerait l'ordre de grandeur du seuil.

---

## 3. Disponible après configuration

| Source | Blocage | Action |
|---|---|---|
| Copernicus / CDS | `~/.cdsapirc` absent ou incomplet | fournir `url:` et `key:` ; `check_copernicus_config()` valide **avant** tout appel. Statut actuel : `NOT_CONFIGURED` |
| Zonage neige NF EN 1991-1-3/NA | table commune → zone non installée | fournir un lookup versionné. **L'interface d'activation de P07 est déjà écrite** dans `rules/P07.yaml` (`hazard_activation_interface`), avec la formule d'altitude `sk_site = sk_zone × (1 + A/917)²` |
| Zonage vent NF EN 1991-1-4/NA | table commune → zone non installée | même mécanisme, variable `hazard.wind.eurocode_zone` déjà déclarée dans `rules/P05.yaml` avec un poids de 0,40 |
| Distances géospatiales | `geom_groupe` **est présent** en EPSG:2154 | calculables localement sans nouvelle API, contre une couche littorale, forestière ou hydrographique |

---

## 4. Absent ou bloquant

| Donnée | Nature du blocage | Statut |
|---|---|---|
| Climatologie grêle française | **aucune source ouverte identifiée.** La courbe MESHS de Schmid et al. 2024 est calibrée en Suisse et exige un radar grêle sans équivalent français public | P06 sans `F`, définitivement en l'état |
| Densité de foudroiement (Ng, Nsg, Nk) | donnée **commerciale** (Météorage, filiale Météo-France) | P10 sans `F` — décision d'achat, pas d'ingénierie |
| Classe de sol EC8 (effets de site) | non disponible | limite majeure de P03 : le zonage sismique est communal, les effets de site peuvent faire varier fortement le mouvement dans une même commune |
| Conversion accélération → intensité EMS-98 | absente du corpus | **μD de RISK-UE non implémentée** (décision 11). La table RISK-UE n'est utilisée qu'en classement ordinal |
| Extrait de sinistres assureur segmenté | inexistant | **aucun péril n'est calibré.** Tous les poids non publiés portent `provisional_modeling_weight` |
| Rayon et couverture des requêtes cavités / mouvements | non journalisés par le collector | `results = 0` reste ininterprétable, donc non exploité |

---

## 5. Matrice finale de suffisance par péril

Statuts observés sur Nice **sans réponse utilisateur** (`out/nice_result.json`), puis **avec** questionnaire renseigné (`out/nice_result_with_answers.json`).

| Péril | Sans réponses | Avec réponses | Dominante de `F` | Ce qui bloque |
|---|---|---|---|---|
| **P01** Inondation | `INDETERMINATE` | `INDETERMINATE` | `hazard.flood.zone` | AZI en 404 ; ni HAND ni distance au cours d'eau |
| **P02** RGA | `NEEDS_USER_INPUT` (F = 66) | `NEEDS_USER_INPUT` | `hazard.clay.exposure_class` ✔ | V exige le questionnaire fondations |
| **P03** Séisme | **`CALCULATED`** F = 75 · V = 49 · R = 60 · conf. 82 | **`CALCULATED`** R = 63 | `hazard.seismic.zone` ✔ | rien — seul péril complet sans questionnaire |
| **P04-CAV** Cavités | `INDETERMINATE` | `INDETERMINATE` | `cavities_count` | `results = 0` non interprétable |
| **P04-GLI** Glissement | `INDETERMINATE` | `INDETERMINATE` | `site.slope_degrees` | pente et TWI non dérivés |
| **P04-BLO** Chute de blocs | `NEEDS_USER_INPUT` | `NEEDS_USER_INPUT` | — (pas d'aléa) | aucune donnée d'aléa à la parcelle |
| **P04-TAS** Tassement | `NEEDS_USER_INPUT` | `NEEDS_USER_INPUT` | — (pas d'aléa) | idem ; le tassement RGA est traité par P02 |
| **P05** Vent | `INDETERMINATE` | `INDETERMINATE` | `climate.wind_speed_max_stat` | variable non demandée + 429 |
| **P06** Grêle | `NEEDS_USER_INPUT` | **`VULNERABILITY_ONLY`** V = 31 | — (aucun aléa) | aucune climatologie grêle FR |
| **P07** Neige | `NEEDS_USER_INPUT` | **`VULNERABILITY_ONLY`** V = 53 | — (aucun aléa) | zonage neige non installé |
| **P08** Incendie | `NEEDS_USER_INPUT` | **`CALCULATED`** R = 16 | `electrical.diagnosis_age` | questionnaire ; preuve faible |
| **P09** Feu de forêt | `INDETERMINATE` | `INDETERMINATE` | `site.distance_to_forest` | WFS non raccordé ; FWI incalculable |
| **P10** Foudre | `NEEDS_USER_INPUT` | **`VULNERABILITY_ONLY`** V = 28 | — (aucun aléa) | Météorage commercial |
| **P11** Dégâts des eaux | `NEEDS_USER_INPUT` | **`CALCULATED`** R = 31 | `plumbing.material` | questionnaire ; jours de gel absents |
| **P14** Submersion | `INDETERMINATE` | `INDETERMINATE` | `site.distance_to_coast` | pas de distance au trait de côte |

**Lecture.** Sur quinze blocs de péril, **un seul** est calculable de bout en bout sans intervention de l'habitant. Le questionnaire en débloque deux de plus et fait passer trois périls en vulnérabilité seule. Six restent indéterminés pour des raisons purement techniques, toutes corrigibles.

---

## 6. Vérification du nombre d'indicateurs — écart 184 / 196 résolu

Vérification menée sur les deux fichiers eux-mêmes, sans supposer lequel était correct (script `verify_count.py`).

| Fichier | md5 (12) | Indicateurs | Méthodes | Études | Onglets |
|---|---|---|---|---|---|
| `Referentiel_indicateurs_risk_engine_2.xlsx` | `cea1ace60e07` | **184** | 102 | 25 | 19 |
| `Referentiel_indicateurs_risk_engine_2_1.xlsx` | `fdd95e6d017c` | **196** | 111 | 30 | 24 |

**Delta v2 → v2_1 :** 12 indicateurs ajoutés, **0 retiré**, **0 doublon d'identifiant** dans l'un ou l'autre fichier.

Identifiants ajoutés : `RUE-A01`, `RUE-V01`, `MESHS-A01`, `SWZ-A01`, `KU-CUB-A01`, `FA-M01`, `AMC-01` à `AMC-06`.
Méthodes ajoutées : `M103` à `M111`. Onglets ajoutés : Courbes RISK-UE P03, Courbe MESHS P06, Courbes Vent P05, Benchmark P11 eau, Courbes AMC P14.

**Conclusion : aucun des deux chiffres n'est erroné.** 184 est l'état antérieur à l'ingestion du classeur de courbes ; 196 est l'état après. `184 + 12 = 196`. **`v2_1` fait foi.**

Ironie utile : ces douze lignes sont des **courbes de dommage monétaires**. Le passage au scoring ordinal les met hors architecture. Elles restent au référentiel pour une éventuelle phase AAL ultérieure, mais **aucune n'alimente ce moteur**.

---

## 7. Correctifs du collector, par rendement décroissant

| # | Action | Coût | Débloque |
|---|---|---|---|
| 1 | Ajouter `temperature_2m_min`, `wind_speed_10m_max`, `relative_humidity_2m_mean`, `soil_moisture_0_to_10cm_mean` au paramètre `daily` | **une ligne** | P11 entièrement, P05 et P09 partiellement, renforce P02 |
| 2 | Cache par maille climatique + backoff exponentiel avec jitter | faible | traite le 429 à la racine — une adresse n'est pas une maille |
| 3 | Calculer les distances littoral / forêt / cours d'eau depuis `geom_groupe` (EPSG:2154, déjà présent) | moyen | P09, P14, P01 |
| 4 | Aiguillage de typologie maison / collectif | moyen | justesse, pas couverture |
| 5 | Acquérir les tables Eurocode vent et neige | faible, non technique | P07 entièrement, renforce P05 |
| 6 | Configurer `.cdsapirc` **ou renoncer explicitement** | faible | Copernicus |
| 7 | Exploiter `fiabilite_*` de BDNB dans la confiance | faible | qualité de la confiance |
| 8 | Paginer intégralement les CatNat | faible | contexte uniquement (poids nul) |
| 9 | Journaliser rayon, filtres et couverture des requêtes cavités et mouvements | faible | rendrait `results = 0` interprétable, donc P04-CAV calculable |
| 10 | Désactiver ou remplacer explicitement l'endpoint AZI en 404 | faible | clarté ; P01 reste bloqué sans zonage PPRI géolocalisé |

---

## 8. Ce qu'il faudrait pour faire passer un péril à `CALCULATED`

| Péril | Donnée manquante précise | Difficulté |
|---|---|---|
| **P07** Neige | table officielle versionnée commune → zone (8 zones, `sk` de 0,45 à 1,40 kN/m²) | **la plus facile** — interface déjà écrite |
| **P11** Dégâts des eaux | `temperature_2m_min` dans l'appel Open-Meteo | **triviale** — une ligne |
| **P05** Vent | `wind_speed_10m_max` + table Eurocode vent | facile |
| **P09** Feu de forêt | distance à la forêt (calculable depuis `geom_groupe`) + humidité relative et vent pour le FWI | moyenne |
| **P14** Submersion | distance au trait de côte + zonage PPRL | moyenne |
| **P01** Inondation | zonage PPRI/TRI géolocalisé **ou** HAND validé. L'AZI seul ne suffira pas | moyenne |
| **P04-GLI** Glissement | pente et TWI dérivés du MNT RGE ALTI | moyenne |
| **P04-CAV** Cavités | journalisation du rayon et de la couverture de la requête | facile mais dépend du collector |
| **P06** Grêle | climatologie grêle française validée | **bloquée** — aucune piste ouverte identifiée |
| **P10** Foudre | densité de foudroiement Météorage | **bloquée** — achat commercial |
| **P03** Séisme (amélioration) | classe de sol EC8 pour les effets de site | difficile |
| **Tous** (calibration) | extrait de sinistres assureur anonymisé et segmenté | **la seule voie** pour passer de « classe correctement » à « prouve qu'il classe bien » |
