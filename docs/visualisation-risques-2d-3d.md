# Visualisation des risques 2D & 3D — état des lieux & propositions

> Document de conception — Typhoon, carte unifiée Mapbox (`frontend/src/components/UnifiedMap.tsx`).
> Objectif : rendre la lecture des risques plus lisible, plus parlante et plus actionnable,
> en 2D comme en 3D, sans sacrifier la mise en avant du bâtiment diagnostiqué.

---

## 1. Contexte

Le diagnostic produit un `RisqueReport` (backend `app/connectors/georisques.py`) qui contient
aujourd'hui **5 périls conservés** :

| code | libellé | donnée géométrique dispo |
|---|---|---|
| `icpe` | Installations industrielles (ICPE) | WMS raster `INSTALLATIONS_CLASSEES_SIMPLIFIE` (BRGM) |
| `canalisations` | Réseaux et canalisations | WMS raster `CANALISATIONS` + **WFS lignes** (`ms:C_GAZ`, `ms:C_HYDROCARBURES`, `ms:C_PRODUITS_CHIM`) |
| `vent_cyclonique` | Vents cycloniques | aucun (fallback cercle au point) |
| `ppr` | Plans de Prévention des Risques | WMS raster `PPRN_COMMUNE_GASPAR` + **WFS périmètres** (`ms:PPRN_PERIMETRE_*`, `ms:PPRN_COMMUNE_*`) |
| `ssp` | Sites et sols pollués (SIS) | **WFS points** (`ms:SSP_CLASSIF_SIS_GE`) |

Chaque aléa porte aussi un `niveau` D03 (`tres_faible` → `critique`) mappé sur les bandes
`D03` de `frontend/src/zone/config.ts` (couleur + libellé + classe).

Le bâtiment diagnostiqué vient de la BDNB (`report.bdnb.batiment`), avec en particulier
`geom_groupe` (empreinte), `hauteur_mean`, et les champs de risque bâtiment
(`alea_argile`, `alea_radon`, `alea_sismique` via la table `batiment_groupe_risques`).

---

## 2. État actuel du rendu (UnifiedMap.tsx)

Ce qui est dessiné aujourd'hui, étape « Cartographie » (`showRisks=true`) :

1. **Bâtiments 3D BDNB** (`mb-buildings-3d`, extrusion par `hauteur_mean`), filtre resserré
   sur le bâtiment cible quand on passe en 3D (le reste de la ville est rendu par les
   bâtiments natifs Mapbox Standard).
2. **Surlignage du bâtiment cible** : extrusion 3D en couleur `--accent`, empreinte 2D
   teintée accent (`mb-buildings-2d-highlight`) + épingle `bldg-pin`.
3. **Couches de risque par aléa** (`renderReport`) :
   - WMS raster BRGM (`alea-<code>`, type `raster`, `raster-opacity: 0.65`) pour les
     périls qui ont une couche dans `WMS_LAYER_MAP` ;
   - WFS vecteur (`fetchWfsLayer`, type `fill`) pour les périls de `WFS_LAYER_MAP` ;
   - sinon **cercle fallback** au point de l'adresse (`alea-<code>`, type `circle`).
4. **Popup adresse** avec les aléas présents + liens IGN/OSM.
5. **Panneau latéral** : bandes D03, score global, cartes aléas (toggle de visibilité
   par couche via `visibleLayerKeys`).

### 2.1 Constats & faiblesses

- **Le WFS Géorisques ne sert pas du JSON.** Vérifié en direct : le service
  `https://www.georisques.gouv.fr/services` n'accepte que
  `application/gml+xml; version=3.2` et `text/xml; subtype=gml/3.2.1`.
  Or `fetchWfsLayer` (frontend/src/zone/mapHelpers.ts) demande `outputFormat=application/json`
  → la requête échoue, l'exception est avalée (`catch { /* */ }`), et **SSP retombe
  toujours sur le cercle fallback**. C'est un bug latent à corriger en premier.
- **Les rasters WMS ne sont pas re-stylables** : couleur, opacité et légende imposées
  par BRGM ; pas de hover, pas de filtre par niveau D03, pas d'extrusion en 3D.
- **Le niveau D03 n'est pas utilisé dans le rendu** : la couleur des polygones WFS est
  `color + '55'` (couleur de bande du `niveau`, mais à plat, sans hiérarchie visuelle
  claire entre aléas).
