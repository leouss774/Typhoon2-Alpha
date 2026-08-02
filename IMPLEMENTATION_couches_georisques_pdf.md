# Implémentation — Extension couches Géorisques (13 périls) + toggle œil + rapport PDF officiel

**Fichiers concernés :**
`frontend/jumeau_numerique/zone.html` · `backend/app/connectors/georisques.py` ·
`backend/app/schemas/risque_report.py` · `backend/app/api/routes/diagnostic.py`

**Branche cible :** `feature/restructure`
**Dépend de :** `IMPLEMENTATION_carte_openlayers.md` (migration OpenLayers déjà en place, layer toggle pastilles déjà en place)

**⚠️ Document de planification uniquement.** Aucune modification de code n'a été appliquée par ce document — il sert de spécification prête à être implémentée dans une prochaine session.

---

## 1. Contexte

État actuel constaté sur `feature/restructure` (dépôt cloné et inspecté) :

- Le backend (`georisques.py`) ne couvre que **8 aléas** : `inondation`, `rga`, `sismicite`, `radon`, `feu_foret`, `mouvement_terrain`, `ppr`, `ssp`.
- Le frontend (`zone.html`) n'a de couche WMS confirmée que pour 3 d'entre eux (`rga`, `inondation`, `sismicite`), les autres retombant sur un cercle de repli.
- Le toggle de calques existant (`buildLayerToggle`) est un sélecteur **exclusif** (pastilles "Tous les périls" / un péril à la fois) — pas une case à cocher indépendante par calque.
- Il n'existe aujourd'hui aucun appel vers l'endpoint officiel de rapport PDF Géorisques ; le rapport IA (`/diagnostic/adresse/rapport`) est un texte structuré généré par Mistral, pas un fichier PDF téléchargeable.

Ce document couvre trois chantiers distincts :

