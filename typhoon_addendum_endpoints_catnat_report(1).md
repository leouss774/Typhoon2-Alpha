# ADDENDUM — Couverture endpoints, historique CatNat, visualisation par péril, rapport narratif Mistral

> Complète `typhoon_adresse_georisques_plan.md` et les re-audits précédents. Constat de départ, vérifié dans le code réel de `feature/restructure` : **6 endpoints Géorisques v1 sur ~20 sont utilisés**, l'historique CatNat n'est exposé que pour l'inondation, aucune visualisation par péril n'existe encore, et le module Mistral actuel génère des conseils courts, pas un rapport complet.

---

## 1. Couverture réelle des endpoints v1

| Endpoint | Utilisé ? | Rôle actuel / à ajouter |
|---|---|---|
| `gaspar/risques` | ✅ | Détection des aléas par mot-clé (inondation, argile, feu de forêt) |
| `gaspar/catnat` | ✅ (partiel) | Compte les arrêtés par mot-clé ; historique complet exposé seulement pour inondation |
| `azi` | ✅ | Atlas zones inondables |
| `cavites` | ✅ | Score mouvement de terrain |
| `zonage_sismique` | ✅ | Score sismicité |
| `radon` | ✅ | Score radon |
| `mvt` | ✅ | Score mouvement de terrain |
| `gaspar/pprn` / `pprt` / `pprm` | ❌ | **Priorité 1** — statut réglementaire de la parcelle, signal fort assurabilité/promoteur |
| `ssp`, `ssp/casias`, `ssp/conclusions_sis`, `ssp/conclusions_sup` | ❌ | **Priorité 1** — sols pollués, risque juridique/financier réel |
| `installations_classees` / `installations_nucleaires` | ❌ | Priorité 2 — proximité industrielle |
| `old` | ❌ | Priorité 2 — obligation débroussaillement, pertinent zones feu de forêt |
| `gaspar/tri`, `tri_zonage` | ❌ | Priorité 2 — détail zones inondation à risque important, complète `azi` |
| `gaspar/papi` | ❌ | Priorité 3 — contexte (programmes de prévention en cours), pas un score |
| `gaspar/dicrim`, `gaspar/tim` | ❌ | Priorité 3 — documents administratifs, traçabilité/liens plutôt que score |
| `resultats_rapport_risque` | ❌ | Voir §4 — candidat pour enrichir/valider le rapport narratif |
| `rapport_pdf` | ❌ | Voir §4 — bouton "télécharger le rapport officiel" |

**Recommandation d'ordre** : PPR et SSP d'abord (impact produit réel pour un promoteur), avant TRI/installations/OLD, puis PAPI/DICRIM/TIM en dernier (contexte, pas du scoring).

---

## 2. Historique CatNat — généraliser au lieu de le réserver à l'inondation

**Constat exact dans le code** : `_count_catnat_keyword(raw, "sécheresse")` compte les arrêtés pour la RGA, `_count_catnat_keyword(raw, "mouvement de terrain")` pour les MVT — mais `catnat_historique` n'est rattaché qu'à `_alea_inondation()`. Les autres périls comptent l'historique sans jamais l'exposer.

**Correctif** : extraire une fonction commune et l'appeler pour chaque péril concerné.

```python
def _catnat_entries_filtrees(raw: dict, keywords: list[str]) -> list[dict] | None:
    """Retourne les arrêtés CatNat dont le libellé contient un des mots-clés."""
    entries = _catnat_entries(raw)
    if not entries:
        return None
    kws = [k.lower() for k in keywords]
    filtrees = [
        e for e in entries
        if any(k in (e.get("libelle_risque_jo") or "").lower() for k in kws)
    ]
    return filtrees or None
```

Puis, dans chaque `_alea_*` concerné :
```python
# _alea_rga
catnat_hist=_catnat_entries_filtrees(raw, ["sécheresse", "secheresse"]),

# _alea_mouvement_terrain
catnat_hist=_catnat_entries_filtrees(raw, ["mouvement de terrain"]),

# _alea_inondation (déjà fait, mais filtrer aussi par mot-clé plutôt que tout prendre)
catnat_hist=_catnat_entries_filtrees(raw, ["inondation", "coulée"]),
```

**Pourquoi filtrer et pas juste dupliquer la liste complète** : aujourd'hui `_alea_inondation` attache TOUS les arrêtés CatNat de la commune, même ceux qui concernent une tempête ou un mouvement de terrain sans rapport avec l'inondation. C'est une inexactitude silencieuse : l'utilisateur voit "historique CatNat" sous la carte inondation, mais certaines lignes ne concernent pas l'inondation. Filtrer par mot-clé, comme le comptage le fait déjà, corrige ça en même temps que ça généralise l'exposition aux autres périls.

