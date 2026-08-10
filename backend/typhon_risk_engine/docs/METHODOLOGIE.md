# Méthodologie du Risk Engine Typhon

**Version moteur** 2.0.0 · **Version règles** 1.0.0 · 28 juillet 2026

---

## 1. Ce que ce moteur produit — et ce qu'il ne produit pas

Il produit, **par péril et indépendamment** :

- `F` — un **indice ordinal d'aléa, d'exposition ou de fréquence relative**, de 0 à 100 ;
- `V` — un indice ordinal de vulnérabilité du bâti, de 0 à 100 ;
- `R = 100 × (F/100)^0,5 × (V/100)^0,5` ;
- une classe de lecture parmi cinq bandes ;
- un score de confiance, **indépendant du risque** ;
- la traçabilité complète : variables utilisées, variables manquantes et pourquoi, mécanismes physiques, références, niveau de preuve.

Il ne produit **aucun** : score global multi-périls, AAL, perte attendue, valeur de reconstruction, prix de marché, probabilité annuelle. Deux garde-fous explicites (`global_score: null`, `monetary_output: null`) sont vérifiés par test.

### Sur le nom `F`

`F` est conservé pour la compatibilité de l'architecture. **Ce n'est pas une fréquence annuelle.** Aucune donnée du corpus ne permet de calibrer une fréquence par adresse. Un `F = 75` sur P03 signifie « zone sismique 4 sur 5 dans un classement ordinal », pas « 75 % de chance annuelle ». La sortie porte ce libellé littéralement, sur chaque bloc de fréquence.

---

## 2. Séparation aléa / vulnérabilité

L'aléa est attaché à l'**adresse ou à la parcelle**. La vulnérabilité est attachée au **bâtiment**. Les deux ne se mélangent qu'à l'ultime combinaison. Cette séparation est structurelle : un même bâtiment déplacé change de `F` sans changer de `V`.

Conséquence pratique : les protections (clapet, détecteur, débroussaillement, parafoudre) agissent **uniquement sur `V`**. Un batardeau ne fait pas baisser le niveau de la crue.

---

## 3. La formule de combinaison

`R = 100 × (F/100)^0,5 × (V/100)^0,5`

Moyenne géométrique pondérée. Trois propriétés voulues :

- **non compensatoire** : `F = 0` donne `R = 0` quelle que soit `V`. Sans aléa, pas de risque ;
- **monotone** en `F` et en `V`, testée sur toute la plage ;
- bornée dans [0, 100].

Les exposants sont **configurables en YAML** et étiquetés `provisional_uncalibrated`. Ils valent 0,5 / 0,5 par décision. Ce n'est pas un résultat, c'est une hypothèse de travail : rien dans le corpus ne justifie 0,5 plutôt que 0,6/0,4.

**Plancher `Vmin = 10`** : aucun bâtiment n'est invulnérable. **Plafond de protection à 50 %** : les protections déclaratives ne peuvent jamais réduire `V` de plus de moitié, parce qu'un équipement déclaré n'est ni vérifié ni forcément entretenu.

---

## 4. Règles de publication — quand le moteur refuse de répondre

Un bloc devient **`INDÉTERMINÉ`** si :

1. sa **variable dominante** est absente — même si moins de 50 % du poids manque ;
2. **plus de 50 % du poids théorique** est manquant.

Chaque bloc a **exactement une** variable dominante, vérifiée au chargement des règles. C'est la variable qui mesure le plus directement le mécanisme physique. Sans elle, le reste ne fait que décorer.

La **renormalisation** des poids n'est autorisée que si la dominante est présente **et** le seuil respecté. Une donnée manquante n'est **jamais imputée**, ni au cas favorable, ni au cas défavorable.

Un score `INDÉTERMINÉ` n'a **aucune valeur numérique cachée** : `risk` vaut `null`, testé.

### Les six statuts de péril

| Statut | Signification |
|---|---|
| `CALCULATED` | `F`, `V` et `R` publiés |
| `NEEDS_USER_INPUT` | le blocage est levable par le questionnaire |
| `INDETERMINATE` | le blocage est technique, l'habitant n'y peut rien |
| `VULNERABILITY_ONLY` | `V` seul, avec le libellé obligatoire « Sensibilité du bâtiment hors exposition — ne constitue pas un score de risque » |
| `NOT_APPLICABLE` | sans objet pour ce bien |
| `UNSUPPORTED` | hors périmètre |

---

## 5. Les neuf statuts de variable — pourquoi ils ne sont pas interchangeables

Un `null` brut n'existe pas dans le moteur. Quatre situations qu'on confond couramment et qui ne veulent pas dire la même chose :

