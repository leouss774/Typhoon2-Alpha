# Risk Engine Typhon

> ## ⚠️ STATUT : EN MIGRATION — NE PAS UTILISER EN PRODUCTION
>
> Ce module est un **candidat au remplacement futur** de `app/scoring/risk_model.py`.
> Il contient un moteur de règles YAML complet (P01–P14) **non connecté** à l'API FastAPI.
>
> **Source de vérité actuelle pour le scoring** : `backend/app/scoring/risk_model.py`
> (importé par `app/agents/scoring_agent.py` et appelé par les routes `/diagnostic*`).
>
> **Ne modifier que `risk_model.py`** pour tout changement affectant le comportement
> de production. Les modifications ici n'ont aucun effet sur l'API tant que la
> migration n'est pas terminée.
>
> Voir `typhoon_reaudit_feature_restructure.md` §2.2 pour le contexte.
> Date de ce statut : 02/08/2026.

---

Moteur multi-périls déterministe pour l'assurance habitation française. Produit, **par péril et indépendamment**, un indice ordinal d'aléa `F`, un indice de vulnérabilité `V`, un risque `R` et un score de confiance.

**Ne produit ni AAL, ni euros, ni score global.**


## Installation

```bash
pip install pyyaml pytest
```

## Usage

```bash
# Évaluation depuis un JSON de collector
python3 -m risk_engine.cli tests/fixtures/nice_06088.json --out out/result.json

# Avec réponses du questionnaire, et émission des questions restantes
python3 -m risk_engine.cli tests/fixtures/nice_06088.json \
    --answers tests/fixtures/answers_nice_apartment.json \
    --questionnaire --out out/result.json

# Tests
python3 -m pytest tests/ -q

# Analyse de sensibilité des poids provisoires
python3 tools/sensitivity.py tests/fixtures/synthetic_high.json \
    --answers tests/fixtures/synthetic_high_answers.json
```

En bibliothèque :

```python
from risk_engine import assess, load_rules
result = assess(collector_json, answers, load_rules())
result["perils"]["P03"]["risk"]["score"]
```

## Structure

```
risk_engine/
  canonical.py            contrat de variable : 9 statuts, 8 portées, hiérarchie de rangs
  transforms.py           3 formes autorisées : categorical, linear_ramp, boolean
  rules_loader.py         chargement + validation stricte des YAML
  normalizer.py           JSON collector -> variables canoniques
  engine.py               calcul F, V, R, statuts de péril
  confidence.py           confiance, indépendante du risque
  questionnaire.py        questionnaire dynamique
  collector_hardening.py  adaptateurs et correctifs, testables sans réseau
  cli.py
rules/                    SOURCE DE VÉRITÉ des constantes métier
  _common.yaml            combinaison, seuils de publication, confiance, bandes
  P01..P14.yaml           15 fichiers de péril (P04 décomposé en 4)
  questionnaire.yaml      69 questions, 9 sections
tests/                    88 tests
tools/sensitivity.py      diagnostic de sensibilité des poids
docs/
  PHASE1_1_AUDIT_CORRIGE.md
  METHODOLOGIE.md
  JOURNAL_DECISIONS.md
```

## Ajouter un péril sans toucher au cœur

1. Créer `rules/PXX.yaml` avec `peril_id`, `name`, `hazard_available`.
2. Déclarer les blocs `frequency` et/ou `vulnerability`. Chacun doit :
   - sommer ses poids à **exactement 1** ;
   - désigner **exactement une** variable `dominant: true` ;
   - fournir pour chaque variable les 15 champs obligatoires (voir `rules_loader.REQUIRED_VAR_FIELDS`), dont `physical_mechanism`, `references`, `evidence_level` et `calibration_status`.
3. Si aucune donnée d'aléa n'existe : `hazard_available: false` + `hazard_absence_reason`. Le moteur produira `VULNERABILITY_ONLY` avec le libellé réglementaire, sans `F` ni `R`. Le loader **refuse** de charger des variables de fréquence dans ce cas.
4. Mapper les variables sources dans `normalizer.py` si elles ne sont pas déjà normalisées.
5. Ajouter les questions dans `rules/questionnaire.yaml` avec `used_by: ["PXX"]`.

Aucune modification de `engine.py` n'est nécessaire. Le loader valide au chargement et refuse un jeu de règles incohérent plutôt que de le corriger silencieusement.

## Garde-fous vérifiés par test

- somme des poids = 1, exactement une dominante par bloc
- `DEFAULT_VALUE` exclue du calcul
- CatNat et booléens communaux à poids nul dans `F`
- `SOURCE_ERROR` ≠ `NO_FEATURE_FOUND`
- dominante absente ⇒ `INDÉTERMINÉ`, sans score caché
- `F = 0` ⇒ `R = 0` ; `R` monotone en `F` et `V`
- une protection ne peut jamais augmenter `V` ; plafond 50 % ; plancher `Vmin = 10`
- reproductibilité bit à bit
- P06, P07, P10 sans `F` ni `R`
- aucune sortie globale, aucune valeur monétaire
- aucune donnée nominative en sortie