Front (`zone.html`) : aucun changement nécessaire, le rendu `catnat_historique` existe déjà et fonctionne par aléa — il suffira qu'il reçoive des données pour RGA/MVT en plus de l'inondation.

---

## 3. Visualisation par péril — calques sur la carte

Le front (`zone.html`, MapLibre 4.7.1) n'affiche aujourd'hui qu'un marqueur ponctuel. Ajout proposé, par ordre de coût/valeur :

### 3.1 Anneaux de gravité autour du point (coût faible, valeur immédiate)
Pas besoin de vraies géométries de zonage pour commencer : un cercle coloré par bande D03 autour du marqueur, un par péril actif, en petit multiple ou en switcher de calque (comme le mockup GEE-style déjà livré `typhoon_zone_risk_mockup.html`).

```javascript
// Un calque GeoJSON par péril, rayon fixe, couleur = bande D03
const aleaLayer = {
  type: 'Feature',
  properties: { code: alea.code, niveau: alea.niveau },
  geometry: { type: 'Point', coordinates: [lon, lat] }
};
map.addLayer({
  id: `alea-${alea.code}`,
  type: 'circle',
  source: { type: 'geojson', data: aleaLayer },
  paint: {
    'circle-radius': 40,
    'circle-color': BAND_COLORS[alea.niveau],
    'circle-opacity': 0.35,
    'circle-stroke-width': 1.5,
    'circle-stroke-color': BAND_COLORS[alea.niveau],
  }
});
```
Un sélecteur (les mêmes "layer pills" que le mockup) bascule quel péril est affiché en surbrillance.

### 3.2 Vrais polygones de zonage (coût moyen, valeur forte)
Géorisques expose des géométries réelles pour plusieurs registres :
- `azi` → périmètre de l'atlas de zone inondable (à vérifier si la réponse contient une géométrie ou juste un identifiant — souvent il faut croiser avec le portail cartographique Géorisques pour le GeoJSON)
- `tri_zonage` → zonage réglementaire TRI (probablement avec géométrie)
- `zonage_sismique` → zonage communal (le zonage sismique est en réalité national par commune, donc un simple contour communal suffit, pas besoin de polygone détaillé)