| Statut | Ce que ça dit | Ce que ça ne dit pas |
|---|---|---|
| `NO_FEATURE_FOUND` | la requête a abouti, zéro objet retourné dans ce rayon et selon la couverture de cette base | « risque nul » |
| `SOURCE_ERROR` | l'API a échoué (404, 429, 5xx) | **rien du tout sur le phénomène** |
| `NOT_CONFIGURED` | la source existe mais n'est pas paramétrée | que la donnée est indisponible en soi |
| `NOT_COLLECTED` | le pipeline ne demande pas ce champ | que le champ n'existe pas |

S'y ajoutent `AVAILABLE`, `NOT_APPLICABLE`, `DEFAULT_VALUE`, `UNKNOWN` et `USER_UNKNOWN`.

**Cas concret.** Sur Nice, l'endpoint AZI renvoie 404. Le traduire en « aucune zone inondable » produirait un score faussement rassurant sur une commune du littoral méditerranéen. Le moteur émet `SOURCE_ERROR` et P01 reste `INDÉTERMINÉ`. Un test verrouille cette distinction.

**Second cas.** `cavites.results = 0`. Sans le rayon ni la couverture de la base, ce zéro est ininterprétable. La règle `P04-CAV` **n'active pas** `accept_no_feature` : le bloc reste indéterminé plutôt que de publier un aléa nul.

---

## 6. Hiérarchie des sources et conflits

**Données bâtiment** (1 = meilleur) : document vérifié / observation directe récente / déclaration ou estimation / BDNB ou inférence publique / inconnu.

**Données d'aléa** : mesure ou zonage à la parcelle / donnée locale réglementaire / zonage officiel communal / maille climatique ou départementale / contexte communal ou proxy / valeur par défaut (**exclue**).

Une source de rang inférieur n'écrase **jamais** une source de rang supérieur. En cas de contradiction, **les deux valeurs sont conservées** (`superseded`), la hiérarchie tranche, le conflit est enregistré, et la composante de cohérence de la confiance baisse.

Une impression de l'habitant sur la nature du sol ne remplace pas `alea_argile`. Une étude géotechnique, si.

---

## 7. Ce qui est explicitement exclu du calcul

**CatNat et booléens communaux : poids strictement nul.** Un arrêté CatNat reflète autant la démarche administrative de la commune que l'aléa physique. Il reste affiché comme contexte et historique.

**Valeurs par défaut : exclues.** `hailRisk`, `snowZone = A1`, `landUse = urban` sont des constantes de remplissage. Elles reçoivent `DEFAULT_VALUE` et sont inutilisables. Le champ `is_default` force ce statut, quel que soit ce qu'on tente d'écrire par-dessus.

**Projections climatiques : jamais dans `F`, `V` ou `R`.** Le bloc prospectif est séparé et sans influence.

**Statistiques de sinistrés comme coefficients : refusées.** Le corpus contient des chiffres tentants — 87 % de fondations sous 1,20 m chez les sinistrés RGA, 38 % d'encastrement variable, D2 comme grade modal. Ce sont des distributions **conditionnelles au sinistre**, sans groupe témoin. Les utiliser comme coefficients causals reviendrait à confondre `P(fondation superficielle | sinistre)` avec `P(sinistre | fondation superficielle)`. Elles orientent le **sens** des règles, jamais leur **valeur**.

**Double comptage RGA : évité.** `alea_argile` est la classe **publiée** de la carte. Réappliquer par-dessus l'algorithme BRGM (lithologie × minéralogie × géotechnique) qui a servi à produire cette carte compterait deux fois la même information. Un test vérifie qu'aucune variable lithologique n'entre dans P02.

**μD de RISK-UE : non implémentée.** L'équation exige une intensité EMS-98 ; le zonage français fournit une accélération. Aucune conversion justifiée n'existe dans le corpus. La table RISK-UE n'est utilisée qu'en **classement ordinal des typologies**.

---

## 8. Score de confiance

Cinq composantes, indépendantes du risque :

| Composante | Poids | Contenu |
|---|---|---|
| Géocodage et correspondance d'entité | 20 % | score BAN, existence de la parcelle, adresse saisie vs groupe BDNB, distinction logement / bâtiment / groupe |
| Complétude pondérée | 30 % | couverture réelle des blocs |
| Échelle spatiale | 25 % | pondérée par la portée des variables effectivement utilisées |
| Niveau de preuve | 15 % | `high` / `medium` / `low` des règles utilisées |
| Cohérence | 10 % | conflits, erreurs de source, pagination incomplète |

**Plafond à 40** si le score est porté majoritairement par des données de rang 5.

