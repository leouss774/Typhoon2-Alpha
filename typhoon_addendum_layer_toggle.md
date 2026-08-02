# ADDENDUM — Toggle de calques par péril (`frontend/jumeau_numerique/zone.html`)

> Complète `typhoon_addendum_endpoints_catnat_report.md` §3.1. Conçu pour s'intégrer directement dans `zone.html` existant : réutilise `D03`, `bandForKey()`, `ALEA_ICONS`, et les variables CSS déjà en place (`--panel`, `--line`, `--storm`, etc.) — aucun nouveau design system, aucune dépendance ajoutée.

---

## 1. Principe

Un péril présent (`present: true`) dans le `RisqueReport` = un calque MapLibre (`circle`) coloré par bande D03, centré sur le point géocodé. Une rangée de pills en haut de la carte permet de basculer entre "Tous les périls" et un péril à la fois — comme le sélecteur d'aléas déjà présent dans la sidebar, mais appliqué à la carte.

**Ce que ça n'est pas (encore)** : pas de vrai polygone de zonage (AZI, TRI) — juste un anneau de gravité autour du point, en attendant de vérifier si Géorisques expose des géométries exploitables (voir addendum précédent §3.2). C'est l'étape à faible coût, pas la version finale.

---

## 2. CSS — à ajouter après le bloc `:root` existant

```css
.layer-toggle {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 5;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  max-width: calc(100% - 32px);
  background: rgba(17,27,23,.92);
  backdrop-filter: blur(6px);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px;
}
.layer-pill-btn {
  background: transparent;
  border: none;
  color: var(--fog);
  font-family: inherit;
  font-size: 12px;
  padding: 6px 11px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}
.layer-pill-btn:hover { background: var(--panel-3); color: var(--paper); }
.layer-pill-btn.active {
  background: var(--storm);
  color: var(--ink);
  font-weight: 600;
}
```

**Attention en copiant** : insérez ce bloc **après** la fermeture du `:root { ... }` existant, pas à l'intérieur — `--storm`, `--panel-3`, `--line`, etc. doivent rester des custom properties globales, pas des règles internes à `.layer-pill-btn`.

---

## 3. HTML — un seul `<div>` à ajouter avant `#map`

```html
<div id="layer-toggle" class="layer-toggle" style="display:none;"></div>
<div id="map"></div>
```
`.map-wrap` a déjà `position: relative` dans le CSS existant — le `position: absolute` du toggle se cale donc naturellement dessus, sans changement de layout.

---

## 4. JavaScript — trois fonctions à ajouter avant `initMap()`

```javascript
/* ── Layer toggle (calques par péril) ── */
let activeLayerKey = 'tous'; // 'tous' | code d'un péril présent

function buildLayerToggle(report) {
  const container = document.getElementById('layer-toggle');
  if (!container) return;
  container.innerHTML = '';

  const aleasPresents = (report.aleas || []).filter(a => a.present === true);
  if (!aleasPresents.length) { container.style.display = 'none'; return; }
  container.style.display = 'flex';

  const makeBtn = (key, label) => {
    const btn = document.createElement('button');
    btn.className = 'layer-pill-btn' + (key === activeLayerKey ? ' active' : '');
    btn.textContent = label;
    btn.onclick = () => {
      activeLayerKey = key;
      container.querySelectorAll('.layer-pill-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderAleaLayers(report);
    };
    return btn;
  };

  container.appendChild(makeBtn('tous', 'Tous les périls'));
  aleasPresents.forEach(a => {
    const icon = ALEA_ICONS[a.code] || '•';
    container.appendChild(makeBtn(a.code, `${icon} ${a.libelle}`));
  });
}

function renderAleaLayers(report) {
  if (!map || !map.getSource) return;
  const aleasPresents = (report.aleas || []).filter(a => a.present === true && a.niveau);

  // Nettoyage des calques précédents avant de redessiner
  aleasPresents.forEach(a => {
    const id = `alea-layer-${a.code}`;
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
  });

  const lon = report.lon, lat = report.lat;
  aleasPresents
    .filter(a => activeLayerKey === 'tous' || activeLayerKey === a.code)
    .forEach(a => {
      const id = `alea-layer-${a.code}`;
      const band = bandForKey(a.niveau) || {};
      const geojson = {
        type: 'Feature',
        properties: { code: a.code, niveau: a.niveau },
        geometry: { type: 'Point', coordinates: [lon, lat] },
      };
      map.addSource(id, { type: 'geojson', data: geojson });
      map.addLayer({
        id,
        type: 'circle',
        source: id,
        paint: {
          'circle-radius': 46,
          'circle-color': band.color || '#7A9187',
          'circle-opacity': activeLayerKey === 'tous' ? 0.22 : 0.38,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': band.color || '#7A9187',
          'circle-stroke-opacity': 0.9,
        },
      });
    });
}
```

**Réutilisation intentionnelle** : `bandForKey()` et `ALEA_ICONS` existent déjà dans `zone.html` (lignes ~342-360 au moment de l'audit) — ce code ne les redéfinit pas, il s'appuie sur eux. Si leur nom a changé depuis, adapter les deux appels en conséquence.

---

## 5. Branchement dans `placePin(lat, lon, report)`

Ajouter à la fin de la fonction existante, juste après le `map.flyTo(...)` :

```javascript
  // Calques par péril : reset sur "Tous les périls" à chaque nouveau rapport
  activeLayerKey = 'tous';
  buildLayerToggle(report);
  if (map.isStyleLoaded()) {
    renderAleaLayers(report);
  } else {
    map.once('idle', () => renderAleaLayers(report));
  }
}
```

**Pourquoi le `isStyleLoaded()`/`once('idle')`** : `addSource`/`addLayer` échouent silencieusement (ou lèvent une erreur console) si le style du fond de carte n'a pas fini de charger — utile surtout au tout premier rapport affiché après le chargement de la page, où la carte peut ne pas être encore prête au moment où `placePin` est appelé.

---

## 6. Comportement attendu

- Aucun péril présent (`present: false` partout) → le toggle reste caché (`display:none`), pas de pills vides affichées.
- "Tous les périls" (état par défaut à chaque nouveau rapport) → tous les calques visibles en même temps, opacité réduite (0.22) pour rester lisible en superposition.
- Un péril sélectionné → seul ce calque affiché, opacité renforcée (0.38) pour le mettre en évidence.
- Nouveau rapport chargé → le toggle est reconstruit à partir de zéro (couleurs/labels toujours synchronisés avec le rapport affiché), et revient sur "Tous les périls" par défaut.

---

## 7. Limites actuelles, honnêtes

- **Rayon fixe (46px), pas une vraie emprise géographique** — un péril "élevé" sur une petite parcelle et un péril "élevé" à l'échelle communale s'affichent avec le même cercle. Acceptable pour une V1 visuelle, pas pour une lecture cartographique précise.
- **Un seul point par péril** — si vous passez au mode zone (grille de points), ce composant ne change pas de nature mais devra être appelé une fois par point de la grille plutôt qu'une fois pour l'adresse unique ; prévoir la performance (nombreux calques MapLibre) avant de réutiliser tel quel à cette échelle.
