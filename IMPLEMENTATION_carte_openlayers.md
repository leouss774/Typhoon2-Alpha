# Implémentation — Migration carte `zone.html` vers OpenLayers + couches WMS réelles

**Fichier concerné :** `frontend/jumeau_numerique/zone.html`
**Branche cible :** `feature/restructure`
**Fichier prêt à copier :** `zone.html` (fourni séparément dans la conversation)

## Contexte

`zone.html` affichait déjà un diagnostic géo-risque par adresse sur une carte MapLibre GL, avec des couches de péril en WFS 2.0 (`georisques.gouv.fr/services`). Deux problèmes identifiés :

1. **Bibliothèque cartographique** : MapLibre GL au lieu d'OpenLayers (utilisé par la carte interactive officielle Géorisques).
2. **Couches inexactes** :
   - `rga` pointait vers `ms:ALEARG_REALISE`, un typename WFS non confirmé.
   - `sismicite` pointait vers `ms:risq_zonage_sismique` en WFS, non confirmé non plus.
   - `inondation` n'avait **aucune couche connue** → repli systématique sur un simple cercle au lieu du vrai polygone de zone inondable.

Le scratchpad de reconnaissance réseau sur `agdvp.brgm.fr/#/context/georisques_global` (carte officielle) a confirmé trois couches WMS réelles, servies par `mapsref.brgm.fr/wxs/georisques/risques` (WMS 1.3.0) :

| Péril | Layer WMS confirmé |
|---|---|
| Argiles / RGA (millésime 2020) | `ALEARG_2019` |
| Inondation (TRI) | `LIMITETRI` |
| Séismes (zonage sismique) | `risq_zonage_sismique` |

## Résumé des changements

| Zone du fichier | Avant | Après |
|---|---|---|
| `<head>` | `maplibre-gl@4.7.1` (JS + CSS) | `ol@9.2.4` (JS + CSS), via jsDelivr |
| Fond de carte | Style MapLibre `raster` sur tuiles CARTO dark | `ol.layer.Tile` + `ol.source.XYZ` sur les mêmes tuiles CARTO dark |
| Marqueur adresse | `maplibregl.Marker` (élément DOM `.map-pin`) | `ol.Overlay` sur le même élément `.map-pin`, repositionné via `setPosition` |
| Popup adresse | `maplibregl.Popup` | `ol.Overlay` sur une div `#ol-popup`, avec bouton de fermeture custom |
| Contrôles carte | `NavigationControl`, `ScaleControl` | `ol.control.defaultControls` + `ol.control.ScaleLine`, restylés en CSS pour garder le thème sombre |
| Couches péril | `map.addSource`/`addLayer` GeoJSON (WFS) + cercle de repli | 3 niveaux : WMS raster confirmé → WFS vecteur confirmé → cercle de repli |
| Nettoyage des couches | Listes d'IDs `_wfsSourceIds` / `_wfsLayerIds` + `removeLayer`/`removeSource` par ID | Liste d'instances `_olLayers` + `map.removeLayer(layer)` directement |
| `flyTo` / resize | `map.flyTo(...)`, listener `resize` → `map.resize()` | `view.animate(...)`, pas de listener nécessaire (OL gère le redimensionnement automatiquement) |

## Étapes d'implémentation

### 1. Remplacer les imports MapLibre par OpenLayers

```html
<!-- Avant -->
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />

<!-- Après -->
<script src="https://cdn.jsdelivr.net/npm/ol@9.2.4/dist/ol.js"></script>
<link href="https://cdn.jsdelivr.net/npm/ol@9.2.4/ol.css" rel="stylesheet" />
```

### 2. CSS — popup, marqueur, contrôles

- Remplacer les règles `.maplibregl-popup-*` par un bloc `#ol-popup` (positionnement absolu géré manuellement, `transform: translate(-50%, -100%)` pour ancrer la pointe en bas).
- Ajouter `transform: translate(-50%, -50%)` à `.map-pin` puisque l'`ol.Overlay` positionne son élément par le coin haut-gauche par défaut.
- Ajouter des overrides `.ol-zoom`, `.ol-scale-line` pour garder le thème sombre existant (les contrôles OL par défaut sont stylés clairs).

### 3. Markup — ajouter les conteneurs d'overlay

Dans `<main class="map-wrap">`, à côté de `#map` :