- **Le cercle fallback est trompeur** : il pointe l'adresse, pas la zone réelle du risque.
- **Rien n'est interactif sur la carte** (pas de survol, pas de tooltip sur les zones).
- **En 3D, les zones de risque sont plates** : elles flottent sur le sol, sans relief,
  alors que c'est justement la vue où on attend une lecture en volume.
- **Le risque bâtiment (BDNB) n'est pas cartographié** : on a les champs argile/radon/
  sismique dans la fiche, mais rien sur la carte (seulement le surlignage accent).

---

## 3. Principes de design

1. **Une couleur = un niveau D03.** Toutes les couches de risque (zones, bâtiments,
   cercles, jauges) utilisent la palette `D03` existante — c'est la référence déjà
   comprise par l'utilisateur (légende du panneau).
2. **L'aléa se lit par le symbole, pas par la couleur.** Icônes Material (`ALEA_ICONS`)
   et libellés restent le canal « quel risque ? » ; la couleur D03 dit « à quel point ? ».
3. **Le bâtiment cible reste le héros.** Aucune couche de risque ne doit masquer le
   surlignage accent ; en cas de doute, on passe les zones de risque sous le bâtiment
   (ordre des couches) et on garde un contour/épingle visible.
4. **Le vecteur prime sur le raster** dès que la donnée existe (hover, styling, 3D).
   Le raster reste en repli de secours.
5. **Lisible en mode jour ET crépuscule** : opacités et contours pensés pour les deux
   presets `lightPreset` (`day`/`dusk`) — un contour sombre améliore le contraste sur
   les fonds clairs.
6. **Performances** : découpage par `code_insee` (déjà fait), simplification des
   géométries, chargement différé par viewport, et nombre de couches borné.

---

## 4. Propositions — vue 2D

### P1. Corriger le WFS et passer les périls vecteur en vrai vecteur

**But** : SSP, PPR et canalisations en GeoJSON réel, stylables, au lieu du raster/cercle.

- Corriger `fetchWfsLayer` : demander `outputFormat=text/xml; subtype=gml/3.2.1`
  (ou `application/gml+xml; version=3.2`) puis convertir GML→GeoJSON côté client
  (parser minimal dédié : `gml:Polygon` / `gml:MultiSurface` / `gml:Point` avec
  `srsName="EPSG:4326"` ou reprojection). La conversion est à garder volontairement
  simple : on ne lit que les géométries + 2-3 attributs utiles.
- Enrichir `WFS_LAYER_MAP` dans `frontend/src/zone/config.ts` :
  ```ts
  ssp: ['ms:SSP_CLASSIF_SIS_GE'],
  ppr: ['ms:PPRN_PERIMETRE_INOND', 'ms:PPRN_PERIMETRE_MVT', 'ms:PPRN_PERIMETRE_SUBMAR'],
  canalisations: ['ms:C_GAZ', 'ms:C_HYDROCARBURES', 'ms:C_PRODUITS_CHIM'],
  ```
  (noms vérifiés dans les capabilities du service, à re-confirmer par péril)
- Fallback WMS raster conservé tant que le vecteur n'est pas disponible pour un péril.

**Fichiers** : `frontend/src/zone/mapHelpers.ts`, `frontend/src/zone/config.ts`,
`frontend/src/components/UnifiedMap.tsx`.

### P2. Colorier par niveau D03 + contours lisibles

**But** : la hiérarchie de risque se lit d'un coup d'œil.

- Remplacer `'fill-color': color + '55'` par un `'fill-color'` par bande D03
  (`match` sur le niveau de la feature, clé `niveau`/`alea_niveau` injectée au fetch),
  `'fill-opacity': 0.5`, `'fill-outline-color': '#263238'` (ou couleur de bande assombrie)
  avec `'line-opacity': 0.6`.
- Même logique pour les cercles fallback : `circle-color` = couleur de bande, contour
  plus épais selon le niveau (3px en `critique`, 1px sinon).

### P3. Couches ponctuelles ICPE/SSP avec halos de distance

**But** : montrer *où* et *à quelle distance* on est exposé, pas seulement « il y en a ».

- ICPE : passer en vecteur WMS `GetFeature` (ou GeoJSON via l'API Géorisques
  `installations_classees`) pour afficher les **points** avec un symbole par statut
  (Seveso = losange/étoile rouge, les autres = cercle gris) + **rayon de distance**
  (ex. 500 m autour des sites Seveso) dessiné en `fill` translucide.