**Une faible confiance ne réduit jamais le risque.** Ce sont deux questions distinctes : « quel est le risque ? » et « à quel point puis-je me fier à cette réponse ? ». Les mélanger produirait des scores faussement rassurants pour les biens mal documentés — exactement l'inverse de ce qu'il faut.

---

## 9. Le questionnaire

Dynamique : filtré par typologie de bien et par périls réellement débloquables. Sur le cas de Nice (appartement en tour), ni les questions de fondations ni celles de toiture ne sont posées — elles ne changeraient aucun score et feraient perdre la confiance de l'utilisateur.

Chaque question offre **« Je ne sais pas »**, qui produit `USER_UNKNOWN`. Un test vérifie que ce statut ne vaut jamais le cas défavorable.

Chaque réponse porte sa **base de connaissance** : `observé`, `document`, `souvenir`, `estimation`, `inconnu` — qui détermine le rang de source. Un plan de fondation cité monte au rang 1, un souvenir reste au rang 3.

**Aucun texte libre n'entre dans le calcul.** Les champs libres sont conservés en pièce jointe pour l'expert.

Les questions sont ordonnées par priorité : celles qui débloquent une variable **dominante** manquante d'abord.

---

## 10. Limites majeures à afficher à l'utilisateur

1. **Aucun péril n'est calibré.** Toutes les pondérations non publiées portent `provisional_modeling_weight`. Le moteur classe ; il ne prouve pas qu'il classe bien. Seul un extrait de sinistres assureur segmenté permettrait de le vérifier.

2. **P03 repose sur un zonage communal.** Les effets de site (classe de sol EC8) peuvent faire varier fortement le mouvement dans une même commune. Ils sont indisponibles.

3. **Le corpus de vulnérabilité est calibré sur la maison individuelle.** BRGM, Mzungu, SafeLand, CEPRI décrivent tous le pavillon. Appliqués à une tour de 17 étages, les facteurs « profondeur de fondation » ou « distance aux arbres » perdent leur validité. Le moteur détecte la typologie et émet un avertissement explicite — il ne prétend pas corriger le problème.

4. **BDNB décrit un groupe de bâtiments.** Sur Nice, 11 adresses partagent le même `batiment_groupe_id`. Le matériau de mur est celui de l'ensemble immobilier, pas de l'appartement.

5. **P08 et P11 sont des modèles ordinaux de niveau de preuve faible.** Aucun taux de base, aucun coefficient segmenté n'existe dans le corpus. Le seul repère chiffré disponible pour P11 est un taux national non segmenté, inutilisable individuellement. Ces deux périls sont aussi les plus sensibles à la perturbation des poids — voir l'analyse de sensibilité.

6. **Six périls sont indéterminés pour des raisons techniques**, non méthodologiques. Elles sont listées et chiffrées dans l'audit corrigé.

---

## 11. Déterminisme

Aucun appel LLM, aucun aléatoire, aucune constante métier dans le code Python. Toutes les valeurs vivent dans `rules/`, dont une empreinte SHA-256 (`rules_digest`) est publiée avec chaque résultat. Pour un même couple (données, version de règles), la sortie est identique bit à bit — vérifié par test.

---

## 12. Analyse de sensibilité — diagnostic, pas calibration

Chaque poids `provisional_modeling_weight` est perturbé de ±0,10, le bloc est renormalisé, et l'on observe les changements de classe ou de statut. 64 poids provisoires, 128 perturbations par scénario.

Résultats :

| Scénario | Changements | Poids critiques identifiés |
|---|---|---|
| `synthetic_low` | 0 | — |
| `synthetic_high` | 1 | `P03 / V / building.levels` |
| `synthetic_medium` | 5 | `P02 / V / foundation.uniform` ; `P08 / F / dhw.generator` ; `P08 / F / chimney.sweep_age` ; `P08 / V / fire.attached_garage` ; `P08 / V / fire.converted_attic` |

Deux enseignements. D'abord, **P08 concentre la sensibilité** — cohérent avec son niveau de preuve, le plus faible du moteur. Ensuite, les bascules surviennent près des frontières de bande : un score de 59,6 contre 60,2 fait passer de « modéré » à « élevé ». C'est une propriété de toute échelle en bandes, pas un défaut du modèle, mais il faut l'afficher.

**Aucun poids n'a été ajusté pour faire passer ce test.** L'analyse est un diagnostic. Un poids critique doit être justifié par une source ou la variable retirée — jamais bricolé.

L'analyse a en revanche révélé un **vrai bug** : la classification opérait sur le flottant brut, laissant un trou entre 79 et 80. Un score de 79,4 n'appartenait à aucune bande. Corrigé — la classification porte désormais sur l'entier publié, avec levée d'exception si un score sortait de toutes les bandes.
