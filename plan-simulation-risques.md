# Plan — Jumeau BIM & simulations de catastrophes naturelles (étapes 4+)

> **État du plan : mis à jour août 2026.** Ce document planifie les **étapes restantes**
> du parcours — le jumeau BIM (étape 4) et les simulations de catastrophes naturelles —
> et liste les frameworks / repos GitHub utilisables par type d'aléa, **licence vérifiée**
> (contrainte produit commercial : pas d'AGPL/GPL dans le code applicatif, pas de
> licence « research only » en prod).
>
> ⚠️ Changement depuis la version précédente : la nappe d'eau threebox sur la carte
> Mapbox a été **retirée** (décision produit). Les simulations vivent donc **dans le
> jumeau BIM** (échelle actif) ; la carte apporte la perception à l'échelle quartier.

---

## 1. Où on en est — état réel

| Étape | Endroit | Déjà en place | Moteur | Statut |
|---|---|---|---|---|
| **1–2 Cartographie / Analyse** | Carte Mapbox 3D | Bâtiments BDNB extrudés (hauteurs réelles), couches risques BRGM WMS/WFS, parcelles IGN (toggle Analyse), fond sombre 2D CARTO / 3D Mapbox Dark | Mapbox GL JS (v2.15) | ✅ |
| **3 Analyse** | Panneau fiche BDNB | Fiche enrichie (enveloppe, systèmes, DPE, risques) type GoRénove — sources 100 % gratuites (BDNB, DPE ADEME, Géorisques) | API BDNB | ✅ |
| **4 Jumeau BIM** | iframe `thingraph/bim-viewer` (**MIT**) | Simulations **inondation / feu / séisme** pilotées par les niveaux Géorisques réels (`postMessage typhon:sim`), débris physiques | three.js + `@dimforge/rapier3d-compat` (Apache-2.0) | ✅ embryon solide |
| **5 Recommandations** | RAG Mistral | Rapport détaillé par aléa | LLM | ✅ |
| **—** | — | **Modèles IFC réels** (vrai BIM client), **moteurs numériques** (hydraulique/sismique/feu), **propagation à l'échelle quartier**, boucle **quartier ↔ actif** | — | ❌ à faire |

**Ce qui est déjà vrai et qu'on garde** : l'intensité des simulations du jumeau suit les
niveaux **D03 réels** calculés par le backend (`report.aleas[*].niveau`) — aucune donnée
inventée. Principe fondateur conservé : les effets sont **dérivés des niveaux réels**,
pédagogiques, jamais présentés comme une étude d'ingénierie (disclaimer déjà en place).

---

## 2. Architecture cible — une seule voie