- SSP : points SIS avec **pastille colorée** selon la classification (SIS → S1/S2/S3)
  et un rayon d'attention (ex. 300 m).
- Les rayons utilisent `turf.buffer` (déjà dans les deps ? sinon petit buffer maison
  en WGS84 — l'empreinte est petite, une approximation à 5 % est acceptable) ou des
  cercles `fill` simples.

### P4. Légende + compteur de couches directement sur la carte

**But** : l'utilisateur comprend la carte sans ouvrir le panneau.

- Ajouter un bloc « légende » en bas à gauche (`mb-demo-tools` / zone existante) :
  uniquement les bandes D03 présentes sur les couches actives, avec pastilles colorées.
- Badge « n couches actives » synchronisé avec `visibleLayerKeys` (déjà remonté depuis
  `Zone.tsx`).

### P5. Carte « risque bâtiment » (BDNB) en 2D

**But** : passer de « la commune est exposée » à « **ce bâtiment** est exposé ».

- Nouveau mode de carte (bascule dans la barre d'outils) : « Risques bâtiment ».
  On colore l'empreinte du bâtiment cible (et éventuellement les bâtiments voisins du
  même `batiment_groupe_id` dans la source `mb-bdnb-buildings`) selon les champs BDNB :
  `alea_argile`, `alea_radon`, `alea_sismique` → couleur D03.
- Trois pastilles de réglage ou une petite légende dédiée (argile / radon / sismique)
  dans le panneau.
- Réutilise `BUILDINGS_SOURCE` : aucun fetch supplémentaire.

---

## 5. Propositions — vue 3D

### P6. Extruder les zones de risque (fill-extrusion)

**But** : en 3D, les zones de risque deviennent des volumes qu'on survole.

- Pour chaque péril vecteur (PPR, canalisations, SSP), ajouter une couche
  `fill-extrusion` au-dessus du sol :
  ```js
  'fill-extrusion-height': ['match', ['get', 'niveau'],
    'critique', 14, 'eleve', 10, 'modere', 6, 'faible', 3, 'tres_faible', 1.5, 1],
  'fill-extrusion-color': <couleur D03>,
  'fill-extrusion-opacity': 0.55,
  'fill-extrusion-vertical-gradient': false,   // homogène, lisible
  ```
- La hauteur code le niveau D03 (échelle logarithmique douce) → la carte « se soulève »
  là où le risque est fort. Plafonner à ~14 m pour rester lisible face aux bâtiments.
- En 2D, on bascule automatiquement ces couches en `fill` plat (même source, deux
  couches de rendu selon `is3d`, comme fait pour `mb-buildings-3d` / `mb-buildings-2d-highlight`).

### P7. Volumes ICPE & SSP (cylindres / pastilles 3D)

**But** : les sites industriels et pollués restent identifiables sous forte inclinaison.

- Couche `fill-extrusion` circulaire (petite empreinte ronde) ou `symbol` avec icône
  flottante au-dessus du point ; hauteur fixe (ex. 8 m), couleur par statut
  (Seveso = rouge D03 critique, ICPE simple = bande modérée, SIS = violet).
- Étiquette (`symbol` avec `text-field`) affichée à partir de zoom 15 : nom du site /
  statut. Éviter les collisions (`symbol-avoid-edges`).

### P8. Colorier les bâtiments par risque BDNB en 3D

**But** : la 3D devient une « carte de chaleur » du bâti.

- Quand le mode « Risques bâtiment » (P5) est actif, remplacer la rampe de hauteur
  (`buildingColorExpr`) par un `case` sur les champs BDNB des features de
  `mb-bdnb-buildings` : argile/radon/sismique → couleur D03 (max des trois pour un
  bâtiment donné).
- En 3D, la ville est rendue par les bâtiments natifs Mapbox — appliquer le coloriage
  au bâtiment cible + voisins BDNB chargés, et garder les natifs neutres pour le
  contraste.

### P9. Renforcer le surlignage du bâtiment cible

**But** : le héros doit rester identifiable même avec des volumes de risque autour.

- **Contour lumineux** : couche `line` au-dessus de l'extrusion (existe déjà en 3D,
  `mb-buildings-outline`) — l'étendre en 2D quand le mode risque bâtiment est actif.