**Point de vigilance honnête** : la documentation Swagger fournie ne montre pas de champ géométrie (WKT/GeoJSON) dans les schémas de réponse listés — `azi`, `catnat`, etc. ne semblent renvoyer que des métadonnées (dates, libellés, code_insee), pas de géométrie directement exploitable pour dessiner un polygone. Il faudra vérifier avec un appel réel si un champ géométrie existe dans la réponse complète (le Swagger montre peut-être un schéma tronqué), sinon le contour communal (IGN, déjà utilisé pour d'autres besoins) reste le seul polygone fiable disponible pour aujourd'hui.

### 3.3 Heatmap communal (coût moyen, valeur pour le mode zone futur)
Pertinent seulement une fois le Sprint C (mode zone) construit — un point par commune de la grille, coloré par score global, rendu en `heatmap` MapLibre plutôt qu'en marqueurs individuels pour lisibilité à grande échelle.

---

## 4. Rapport narratif complet généré par Mistral (style `resultats_rapport_risque`)

`adresse_recommandations.py` génère aujourd'hui un résumé court + listes d'actions. Ce que vous demandez ici est un **rapport plus long et structuré**, plus proche de ce que produit le rapport officiel Géorisques — sans copier son texte (droits d'auteur/contenu officiel), mais avec la même exhaustivité de structure.

### 4.1 Nouveau contrat de sortie

```python
class SectionRapport(BaseModel):
    titre: str
    contenu: str            # 2-4 phrases, jamais de chiffre inventé
    aleas_associes: list[str]  # codes des AleaDetail concernés

class RapportNarratif(BaseModel):
    introduction: str                  # 2-3 phrases de cadrage général
    sections: list[SectionRapport]     # une par péril présent + une section CatNat si historique
    synthese_finale: str               # ce qui domine, ce qui est secondaire
    obligations_reglementaires: list[str] | None = None  # si PPR/OLD branchés (§1)
    genere_par: str = "mistral-small-latest"
    avertissement_ia: str = (
        "Ce rapport est généré automatiquement à partir des données Géorisques "
        "normalisées ci-dessus. Il ne remplace pas l'ERRIAL ni l'avis d'un professionnel."
    )
```

### 4.2 Principe de génération — identique à `adresse_recommandations.py`, étendu

- **Toujours à partir du `RisqueReport` déjà normalisé**, jamais des données Géorisques brutes — même règle non négociable que pour les recommandations courtes.
- **Une section par péril présent**, pas par péril interrogé — si `present=False` ou `present=None`, pas de section dédiée (mentionné au plus dans la synthèse : "aucune donnée disponible pour X").
- **CatNat comme section à part**, alimentée par les historiques désormais filtrés par péril (§2) — permet une vraie narration temporelle ("trois arrêtés sécheresse depuis 2003") sans que Mistral invente de dates : les dates viennent du JSON fourni, jamais générées.
- **Génération en un seul appel Mistral**, pas un appel par section — moins de latence, moins de risque d'incohérence entre sections.

```python
_SYSTEM_PROMPT_RAPPORT = """Tu rédiges un rapport de risques immobiliers structuré, en français,
pour un particulier ou un promoteur, à partir d'un JSON de données Géorisques déjà normalisées.

RÈGLES STRICTES :
- Une section par péril présent (present=true) dans les données fournies.
- N'invente AUCUNE date, AUCUN chiffre, AUCUN fait absent du JSON fourni.
- Si un péril a un historique CatNat, mentionne le nombre d'arrêtés et la période couverte
  (calculée à partir des dates du JSON, jamais estimée).
- La synthèse finale doit hiérarchiser les périls par niveau (bandes D03), pas par ordre d'apparition.
- Réponds uniquement en JSON, structure RapportNarratif ci-dessous, sans texte hors JSON.
"""
```

### 4.3 Fallback PDF officiel, en complément (pas en remplacement)

Ajouter un lien "Voir le rapport officiel Géorisques (PDF)" pointant vers `GET /api/v1/rapport_pdf?latlon=...` — génère le PDF officiel signé Géorisques pour la même adresse, sans que vous ayez à reproduire son contenu exact (évite tout risque de contrefaçon de mise en page officielle) tout en donnant accès à la source primaire à côté de votre rapport enrichi.

### 4.4 Fail-soft, identique au principe déjà en place
- Timeout/erreur Mistral → `rapport_narratif=None`, le `RisqueReport` factuel + `recommandations` courtes restent affichés normalement.
- Latence : ce rapport plus long prendra probablement plus de temps qu'un simple résumé — envisager de le déclencher **à la demande** (bouton "Générer le rapport complet") plutôt qu'automatiquement à chaque appel `/diagnostic/adresse`, pour ne pas alourdir la latence du chemin principal. Nouvel endpoint dédié suggéré :

```
POST /diagnostic/adresse/rapport
body: { risque_report: {...} }   # le RisqueReport déjà obtenu via /diagnostic/adresse
→ RapportNarratif | 502 si Mistral indisponible
```

---

## 5. Ordre de build suggéré

1. **CatNat généralisé** (§2) — petit changement, corrige une inexactitude actuelle, active immédiatement plus de contenu pour le futur rapport narratif.
2. **PPR + SSP** (§1, priorité 1) — nouveaux `_alea_*` dans `georisques.py`, même pattern fail-soft que l'existant.
3. **Rapport narratif Mistral** (§4) — nouvel endpoint séparé, réutilise `RisqueReport` enrichi par les étapes 1-2.
4. **Anneaux de gravité par péril sur la carte** (§3.1) — visuel, indépendant du reste, peut être fait en parallèle.
5. **Polygones réels / heatmap zone** (§3.2-3.3) — après vérification de la disponibilité réelle de géométries dans les réponses Géorisques, et après le Sprint C (mode zone).

---

## 6. Prompt court (agent de code)

> Étape 1 : dans `georisques.py`, généralise l'exposition de `catnat_historique` à `_alea_rga` et `_alea_mouvement_terrain` via une fonction commune `_catnat_entries_filtrees(raw, keywords)`, en filtrant par mot-clé au lieu d'attacher la liste complète comme le fait actuellement `_alea_inondation`. Étape 2 : ajoute les connecteurs `pprn`/`pprt`/`pprm` et `ssp` (mêmes conventions fail-soft que l'existant, un `_alea_*` par registre). Étape 3 : crée `app/recommandations/rapport_narratif.py` sur le modèle exact de `adresse_recommandations.py` (même règle : le prompt Mistral ne reçoit que le `RisqueReport` déjà normalisé, jamais les données brutes), exposé via un nouvel endpoint `POST /diagnostic/adresse/rapport` séparé de `/diagnostic/adresse` pour ne pas alourdir la latence du chemin principal.
