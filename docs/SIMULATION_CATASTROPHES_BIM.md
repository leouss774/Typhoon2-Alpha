# Simulation de catastrophes naturelles dans le Jumeau BIM — Spécification

**Statut :** implémenté (6 août 2026) — voir §10 « État d'avancement »
**Date :** 6 août 2026
**Portée :** simuler en temps réel, dans le viewer thingraph/bim-viewer (étape 4 « Jumeau BIM » du flux /zone), les aléas **inondation**, **feu de forêt / feu de bâtiment** et **séisme**, pilotés par les données réelles du rapport (`/diagnostic/adresse` → `aleas[*].niveau`).

---

## 1. Objectif

Le jumeau numérique affiche aujourd'hui un bâtiment glTF statique (emprise BDNB réelle, étages, toiture, matériaux, fenêtres, porte). L'objectif est de lui donner **une dimension dynamique et pédagogique** : visualiser comment le bâtiment est exposé à chaque aléa, avec des simulations physiques/GPU exécutées dans le navigateur.

**Contrainte forte du projet** (rappelée dans l'AUDIT) : aucune donnée inventée. La simulation ne génère PAS de nouvelles données de risque — elle **visualise** le niveau déjà calculé par le backend. L'intensité de chaque simulation est dérivée de `niveau` (Très faible → Critique, bandes D03) et des données BDNB (matériaux, hauteur, étages).

> ⚠️ Avertissement à afficher dans l'UI : *« Simulation visuelle à but pédagogique — ne remplace pas une étude d'ingénierie (modélisation hydraulique, thermique ou sismique réglementaire). »*

---

## 2. État actuel du viewer (ce qui existe déjà)

| Élément | Détail |
|---|---|
| Viewer | clone local `thingraph/bim-viewer` (`frontend/bim-viewer/`), Vue 2 + TSX, webpack (vue-cli), servi sous `/bim-viewer/` |
| Moteur 3D | `three@^0.152.0` (WebGL2), renderer propre dans `src/core/Viewer3D.ts` |
| Modèle | glTF/GLB généré par `backend/app/digital_twin/gltf_builder.py` (murs / toiture / planchers / cadres / vitrage / porte — 6 primitives nommées) |
| Données aléas | `RisqueReport.aleas: [{code, libelle, present, niveau}]` — niveaux D03 : `très_faible | faible | modéré | élevé | critique` (+ scores 0–100 par zone) |
| Données bâtiment | `report.bdnb.batiment` : `hauteur_mean`, `nb_niveau`, `mat_mur_txt`, `mat_toit_txt`, `nb_log`, `surface_emprise_sol`, `l_orientation_baie_vitree`, `pourcentage_surface_baie_vitree_exterieur` |
| UI du viewer | panneau **dat.gui** (« Common settings », « Model operations »…) + `BottomBar` + `BimTree` — point d'accroche naturel pour un menu « Simulations » |
| Boucle de rendu | `Viewer3D.animate()` (three.js RAF) — point d'injection des mises à jour de simulation |

---

## 3. Faisabilité par aléa

### 3.1 Inondation — ✅ faisable (GPU Shallow Water)

Principe : un solveur **Shallow Water Equations (SWE)** sur grille 2D, exécuté en GPGPU (ping-pong de FBO) — le classique en WebGL. La hauteur d'eau monte autour/à travers le bâtiment ; les matériaux « vitrage » peuvent devenir translucides sous l'eau, le rez-de-chaussée s'immerge en fonction du niveau (`élevé`/`critique` → submersion jusqu'à X m).

- Grille projetée sur l'emprise au sol du bâtiment (et une zone tampon), résolution ~128–256² — largement dans les capacités WebGL2.
- Éclaboussures/front d'eau : particules simples en complément si besoin.
- Entrée : intensité = f(niveau) → hauteur d'eau cible + vitesse de montée.

### 3.2 Feu — ✅ faisable (particules GPU / volume raymarché)

Deux familles de rendus, toutes deux éprouvées :