```
┌────────── ÉCHELLE QUARTIER (carte Mapbox 3D) — perception ──────────┐
│  La catastrophe se propage visiblement sur le bâti réel (BDNB)      │
│  · Feu    : propagation + fumée/braises sur les volumes 3D          │
│  · Vent   : particules (webgl-wind) — le produit s'appelle Typhoon  │
│  · Séisme : secousse caméra + paliers de dégâts colorés             │
│  · Eau    : (facultatif, plus tard) polygones PPR animés            │
│  ─ clic sur un bâtiment sinistré → ouvre le jumeau, MÊME intensité ─│
└─────────────────────────────────────────────────────────────────────┘
                              │  passe le niveau D03 de l'aléa (typhon:sim)
                              ▼
┌─────────────── ÉCHELLE ACTIF (jumeau BIM, étape 4) — compréhension ───────────────┐
│  Que se passe-t-il DANS le bâtiment ?                                              │
│  · Inondation : montée d'eau par niveau (existe)                                   │
│  · Feu        : propagation étage par étage + fumée (existe, à enrichir)           │
│  · Séisme     : secousse + débris physiques rapier (existe)                        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Règle d'architecture (à respecter dès le départ) :
1. **Moteurs numériques lourds = backend** (OpenQuake, CLIMADA, Cell2Fire…) → produisent
   des **frames/états** (GeoJSON, grilles temporelles). Jamais dans le navigateur.
2. **Rendu = frontend** (Mapbox, three.js, le bim-viewer) → anime ces frames.
3. En l'absence de moteur (aujourd'hui), les effets sont **dérivés des niveaux D03** —
   simulation *visuelle pédagogique*, avec le disclaimer partout.

---

## 3. Repos GitHub par aléa — licences vérifiées

### 3.1 Inondation

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`uihilab/Hydro3DJS`** (Univ. Iowa) | MIT | Lib 3D hydrologique : `addWater(geojson)`, `addRain(geojson)`, shaders eau/pluie, modèles glTF. **Dépend de Google Maps** → ne brancher jamais tel quel ; **porter uniquement les shaders** dans three.js/Mapbox. | Actif + quartier |
| **`aeplay/WebFlood`** | démo de thèse | Shallow-water résolu **sur GPU (GLSL)** dans le navigateur (inondation urbaine Iowa City, depuis un MNT). Preuve de concept pour un futur moteur hydraulique client léger — à réécrire proprement si on y va. | Quartier (plus tard) |
| **`jeantimex/threejs-water`** | MIT | Eau three.js temps réel : réflexions/refractions, caustiques — idéal pour **améliorer le rendu de l'eau dans le jumeau BIM** (l'inondation existe déjà, elle est plate). | Actif |
| **`MollyLovses/OSM-3D-Viewer`** | MIT | « Advanced water shaders » pour Mapbox/threebox — source directe d'amélioration si on remet de l'eau sur la carte. | Quartier (facultatif) |
| *Backend réel* | — | HEC-RAS / Telemac-Mascaret : open source **mais hors GitHub** (USACE/EDF). Pour la démo : zones inondables **PPR/AZI Géorisques** déjà dans le rapport + rendu visuel. | Backend (plus tard) |

### 3.2 Feu de forêt

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`cell2fire/Cell2Fire`** (fork maintenu **`C2FK`**) | **« For Research Use Only »** — pas de prod commerciale sans accord | Le meilleur moteur réel open de croissance de feu (cellules elliptiques, C++/Python, sort des grilles de propagation temporelles). **À garder en backend si un client le finance.** | Backend / quartier |
| **`PavelDoGreat/WebGL-Fluid-Simulation`** | MIT | Fluide WebGL2 — parfait pour **fumée / braises** dans le jumeau BIM (le feu y existe déjà, sans fumée). Effet très lisible en démo. | Actif + quartier |
| *Visuel custom* | — | Propagation de feu sur les volumes 3D : « enflammer » les bâtiments voisins par **automate cellulaire simple** (~100 lignes), niveau = D03 feu de forêt. Option démo recommandée. | Quartier |

### 3.3 Séisme

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`gem/oq-engine`** (OpenQuake, GEM) | **AGPL-3.0** — OK en **service backend isolé**, contaminant si lié au code applicatif | La référence mondiale en **aléa/risque sismique probabiliste** : courbes d'aléa, sets d'événements stochastiques, PGA/SA par site → intensité de secousse réaliste. | Backend |
| **`gem/oq-mbtk`** (Model Building Toolkit) | AGPL-3.0 | Construit les modèles d'exposition/vulnérabilité par type de bâtiment — utile pour cartographier la vulnérabilité du parc BDNB. | Backend |
| *Visuel custom* | — | Secousse caméra (easing sinusoïdal amorti) + **états de dégâts** par bâtiment (4 paliers : intact → effondré) colorés sur les volumes 3D. Le jumeau a déjà la version « dans le bâtiment » (shake + débris rapier). | Actif + quartier |

### 3.4 Vent cyclonique (typhon — le nom du produit !)

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`mapbox/webgl-wind`** | BSD-3-Clause | LE classique Mapbox (V. Agafonkin) : jusqu'à **1 M de particules de vent à 60 fps** en custom layer, alimentable par GFS/ERA5 (NetCDF→PNG). Natif Mapbox GL JS — notre stack. Effet « tempête » spectaculaire. | Quartier |
| **`wipfli/weatherlayers`** | permissive | Couches météo (vent particules, raster) pour **Mapbox GL JS / MapLibre** — complément pour rasters de pluie/température. | Quartier |

### 3.5 Mouvement de terrain / coulées

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`SynxFlow/SynxFlow`** | académique (CUDA) | Simule inondations + coulées + débris sur **GPU multi-CUDA**. Sérieux mais lourd (GPU NV requis) — option backend long terme. | Backend (plus tard) |
| **`loicmagne/webgl2_fluidsim`** | open | Stable Fluids en ~500 lignes WebGL2 — base propre pour une **coulée visuelle** côté client. | Quartier |
| **`PavelDoGreat/WebGL-Fluid-Simulation`** (déjà cité) | MIT | Réutilisable pour la coulée (fluide dense teinté terre). | Actif |

### 3.6 Multi-aléas / score de risque

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`CLIMADA-project/climada_python`** (ETH Zürich) | GPL-3.0 | Framework **probabiliste multi-aléas** (exposition × aléa × vulnérabilité) — le standard académique. Référence pour faire évoluer le « Score de risque global /100 » vers quelque chose de défendable. | Backend |
| **`RiskScape`** (NIWA/GNS, NZ) | open source | Plateforme multi-aléas (inondation, séisme, feu…) avec modèles de vulnérabilité par type d'actif. Complémentaire de CLIMADA. | Backend |

### 3.7 Jumeau BIM — améliorer l'étape 4

| Repo | Licence | Pourquoi | Où |
|---|---|---|---|
| **`thingraph/bim-viewer`** (déjà embarqué) | **MIT** | Notre viewer actuel (three.js + Vue, gltf/ifc). Les simulations inondation/feu/séisme sont **nos patches locaux** — on garde et on enrichit. | Actif |
| **`ThatOpen/web-ifc`** + **`ThatOpen/web-ifc-three`** | **MPL-2.0** | Parseur IFC officiel pour three.js — permet de charger de **vrais modèles IFC** (pas seulement l'extrusion BDNB) quand un client fournit son BIM. Le viewer le supporte déjà en partie (ifc). | Actif |
| **`xeokit/xeokit-sdk`** | **AGPL-3.0** (licence commerciale dispo) | Viewer BIM/GIS double précision — alternative solide mais **à éviter sauf budget licence commerciale**. | Actif |
| **`NASA-AMMOS/3DTilesRendererJS`** | MIT | Renderer **3D Tiles** pour three.js — charge des villes entières (ex. **Bati3D IGN**) à l'échelle quartier. | Quartier |
| **`dimforge/rapier3d-compat`** (déjà dans le viewer) | Apache-2.0 | Physique des débris. Alternatives : `cannon-es` (MIT), `ammo.js` (zlib). | Actif |

---

## 4. Feuille de route — étapes restantes

**Vague 1 — consolider le jumeau BIM (étape 4) — 1 à 2 semaines, le plus rentable**
Rien de nouveau côté backend, tout est dérivé des niveaux D03 déjà calculés :
1. **Enrichir les simulations existantes** du viewer :
   - **Feu** : ajouter la fumée (`WebGL-Fluid-Simulation` en overlay three.js) — le feu existe déjà, il est sans fumée.
   - **Inondation** : améliorer le rendu de l'eau (`threejs-water` : transparence, reflets) dans le jumeau.
   - **Séisme** : paliers de dégâts visuels + débris rapier (déjà là) — ajouter l'état de dégâts par élément.
2. **UX du viewer** : panneau de pilotage (choix de l'aléa, intensité D03, lecture/rewind), synchronisation avec les niveaux réels du rapport (déjà câblée via `typhon:sim` — la fiabiliser sur les 3 aléas).
3. **Étape 5** : lier chaque recommandation RAG à une simulation du viewer (« voir le scénario feu sur ce bâtiment »).

**Vague 2 — échelle quartier (perception) — 2 à 3 semaines**
1. **Vent cyclonique** : `mapbox/webgl-wind` en custom layer sur la carte (toggle « Vents cycloniques » — déjà présent dans le rapport). Effet de marque, coût faible.
2. **Feu** : propagation par automate cellulaire sur les volumes 3D + fumée.
3. **Séisme** : secousse caméra + états de dégâts colorés sur le bâti BDNB.
4. **Boucle quartier ↔ actif** : clic sur bâtiment sinistré → ouvre le jumeau avec la même intensité (contrat `typhon:sim` — existe déjà, le câbler côté carte).

**Vague 3 — jumeau fidèle (plus tard, dépend d'un client)**
- Chargement de **vrais modèles IFC** via `web-ifc` dans le bim-viewer.
- Ville à l'échelle quartier via **3D Tiles IGN Bati3D** (`3DTilesRendererJS`).

**Vague 4 — moteurs réels (backend isolés)**
- **OpenQuake** (sismique) et **CLIMADA** (score multi-aléas) en microservices séparés (respect AGPL/GPL par séparation de processus).
- Zones inondables PPR → polygones d'eau animés (shaders `Hydro3DJS` portés).

---

## 5. Ce qu'on ne fait pas
- ❌ Moteurs numériques lourds dans le navigateur (SPH, shallow-water GPU temps réel) — sauf `WebFlood` réécrit proprement, plus tard.
- ❌ `xeokit` sans licence commerciale (AGPL).
- ❌ `Cell2Fire` / `SynxFlow` en prod sans accord éditeur (research-only / CUDA).
- ❌ Aucune simulation présentée comme une étude d'ingénierie — le disclaimer pédagogique reste partout.

## 6. Risques / pièges
- **AGPL (OpenQuake, xeokit)** et **GPL (CLIMADA)** : OK en service séparé, contaminant si lié au code applicatif — architecturer en microservice dès le départ.
- **Google Maps-bound (Hydro3DJS)** : ne porter que les shaders, jamais l'API.
- **Données** : les vrais moteurs exigent MNT, occupation du sol, météo — pour la démo, les niveaux D03 Géorisques suffisent ; ne pas bloquer la démo sur des données qui n'existent pas.
- **Version de Mapbox** : nous sommes en **mapbox-gl v2.15** (pas de style `imports`) — si on veut le Standard configurable, prévoir une montée en v3 (impact à évaluer sur le code existant).