1. **Couvrir les 13 catégories de périls de la carte interactive officielle** (`georisques.gouv.fr/cartes-interactives`) avec de vraies couches WMS confirmées.
2. **Remplacer le toggle exclusif par des cases à cocher indépendantes avec icône œil** (afficher/masquer chaque calque sans en exclure d'autres).
3. **Ajouter un vrai rapport PDF téléchargeable**, généré par l'endpoint officiel Géorisques (`/api/v1/rapport_pdf`), en plus du rapport narratif IA existant.

---

## 2. Recherche — endpoints et couches confirmés

### 2.1 API Géorisques v1 (backend)

Source : `https://www.georisques.gouv.fr/doc-api` (aucune clé requise pour v1, 1000 req/min/IP).

Endpoints déjà utilisés par `georisques.py` (`_BASE = https://www.georisques.gouv.fr/api/v1`) :
`gaspar/risques`, `gaspar/catnat`, `azi`, `cavites`, `zonage_sismique`, `radon`, `mvt`, `gaspar/pprn`, `ssp`.

Endpoints supplémentaires confirmés (nécessaires pour couvrir les nouvelles catégories) :

| Endpoint v1 | Usage |
|---|---|
| `installations_classees` | ICPE — paramètres `code_insee` ou `latlon` + `rayon` |
| `gaspar/pprt` | PPR technologique (risque industriel) — `code_insee` |
| `rapport_pdf` | **Rapport PDF officiel complet** — `latlon=lon,lat` |

> ⚠️ `gaspar/risques` (déjà appelé) contient déjà les mots-clés bruts pour avalanches, submersion marine, éruption volcanique et phénomènes météorologiques (dont vents cycloniques dans les DOM-TOM) — pas besoin de nouvel appel réseau pour ces aléas, seulement de nouveaux filtres `_has_hazard_keyword(...)` sur les données déjà collectées, comme c'est déjà fait pour `feu_foret`.
>
> Pas d'endpoint v1 dédié identifié pour "réseaux et canalisations" ni pour "territoires" (TRI) au niveau attribut — ces deux couches sont **cartographiques uniquement** (WMS, voir §2.2), sans équivalent JSON par adresse dans l'API v1 publique.

### 2.2 Couches WMS confirmées (BRGM `GEORISQUES_SERVICES`)

Service : `https://mapsref.brgm.fr/wxs/georisques/risques` (WMS 1.3.0, déjà utilisé pour `rga`/`inondation`/`sismicite` dans le code actuel).

Capabilities confirmées via l'annuaire Spatineo (miroir de métadonnées du service GEORISQUES_SERVICES du BRGM, 175 couches recensées) et vérifiées ponctuellement avec les couches déjà en usage (`LIMITETRI`, `ms:SSP_CLASSIF_SIS_GE`).

**⚠️ Point de vigilance avant merge :** le code actuel utilise `ALEARG_2019` et `risq_zonage_sismique`, deux noms qui **n'apparaissent pas** dans la liste de couches confirmée ci-dessous (qui donne plutôt `ALEARG` / `ALEARG_REALISE` et `SIS_INTENSITE*`). Il est possible que ces noms existent quand même sur le service de production sans figurer dans le miroir Spatineo (couches ajoutées depuis, ou service `risques` légèrement différent de `georisques_services`). **Avant d'implémenter, relancer un `GetCapabilities` direct sur `https://mapsref.brgm.fr/wxs/georisques/risques?service=WMS&version=1.3.0&request=GetCapabilities` et differ (`grep -i "<Name>"`) avec le tableau ci-dessous pour trancher.**

| Péril (carte interactive) | Code aléa proposé | Couche(s) WMS confirmée(s) | Type géométrie |
|---|---|---|---|
| Argiles (RGA) | `rga` | `ALEARG` (ou `ALEARG_REALISE` / `ALEARG_REALISE_PE` — à trancher, cf. avertissement) | polygone |
| Avalanches | `avalanche` | `PPRN_ZONE_AVALANCHE_FXX` (zonage réglementaire fin) — repli commune : `PPRN_COMMUNE_AVALANCHE_APPROUV` / `PPRN_COMMUNE_AVALANCHE_PRESCRIT` | polygone |
| Cavités | `cavite` | `CAVITE_LOCALISEE` (points géolocalisés BD Cavités) | point |
| Feu (de forêt) | `feu_foret` | `PPRN_ZONE_FEU_FXX` — repli commune : `PPRN_COMMUNE_FEU_APPROUV` / `PPRN_COMMUNE_FEU_PRESCRIT` | polygone |
| Inondation | `inondation` | `LIMITETRI` *(déjà en place, inchangé)* + option `TRI_COMMUNE` | polygone |
| Installations industrielles (ICPE) | `icpe` | `INSTALLATIONS_CLASSEES_SIMPLIFIE` (toutes ICPE) + `ICPE_SEVESO` (sur-couche Seveso) | point |
| Mouvements de terrain | `mouvement_terrain` | `MVT_LOCALISE` (points BDMVT) — remplace le repli WFS actuel `ms:PPRN_COMMUNE_CAVITE_*` qui ciblait en fait le sous-aléa cavités, pas MVT générique | point |
| Plans de prévention des risques (PPR, vue consolidée) | `ppr` | `PPRN_COMMUNE_GASPAR` (PPR naturels, toutes natures confondues) + `PPRT_COMMUNE_GASPAR` (PPR technologiques) *(garder en synthèse ; les sous-PPR par nature alimentent chaque péril dédié ci-dessus)* | polygone |
| Radon | `radon` | `RADON` (potentiel radon à la commune — remplace le cercle de repli systématique actuel) | polygone |
| Réseaux et canalisations | `canalisations` | `CANALISATIONS` (vue consolidée) ou détail par fluide : `C_GAZ`, `C_HYDROCARBURES`, `C_PRODUITS_CHIM` | ligne |
| Sites et sols (potentiellement) pollués | `ssp` | `SSP_CLASSIF_SIS_GE` *(déjà en place en WFS)* + `SSP_ETS_GE_POLYGON`/`SSP_ETS_GE_POINT` (anciens sites BASIAS) + `SSP_INSTR_GE_POLYGONE` (BASOL) | mixte |
| Séismes | `sismicite` | `SIS_INTENSITE_MAXCOM` (intensité interpolée max par commune) — cf. avertissement ci-dessus sur `risq_zonage_sismique` | polygone |
| Territoires (à risque important d'inondation) | `territoires` | `TRI_COMMUNE` (limites de commune concernée par un TRI) — se recoupe avec `inondation`/`LIMITETRI`, à afficher comme sous-calque optionnel plutôt que péril indépendant | polygone |
| Vents cycloniques | `vent_cyclonique` | Pas de couche WMS dédiée identifiée. Rattaché aux PPR "Phénomène météorologique" (`PPRN_COMMUNE_ATMOS_APPROUV` / `PPRN_COMMUNE_ATMOS_PRESCRIT`), catégorie qui couvre les vents cycloniques dans les DOM-TOM. À confirmer/affiner avec le BRGM ou en filtrant l'attribut `libelle_risque` du GeoJSON si une version vectorielle est utilisée | polygone |

> `PPR` détaillé par nature de risque (argile, avalanche, cavité, feu, inondation, MVT, séisme, submersion, industriel, volcan) existe couche par couche (`PPRN_ZONE_<TYPE>_FXX` pour le zonage réglementaire fin, `PPRN_COMMUNE_<TYPE>_APPROUV/PRESCRIT` pour le repli à la commune). Le tableau ci-dessus réutilise ces couches directement dans chaque péril plutôt que de dupliquer un calque "PPR" générique par-dessus — seule une entrée de synthèse `PPRN_COMMUNE_GASPAR`/`PPRT_COMMUNE_GASPAR` est gardée pour la vue d'ensemble PPR.

### 2.3 Rapport PDF officiel

- **Endpoint :** `GET https://georisques.gouv.fr/api/v1/rapport_pdf?latlon={lon},{lat}`
- **Réponse :** `Content-Type: application/pdf`, corps binaire direct (vérifié : la requête sur une adresse réelle renvoie bien un PDF multi-pages avec récapitulatif des risques naturels/technologiques, détail par aléa, historique CatNat).
- **Pas de clé requise** (v1 public).
- **Limite connue :** l'endpoint retourne parfois une `404` (`"Les paramètres saisis ne sont pas correct."`) pour des coordonnées ne correspondant à aucune adresse précise reconnue côté Géorisques — comportement rapporté sur le forum data.gouv.fr, cause exacte non documentée par le BRGM. **Le fallback doit donc gérer un 404 proprement**, pas seulement les 5xx.
- Le paramètre attendu est `lon,lat` (longitude puis latitude), et non `lat,lon` — à vérifier avec soin côté implémentation (source d'erreurs silencieuses si inversé, l'endpoint ne renvoie pas toujours une erreur explicite en cas d'inversion selon les retours du forum).

---

## 3. Backend — nouveaux aléas dans `RisqueReport`

### 3.1 `connectors/georisques.py`

1. Ajouter aux `sources` de `fetch_georisques_raw` :
   - `"cavites"` existe déjà (utilisée uniquement pour `mouvement_terrain` actuellement) → créer un aléa `cavite` dédié qui consomme la même donnée avec sa propre normalisation, plutôt que de la fusionner dans `mouvement_terrain`.
   - `"icpe": ("installations_classees", {"code_insee": citycode, "rayon": rayon_m})`
   - `"pprt": ("gaspar/pprt", {"code_insee": citycode})`
2. Nouvelles fonctions de normalisation, sur le modèle de `_alea_feu_foret` / `_alea_mouvement_terrain` :
   - `_alea_cavite(raw)` → `present = len(cavites) > 0`, score basé sur le nombre de cavités recensées.
   - `_alea_avalanche(raw)` → mot-clé `"avalanche"` dans `risques_commune` (déjà collecté, pas de nouvel appel).
   - `_alea_icpe(raw)` → `present = len(icpe) > 0` (+ bonus si un établissement est classé Seveso, champ à vérifier dans la réponse `installations_classees`).
   - `_alea_canalisations(raw)` → mot-clé `"canalisation"` / `"matières dangereuses"` dans `risques_commune` (déjà collecté).
   - `_alea_vent_cyclonique(raw)` → mot-clé `"cyclone"` / `"vent"` dans `risques_commune`, uniquement pertinent pour les codes INSEE des DOM-TOM — prévoir un retour `present=False` explicite (pas d'erreur) en métropole plutôt qu'un aléa "indisponible".
   - `_alea_pprt(raw)` (optionnel, si on veut distinguer PPR naturel / PPR technologique plutôt que le `ppr` fusionné actuel) → mot-clé sur `gaspar/pprt`.
3. Étendre la liste `aleas = [...]` dans `get_risque_report()` avec les nouvelles fonctions.
4. `code` de chaque `AleaDetail` doit correspondre **exactement** aux clés du futur `WMS_LAYER_MAP` frontend (voir §4.2) — c'est la clé de jointure entre backend et carte.

### 3.2 `schemas/risque_report.py`

Aucun changement de structure nécessaire : `AleaDetail` est déjà générique (`code`, `libelle`, `present`, `niveau`, `zonage`, `catnat_historique`, `url_detail`). Les nouveaux aléas s'insèrent sans casser le contrat existant.

### 3.3 Nouvelle route — proxy du rapport PDF officiel

Ajouter dans `api/routes/diagnostic.py` :

```python
@router.get("/diagnostic/adresse/rapport-pdf")
async def rapport_pdf_officiel(
    lat: float = Query(...),
    lon: float = Query(...),
) -> Response:
    """
    Proxy vers l'endpoint officiel Géorisques /api/v1/rapport_pdf.
    Renvoie le PDF binaire tel quel (Content-Type: application/pdf).
    404 si Géorisques ne peut pas générer de rapport pour ces coordonnées
    (adresse non reconnue côté BRGM — comportement connu de la source).
    """
```

Points d'implémentation :
- Appeler `GET https://georisques.gouv.fr/api/v1/rapport_pdf?latlon={lon},{lat}` (attention à l'ordre `lon,lat`).
- `httpx.AsyncClient(timeout=15.0)` (le PDF peut être plus lent à générer qu'un JSON — envisager un timeout dédié plus large, ex. 20–25s, si des 504 sont observés en test).
- Propager le flux binaire avec `Response(content=resp.content, media_type="application/pdf")`.
- Sur `404` de Géorisques → renvoyer un `404` FastAPI avec un détail explicite (`"error": "rapport_pdf_indisponible"`), **pas** un 502, pour que le frontend puisse distinguer "cette adresse n'a pas de rapport officiel" de "Géorisques est en panne".
- Ne **pas** faire dépendre cette route de `get_risque_report()` : elle doit fonctionner indépendamment du RisqueReport interne, en réutilisant seulement `lat`/`lon` déjà obtenus par le géocodage IGN du flux `/diagnostic/adresse`.

Pourquoi proxifier plutôt que de rediriger le frontend directement vers `georisques.gouv.fr` : évite un appel cross-origin depuis le navigateur, garde une seule origine `API` côté frontend (cohérent avec le reste de `zone.html`), et permet de logguer/monitorer les échecs de génération PDF côté backend Typhoon.

---

## 4. Frontend — `zone.html`

### 4.1 Icônes de péril (`ALEA_ICONS`)

Compléter la table existante avec les nouveaux codes :

```js
const ALEA_ICONS = {
  inondation: '🌊',
  rga: '🏗️',
  sismicite: '🌍',
  radon: '☢️',
  feu_foret: '🔥',
  mouvement_terrain: '⛰️',
  ppr: '📜',
  ssp: '🏭',
  cavite: '🕳️',
  avalanche: '🏔️',
  icpe: '🏗️', // à différencier visuellement de rga si collision perçue
  canalisations: '⛽',
  vent_cyclonique: '🌀',
  territoires: '🗺️',
};
```

### 4.2 `WMS_LAYER_MAP` étendu

```js
const WMS_LAYER_MAP = {
  rga:               'ALEARG',                 // À confirmer vs ALEARG_REALISE, cf. §2.2
  inondation:        'LIMITETRI',
  territoires:       'TRI_COMMUNE',
  sismicite:         'SIS_INTENSITE_MAXCOM',    // À confirmer vs risq_zonage_sismique, cf. §2.2
  avalanche:         'PPRN_ZONE_AVALANCHE_FXX',
  cavite:            'CAVITE_LOCALISEE',
  feu_foret:         'PPRN_ZONE_FEU_FXX',
  icpe:              'INSTALLATIONS_CLASSEES_SIMPLIFIE',
  mouvement_terrain: 'MVT_LOCALISE',
  radon:             'RADON',
  canalisations:     'CANALISATIONS',
  ppr:               'PPRN_COMMUNE_GASPAR',
};
```

`WFS_LAYER_MAP` conservé pour `ssp` uniquement (déjà confirmé et fonctionnel) :

```js
const WFS_LAYER_MAP = {
  ssp: ['ms:SSP_CLASSIF_SIS_GE'],
};
```

Avec cette extension, **tous les périls passent en niveau 1 (WMS)** sauf `ssp` (niveau 2, WFS déjà confirmé). Le niveau 3 (cercle de repli) ne devrait plus servir qu'en cas d'échec réseau ponctuel d'une tuile WMS, plus comme stratégie par défaut pour `radon`/`feu_foret` comme c'était le cas avant cette extension.

### 4.3 Remplacer le toggle exclusif par des cases à cocher indépendantes (icône œil)

**Comportement actuel (`buildLayerToggle`) :** un seul péril actif à la fois (`activeLayerKey`), pastilles mutuellement exclusives.

**Comportement cible :** chaque péril présent a son propre état visible/masqué, indépendant des autres — cohérent avec la carte interactive officielle Géorisques qui permet de superposer plusieurs couches.

Changements structurels :

1. Remplacer `let activeLayerKey = 'tous'` par `let visibleLayerKeys = new Set()`, initialisé à l'ensemble de tous les codes d'aléas présents lors de chaque nouveau diagnostic (tout visible par défaut, comme aujourd'hui avec `'tous'`).
2. Remplacer `_olLayers` (tableau plat) par une **map** `_olLayersByKey = new Map()` (clé = code aléa → tableau de couches OL associées, car un péril peut avoir plusieurs couches empilées, ex. `ssp` avec plusieurs sources). Ça permet de basculer la visibilité d'un péril sans reconstruire les autres.
3. `buildLayerToggle(report)` : remplacer les boutons pastille par une liste de lignes, une par péril présent, chacune avec :
   - le libellé + icône (inchangé),
   - un bouton icône œil (`👁️` visible / `🚫` ou `👁️‍🗨️` masqué — privilégier deux icônes SVG inline plutôt que des emojis pour un rendu cohérent cross-plateforme, voir gabarit ci-dessous),
   - au clic : toggle l'entrée correspondante dans `visibleLayerKeys`, applique directement `layer.setVisible(bool)` sur les couches OL déjà chargées dans `_olLayersByKey.get(code)` — **pas besoin de recharger le WMS/WFS**, `ol.layer.Base.setVisible()` suffit et est instantané (pas de nouvel appel réseau).
4. Ajouter un bouton global "Tout afficher / Tout masquer" en tête de liste, pratique avec 13 périls potentiels.
5. `renderAleaLayers(report)` : simplifié — n'a plus besoin de filtrer par `activeLayerKey === 'tous' || activeLayerKey === a.code`, charge toutes les couches de tous les périls présents une seule fois, et applique `layer.setVisible(visibleLayerKeys.has(a.code))` à la construction.

Gabarit CSS/markup suggéré pour la ligne de toggle (à insérer à la place de `.layer-pill-btn`) :

```html
<div class="layer-row">
  <button class="layer-eye-btn" data-visible="true" aria-label="Afficher/masquer Inondation">
    <svg class="icon-eye-open">...</svg>
    <svg class="icon-eye-closed" hidden>...</svg>
  </button>
  <span class="layer-row-label">🌊 Inondation</span>
</div>
```

Icônes œil : réutiliser un set SVG minimal (type Feather/Lucide `eye` / `eye-off`, 16–18px, `stroke="currentColor"` pour hériter de `var(--fog)`/`var(--storm)` du thème sombre existant) plutôt que des emojis, pour cohérence avec le reste du design system D03.

### 4.4 Bouton "Télécharger le rapport PDF officiel"

Dans le bloc résultat (`#results`, à côté du bouton de rapport narratif IA existant s'il y en a un dans le markup, sinon dans `.score-block` ou `.addr-heading`) :

```html
<a id="pdf-report-link" class="btn-secondary" target="_blank" rel="noopener">
  📄 Télécharger le rapport PDF officiel Géorisques
</a>
```

Logique JS, dans `displayReport(r)` après le positionnement de la carte :

```js
const pdfLink = document.getElementById('pdf-report-link');
pdfLink.href = `${API}/diagnostic/adresse/rapport-pdf?lat=${r.lat}&lon=${r.lon}`;
```

Le lien pointe vers le proxy backend (§3.3), pas directement vers `georisques.gouv.fr`, pour rester cohérent avec le reste de l'app et pouvoir gérer un état "indisponible pour cette adresse" côté UI (ex. griser le bouton avec un `fetch HEAD` préalable, ou laisser l'ouverture en nouvel onglet gérer nativement le 404 — à trancher selon UX voulue).

---

## 5. Points à vérifier avant implémentation réelle

- [ ] Confirmer `ALEARG` vs `ALEARG_REALISE` vs `ALEARG_2019` (nom actuellement en prod dans le code) par un `GetCapabilities` direct sur `mapsref.brgm.fr/wxs/georisques/risques` (pas seulement le miroir `georisques_services` utilisé pour cette recherche).
- [ ] Idem pour `SIS_INTENSITE_MAXCOM` vs `risq_zonage_sismique`.
- [ ] Vérifier le format exact de la réponse `installations_classees` (présence d'un champ Seveso exploitable pour la pondération du score `icpe`).
- [ ] Tester `rapport_pdf` sur plusieurs adresses (urbaine dense, rurale isolée, DOM-TOM) pour caractériser les cas de 404 avant de coder le fallback UI.
- [ ] Vérifier si `PPRN_ZONE_<TYPE>_FXX` (zonage fin) répond correctement en dehors de la France métropolitaine (suffixe `_FXX`) — prévoir un repli vers les couches `_GUY` (Guyane) ou la couche commune `PPRN_COMMUNE_<TYPE>_*` pour les DOM-TOM, pertinent notamment pour `vent_cyclonique` et `avalanche`.
- [ ] Trancher la couche exacte pour `vent_cyclonique` (aucune couche WMS dédiée trouvée ; option retenue = PPR "Phénomène météorologique" à confirmer avec le catalogue BRGM ou en contactant le support Géorisques).