- **Étiquette flottante** (id BDNB court, ex. `BG-8ABJ-68B4-J143` tronqué) à zoom ≥ 15.
- **Jauge verticale** optionnelle : petit barreau à côté de l'édifice codant le score
  global D03 (max des aléas présents), via une mini-extrusion ou un `symbol`.

### P10. (Option, plus tard) Animation « lame d'eau » / exposition

**But** : pédagogie sur le risque inondation (nécessite de réintégrer l'aléa inondation
dans le rapport — retiré précédemment).

- Animer une surface `fill-extrusion` translucide montant le long de la façade du
  bâtiment cible (hauteur selon le niveau D03), avec un bouton play/pause dans la barre
  d'outils. S'appuie sur `requestAnimationFrame` + `setPaintProperty` (cheap).

---

## 6. Plan d'implémentation recommandé

| Phase | Contenu | Fichiers | Effort estimé |
|---|---|---|---|
| **0** | Corriger `fetchWfsLayer` (GML→GeoJSON) + activer SSP vecteur | `mapHelpers.ts`, `config.ts` | 0,5 j |
| **1** | Coloriage D03 + contours + hover/tooltip sur les couches vecteur | `UnifiedMap.tsx` | 1 j |
| **2** | Légende + compteur de couches sur la carte | `UnifiedMap.tsx`, `zone.css` | 0,5 j |
| **3** | PPR & canalisations en WFS vecteur (+ rayons SSP/ICPE) | `config.ts`, `mapHelpers.ts`, `UnifiedMap.tsx` | 1,5 j |
| **4** | Mode « Risques bâtiment » (2D puis 3D) | `UnifiedMap.tsx`, `Zone.tsx` (bascule), `zone.css` | 1,5 j |
| **5** | Extrusion 3D des zones (P6) + volumes ICPE/SSP (P7) + étiquette cible (P9) | `UnifiedMap.tsx` | 2 j |
| **6** | (Option) animation lame d'eau | `UnifiedMap.tsx`, backend (réintégration inondation) | 2-3 j |

L'ordre est choisi pour livrer de la valeur rapidement (phases 0-2 = gros gain visuel
sans backend) et garder les risques techniques (GML, perf 3D) en début de course.

---

## 7. Risques & points de vigilance

- **WFS Géorisques = GML uniquement** : le parser GML est le point technique le plus
  risqué (variantes `gml:MultiSurface`, `gml:Polygon`, crs). Mitigation : parser
  minimaliste + tests unitaires sur des fixtures ; le raster reste le fallback.
- **Volume des géométries PPR** : certains périmètres sont lourds → `count` borné,
  filtre par `code_insee` (déjà en place), et éventuellement simplification
  (`turf.simplify` si dispo, sinon rejet des géométries > N points).
- **Ordre des couches** : les zones de risque doivent passer *sous* les bâtiments
  extrudés pour ne pas masquer le surlignage → insérer les couches avec `before:`
  (id de la couche `mb-buildings-3d` ou `mb-native-buildings`).
- **Cohérence 2D/3D** : chaque péril doit avoir exactement deux couches de rendu
  (fill / fill-extrusion) basculées par `toggle3D`, sinon l'utilisateur voit des
  différences entre les vues.
- **Perf en 3D** : `fill-extrusion` sur de gros polygones peut faire chuter le FPS —
  surveiller avec `map.on('render')` / DevTools, réduire l'opacité et la hauteur max
  si besoin.
- **Le cercle fallback doit rester honnête** : il marque « présence communale » —
  le libellé du tooltip doit le dire clairement pour ne pas sous-entendre que la zone
  exacte est couverte.
- **Accessibilité** : tooltips au survol doublés d'un clic (focus) ; `aria-label` sur
  la bascule de mode risque bâtiment ; contraste D03 vérifié sur fond clair et crépuscule.

---

## 8. Définition de « fait » (DoD) pour une phase

- La couche correspondante est visible en 2D **et** en 3D, bascule proprement via le
  bouton 3D existant ;
- Les couleurs utilisent les bandes D03 existantes (`bandForKey`) ;
- Le bâtiment cible reste surligné au-dessus de toutes les couches de risque ;
- `npx tsc -b --force` passe, aucun warning console nouveau ;
- Vérification manuelle sur une adresse réelle (ex. 14 Avenue des Palmiers 06000 Nice)
  en modes jour + crépuscule.