1. **Système de particules** (`THREE.Points`, shader avec bruit de turbulence + ramp de couleurs) — léger, attachable à une zone (fenêtres, toiture) ou au bâtiment entier.
2. **Feu volumétrique raymarché** dans une boîte englobante (méthode de `THREE.Fire` de mattatz, utilisée dans l'exemple officiel three.js `webgl_fire`) — plus spectaculaire, plus coûteux.

Le feu de forêt / feux de façade : les particules sont ancrées sur le maillage (normales des murs) et montent avec la convection. `niveau` contrôle le nombre de sources, la hauteur des flammes, la vitesse de propagation le long des façades.

### 3.3 Séisme — ✅ faisable (rigid bodies OU déformation par shader)

Deux approches complémentaires :

1. **Simulation physique (recommandée)** : le bâtiment devient un assemblage de corps rigides (étages + murs) reliés par des contraintes ; un signal sismique (accélérogramme synthétique ou enveloppe sinusoïdale amortie, calibré sur `niveau`) déplace le sol ; les contraintes peuvent céder → oscillation puis effondrement pour `critique`. Moteurs : **cannon-es** (pur JS, MIT, simple) ou **Rapier** (WASM, Apache-2.0, très rapide — nécessaire si on simule des centaines de pièces).
2. **Approche légère (shader/matrice)** : vibration du groupe bâtiment via une onde sinusoïdale amortie + décalage progressif des étages (cisaillement). Zéro dépendance, très fluide, mais sans effondrement crédible.

### 3.4 Autres aléas (bonus)

| Aléa | Approche proposée | Coût |
|---|---|---|
| Mouvement de terrain / affaissement | déplacement vertical progressif de l'emprise (déformation du sol sous le bâtiment) | faible |
| Vent cyclonique | flexion de la structure (couple) + particules de pluie/débris | faible |
| ICPE / explosion | onde de choc (sphère déformante) + déformation des vitrages | moyen |

---

## 4. Dépôts GitHub / bibliothèques identifiés

### 4.1 Inondation (SWE / eau)

| Repo | URL | Licence | Notes d'intégration |
|---|---|---|---|
| **Hydro3DJS** (uihilab) | https://github.com/uihilab/Hydro3DJS | MIT | Construit sur three.js + Google Maps ; charge GLTF/GLB (nos bâtiments) + polygones d'inondation GeoJSON. Le plus proche d'un produit clé en main. |
| **WebFlood** (aeplay) | https://github.com/aeplay/WebFlood | open (thèse) | Solveur SWE semi-lagrangien sur GPU (GLSL), pensé pour l'inondation urbaine (Iowa City, dam-break). Excellente référence algorithmique ; code à extraire/porter. |
| **Webgl-Erosion** (LanLou123) | https://github.com/LanLou123/Webgl-Erosion | open | Terrain + flux d'eau interactifs ; utile pour l'aspect « montée des eaux / écoulement » sur un heightfield. |
| **fluid-gl** (tsupinie) | https://github.com/tsupinie/fluid-gl | open | Noyau SWE pur GLSL (C-grid, RK3) — la référence mathématique à porter dans notre pipeline GPGPU. |
| **three-fluid-fx** (artcodev) | https://github.com/artcodev/three-fluid-fx | MIT | Stable-Fluids 2D pour three.js (WebGL2 **et** WebGPU) ; **pas** un solveur d'inondation, mais excellent pour les reflets/distorsions « eau » en post-processing. Requiert three ≥ 0.183. |

**Recommandation :** porter le noyau SWE de *WebFlood*/*fluid-gl* dans un pipeline GPGPU three.js r152 (ping-pong FBO + `WebGLRenderTarget`), habillé façon *Hydro3DJS* (bâtiment GLB + plan d'eau animé).

### 4.2 Feu / fumée

| Repo | URL | Licence | Notes d'intégration |
|---|---|---|---|
| **THREE.Fire** (mattatz) | https://github.com/mattatz/THREE.Fire | open | Feu volumétrique raymarché (dans une boîte) — c'est l'origine de l'exemple officiel three.js `webgl_fire`. Directement utilisable, y compris en r152. |
| **three-particle-fire** (yomotsu) | https://github.com/yomotsu/three-particle-fire | open | Système de particules `THREE.Points` clé en main (`particleFire.install({THREE})`, `material.update(delta)`). Léger ; idéal pour les fenêtres/toiture. |
| **threejs-fluid-simulation** (bandinopla) | https://github.com/bandinopla/threejs-fluid-simulation | MIT | Port three.js du fameux « WebGL-Fluid-Simulation » (fumée 2D) ; permet de tracer des objets 3D comme forces. Bon pour la fumée dérivant au-dessus du toit. |
| **three-fluid-fx** (artcodev) | https://github.com/artcodev/three-fluid-fx | MIT | Même famille (2D stable fluids, passes EffectComposer : `SmokeOverlayPass`…). |

**Recommandation :** `three-particle-fire` pour les sources de flamme (léger, s'accroche aux facades) + `THREE.Fire` pour les gros foyers (toiture), avec notre propre shader de ramp si besoin de réglage fin.

### 4.3 Séisme / physique

| Moteur | URL | Licence | JS/WASM | Statut | Note |
|---|---|---|---|---|---|
| **cannon-es** | https://github.com/pmndrs/cannon-es | MIT | pur JS | actif | Le standard pour three.js ; helpers et exemples officiels. Parfait pour < 200 corps. |
| **Rapier** (`@dimforge/rapier3d-compat`) | https://github.com/dimforge/rapier | Apache-2.0 | WASM | très actif | 10–100× plus rapide ; exemples officiels three.js (`physics_rapier`). Choix pour effondrement à grande échelle. |
| **ammo.js** (Bullet) | https://github.com/kripken/ammo.js | zlib | WASM | maintenu à minima | Exemple officiel three.js `physics_ammo_break` (mur de briques destructible) — la référence « effondrement » des démos three.js. |
| **oimo.js** | https://github.com/lo-th/Oimo.js | MIT | pur JS | dormant | Léger, mais peu maintenu. |
| **planck.js** | https://github.com/piqnt/planck.js | MIT | pur JS | actif | **2D uniquement** — exclu pour un bâtiment 3D. |

**Référence d'effondrement à imiter :** l'exemple officiel three.js **`physics_ammo_break`** (threejs.org/examples/#physics_ammo_break) et **`physics_rapier`** (versions récentes).

**Recommandation :** commencer par **cannon-es** (aucun WASM, intégration three.js éprouvée) pour l'oscillation/effondrement des étages ; migrer vers **Rapier** si les performances ou le nombre de corps l'exigent.

---

## 5. Architecture proposée

```
bim-viewer/src/simulations/
├── index.ts              # DisasterSimulationManager — registre par aléa, cycle de vie
├── types.ts              # Intensité par niveau (paramètres par aléa)
├── drive.ts              # aléas report (RisqueReport) → paramètres de simulation
├── flood/
│   ├── ShallowWater.ts   # solveur SWE GPGPU (ping-pong FBO), porté de WebFlood/fluid-gl
│   ├── WaterMesh.ts      # plan d'eau déformé par la hauteur du solveur
│   └── rain.ts           # (option) particules de pluie
├── fire/
│   ├── FireSources.ts    # sources de flamme ancrées sur les façades (three-particle-fire)
│   ├── VolumetricFire.ts # (option) foyer principal raymarché (THREE.Fire)
│   └── smoke.ts          # (option) fumée 2D (bandinopla)
└── seismic/
    ├── ShakeDriver.ts    # signal sismique (enveloppe amortie, calibrée sur le niveau)
    ├── rigid/
    │   ├── BuildingRigidBody.ts  # découpe du GLB en étages → corps rigides cannon-es
    │   └── collapse.ts           # ruptures de contraintes (effondrement)
    └── sway.ts           # (variante légère) cisaillement par matrices
```

Points d'intégration dans le code existant :

1. **`Viewer3D.ts`** — hook dans `animate()` : `simulationManager.update(delta, elapsed)`.
2. **`Viewer3DContainer.tsx`** — montage/démontage du manager ; passage du `report` (via postMessage parent→iframe, cf. §6) ou d'un query param.
3. **dat.gui (`DatGuiHelper.ts`)** — nouveau dossier **« Simulations »** : activer/désactiver par aléa, curseurs intensité, vitesse, bouton « Reset ».
4. **`BimTree`** — les objets de simulation (plan d'eau, flammes, sol) apparaissent comme groupe « Simulations » (masquables).

---

## 6. Flux de données (parent React → iframe)

Le rapport (`aleas`, `bdnb`) vit côté React (`/zone`). Deux options :

1. **PostMessage** (recommandé) : le parent envoie `{type:'typhoon:sim', aleas, batiment}` à l'iframe ; le viewer pilote les simulations. Réutilise le canal Postmate déjà présent (`src/core/postmate/`).
2. **Query param** : encoder un résumé des aléas dans l'URL de l'iframe (limité en taille, moins propre).

`drive.ts` convertit : `niveau` → intensité 0–1 → paramètres (hauteur d'eau max, nombre de sources de feu, amplitude/fréquence sismique) + texte de légende.

| Niveau | Inondation | Feu | Séisme |
|---|---|---|---|
| très_faible | 0.05 m, pas d'immer. | 1–2 sources faibles | micro-tremblement (visuel seul) |
| faible | 0.2 m, cave | 3–5 sources | vibrations perceptibles |
| modéré | 0.6 m, RDC | façade partielle | oscillations visibles |
| élevé | 1.2 m, 1er étage | toiture + façades | oscillations fortes |
| critique | 2+ m, immersion totale | embrasement | effondrement (rigid bodies) |

---

## 7. Plan d'implémentation par phases

- **P0 — Socle (½ jour)** : manager + dossier dat.gui « Simulations » + `drive.ts` + postMessage parent→iframe.
- **P1 — Séisme léger (1 jour)** : `ShakeDriver` + `sway.ts` (zéro dépendance) — impact immédiat, fluide, bas risque.
- **P2 — Feu (2–3 jours)** : `three-particle-fire` + `THREE.Fire` ancrés sur les façades/ toiture ; propagation pilotée par le niveau.
- **P3 — Inondation (3–5 jours)** : solveur SWE GPGPU porté de WebFlood/fluid-gl ; plan d'eau + immersion progressive ; matériau vitrage translucide sous l'eau.
- **P4 — Effondrement sismique (3–5 jours)** : découpe du GLB en corps rigides (cannon-es d'abord), contraintes de rupture, effondrement pour `critique`. Migration éventuelle Rapier.
- **P5 — Polissage** : curseurs temps réel, presets par aléa, avertissement pédagogique, test multi-niveaux, perf (compteur FPS déjà présent dans le viewer).

**Critères d'acceptation P1–P4 :** la simulation s'active/désactive depuis dat.gui, l'intensité suit `aleas[*].niveau` du rapport, le rendu reste ≥ 30 FPS sur GPU intégré, aucun crash du viewer (fail-soft si WebGL2 indisponible).

---

## 8. Contraintes & risques

- **Three.js r152** : compatible avec cannon-es, `THREE.Fire`, `three-particle-fire`. `three-fluid-fx` exige ≥ 0.183 → à porter soi-même ou à ignorer (on a WebFlood/fluid-gl).
- **WASM** : Rapier/ammo.js nécessitent l'acceptation de WASM (~1–2 Mo) — OK en local/file://, à vérifier en prod (Content-Security-Policy éventuelle).
- **GPGPU SWE** : nécessite WebGL2 + `OES_texture_half_float` — détection au démarrage, repli = plan d'eau statique animé (hauteur sinusoïdale) sans solveur.
- **Découpe du GLB pour l'effondrement** : le GLB est un maillage unique par primitive ; il faudra **générer la découpe côté backend** (le builder glTF peut déjà produire des primitives par étage — extension de `gltf_builder.py` : un `parts` « étages » séparés) ou découper côté client (plus fragile).
- **Licences** : tous les moteurs proposés sont MIT/Apache/zlib → compatibles. Vérifier l'état « open (thèse) » de WebFlood avant portage commercial ; à défaut, s'inspirer du papier (SWE est de la science publique).
- **Précision** : c'est de la visualisation, pas de la modélisation réglementaire → avertissement UI obligatoire.

---

## 9. Questions ouvertes — décisions actées

1. **Quel aléa en premier ?** → Les trois (P1–P4 fusionnés en un livrable) :
   séisme (cisaillement + effondrement), feu (particules GPU), inondation
   (plan d'eau animé) sont livrés ensemble, pilotés par le rapport.
2. **cannon-es ou Rapier ?** → **Rapier** (`@dimforge/rapier3d-compat`
   v0.19, WASM inline, Apache-2.0) — très utilisé sur GitHub, et le build
   « compat » embarque le WASM en base64 (aucune requête réseau, compatible
   CSP/file://). Chunk séparé (~2 Mo) chargé à la demande, uniquement pour
   un effondrement `critique`. Repli automatique sur le cisaillement par
   matrices si Rapier est indisponible (fail-soft).
3. **Étendre `gltf_builder.py` ?** → Oui. `build_glb_bim(..., etages_separes=True,
   parts_as_nodes=True)` : bandes de murs par niveau (clefs `etage_1..N`)
   et **une node glTF par partie** (`Etage 1`, `Toiture`, `Planchers`...),
   matériau associé par NOM de partie (les étages partagent « Murs »).
   `/diagnostic/adresse/gltf` active les deux drapeaux — le viewer peut
   cisailer/effondrer chaque étage sans découper le maillage côté client.
4. **Canal parent → iframe ?** → Oui, postMessage brut `typhoon:sim`
   (ZoneBIM.tsx → viewer), payload `{ aleas, batiment }` — aucun handshake
   postmate à synchroniser. Repli query param `?sim=feu:eleve,...`.
5. **Projets d'exemple ?** → Oui : les simulations sont disponibles partout
   (projets d'exemple, mode autonome) avec les intensités réglables dans
   dat.gui ; le query param `sim` permet un déclenchement programmatique.

## 10. État d'avancement (livrable initial, 6 août 2026)

- **P0 socle** : `src/simulations/` (SimulationManager, drive, types),
  dossier dat.gui « Simulations », payload rapport + query param. ✅
- **P1 séisme** : `ShakeDriver` (enveloppe amortie) + cisaillement par
  étage (matrices, zéro dépendance) — tous niveaux. ✅
- **P4 effondrement** : corps rigides **Rapier** par étage (impulsion
  croissante avec la hauteur, rotation, rattachement toiture/cadres/
  vitrage/porte à l'étage supérieur, planchers laissés en place) pour
  `critique`, restauration à la désactivation. ✅
- **P2 feu** : particules GPU maison (THREE.Points + shader turbulence/
  ramp) ancrées sur façades + toiture, nombre de foyers et hauteur de
  flamme par niveau. ✅
- **P3 inondation** : plan d'eau animé (shader de vagues) montant jusqu'à
  `FLOOD_HEIGHTS[niveau]` — le repli « eau animée sans solveur » prévu par
  la spec. Le solveur SWE GPGPU (WebFlood/fluid-gl) reste une évolution.
- **P5 polissage** : curseurs temps réel (vitesse), reset, avertissement
  pédagogique dans l'UI (`bim-sim-note`), fail-soft WebGL/Rapier. ✅

### Mise à jour — interactions avec le bâtiment (6 août 2026, soir)

Les simulations ne sont plus de simples « décors » : elles interagissent
avec le modèle 3D du bâtiment (les étages séparés `Etage N` du GLB).

- **Inondation — submersion réelle** : les matériaux du bâtiment sont clonés
  et enrichis d'un shader (`onBeforeCompile`, chunk `output_fragment` r152,
  un programme par clone) : toute partie dont l'altitude est sous le niveau
  d'eau passe en teinte « sous l'eau » et devient translucide — on voit le
  RDC s'immerger puis les étages. Le plan d'eau est corrigé (échelle 1 : la
  hauteur est désormais en mètres monde, le bug ×60 qui faisait flotter
  l'eau à ~36 m est corrigé) avec vagues multi-octaves + liseré d'écume
  (foam) calculé en shader à la distance des murs.
- **Feu — propagation par étage et dégâts** : les foyers sont indexés par
  étage et s'allument du RDC vers le haut (vitesse selon le niveau,
  plafonné par `MAX_BURN_FRACTION` : très faible = RDC seul, critique =
  embrasement complet + toiture). Les murs de chaque étage carbonisent
  (couleur → charbon, rugosité), le vitrage s'embrase (émission orange)
  puis « casse » (opacité → 0), la toiture s'enflamme aux niveaux élevés,
  et un panache de fumée monte au-dessus du toit. Tout est restauré à la
  désactivation.
- **Fiabilité** : `position` ajoutée aux géométries `THREE.Points` (sans
  lui, three dessine 0 sommets), `smoothstep` aux arêtes bien ordonnées
  (edge0 < edge1, sinon comportement indéfini), uniformes déclarés par
  étape de shader. Vérifié : 64–72 FPS sur GPU intégré, aucun crash.

Toujours pas de solveur SWE GPGPU (évolution) ; le cisaillement sismique et
l'effondrement Rapier étaient déjà interactifs (P1/P4).

Points d'intégration : `Viewer3D.animate()` (update + rendu continu tant
qu'une simulation est active), `addLoadedModelToScene` (bindModel),
`DatGuiHelper` (folder Simulations + synchronisation sans boucle infinie),
`ZoneBIM.tsx` (postMessage `typhoon:sim`).

Critères d'acceptation vérifiés : activation/désactivation dat.gui,
intensité suivant `aleas[*].niveau`, effondrement Rapier fonctionnel sur
un modèle à étages (testé en conditions réelles), restauration complète à
la désactivation, aucun crash (RangeError de boucle dat.gui corrigé).