```html
<div class="map-pin" id="map-pin" style="position:absolute;"></div>
<div id="ol-popup"></div>
```

### 4. `initMap()` — recréer la carte en OpenLayers

- Fond de carte : `ol.layer.Tile` + `ol.source.XYZ` sur `https://{a-b}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`.
- Deux `ol.Overlay` créés une seule fois à l'init (`markerOverlay`, `popupOverlay`), réutilisés à chaque nouveau diagnostic via `setPosition`.
- `view` centrée sur `ol.proj.fromLonLat([2.35, 46.8])`, zoom 5 (identique à l'existant).

### 5. Couches de péril — nouvelle logique à 3 niveaux (`renderAleaLayers`)

Pour chaque aléa présent dans le rapport :

1. **WMS confirmé** (`WMS_LAYER_MAP`) → `ol.layer.Tile` + `ol.source.TileWMS` pointant vers `https://mapsref.brgm.fr/wxs/georisques/risques`. Utilisé pour `rga`, `inondation`, `sismicite`.
2. **Sinon, WFS confirmé** (`WFS_LAYER_MAP`) → fetch GeoJSON sur `georisques.gouv.fr/services`, parsé avec `ol.format.GeoJSON` (`dataProjection: 'EPSG:4326'`, `featureProjection: 'EPSG:3857'`), rendu en `ol.layer.Vector`. Toujours utilisé pour `mouvement_terrain`, `ppr`, `ssp`.
3. **Sinon, cercle de repli** → `ol.layer.Vector` avec un unique point stylé en `ol.style.Circle` (rayon 46 px), pour `radon`, `feu_foret`, ou toute couche WFS ayant renvoyé une réponse vide.

Chaque couche ajoutée est poussée dans `_olLayers` via `_trackLayer(layer)`, qui appelle aussi `map.addLayer(layer)`. Le nettoyage entre deux diagnostics (`_cleanAllLayers()`) itère simplement `_olLayers` et appelle `map.removeLayer(layer)`.

### 6. `placePin()` — repositionner marqueur/popup et déclencher le rendu des couches

```js
const coord = ol.proj.fromLonLat([lon, lat]);
markerOverlay.setPosition(coord);
popupOverlay.setPosition(coord);
map.getView().animate({ center: coord, zoom: 14, duration: 1200 });

activeLayerKey = 'tous';
_cleanAllLayers();
buildLayerToggle(report);
renderAleaLayers(report);
```

Contrairement à la version MapLibre, pas besoin d'attendre un événement `idle`/`load` : OpenLayers accepte `addLayer` immédiatement après l'init de la carte.

### 7. Nettoyage final

Supprimer le listener `window.addEventListener('resize', () => map.resize())` — OpenLayers observe le redimensionnement de son conteneur automatiquement (`ResizeObserver` interne), ce code devient mort.

## Vérification avant merge

- [ ] Rechercher `maplibregl` dans le fichier final → aucune occurrence.
- [ ] Charger `zone.html` en local avec le backend (`API` pointant vers `http://127.0.0.1:8765` ou équivalent) et diagnostiquer une adresse réelle.
- [ ] Vérifier que la couche RGA (`ALEARG_2019`) s'affiche bien en zone argileuse connue (ex. adresse en région parisienne).
- [ ] Vérifier que la couche inondation (`LIMITETRI`) affiche un vrai polygone (et non plus un cercle) sur une adresse en zone inondable connue (ex. bord de Loire, bord de Rhône).
- [ ] Basculer les pastilles de calque (`Tous les périls` / par péril) et confirmer que `_cleanAllLayers()` retire bien les anciennes couches avant d'ajouter les nouvelles (pas de superposition résiduelle).
- [ ] Vérifier visuellement le popup (fermeture via le bouton `×`, positionnement au-dessus du marqueur).

## Limites connues / suivi

- Les couches WMS BRGM ne sont pas découpées à la commune : elles couvrent toute la tuile visible, comme sur la carte officielle. L'opacité a été réduite en conséquence (`fillOpacity + 0.35` au lieu d'une superposition pleine).
- `radon` et `feu_foret` n'ont toujours pas de couche polygonale connue publiquement — cercle de repli conservé.
- Les typenames WFS pour `mouvement_terrain`, `ppr`, `ssp` n'ont pas été re-vérifiés dans ce lot ; ils étaient déjà marqués comme confirmés dans le code existant.
