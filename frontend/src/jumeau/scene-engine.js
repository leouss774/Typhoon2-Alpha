import * as THREE from 'three';

/* Moteur 3D du jumeau numérique — porté tel quel depuis
   frontend/jumeau_numerique/index.html (script 1, lignes 1846-4036), puis
   enveloppé dans initScene()/disposeScene() pour le cycle de vie React. */

let _rafId = 0;
let _resizeHandler = null;
let _mouseUpHandler = null;
let _mouseMoveHandler = null;
let _canvas = null;
let _renderer = null;
const _elementHandlers = [];

// Échappement HTML partagé : utilisé par le rendu DOM du moteur ET par
// matchArtisans() (exporté pour la page /artisans). Défini au niveau module
// pour être accessible des deux côtés sans duplication.
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function initScene() {
/* =========================================================================
   TYPHOON — JUMEAU NUMÉRIQUE 3D — moteur réel (diagnostic du bien)
   Consomme le contrat JSON produit par digital_twin_agent :
   { adresse, bien, geometry, score_global, zones{7}, projection_2050, climat_2050 }
   Rendu : effet scan holographique (remplissage translucide + wireframe bleu),
   couleur des zones = niveau de risque, effets visuels (fissures / montée des
   eaux / auréoles d'humidité) pilotés par une fonction de mapping pure
   risque -> paramètres visuels. Cet écran est affiché uniquement une fois
   qu'un diagnostic (réel ou exemple) a été chargé — voir le script
   d'orchestration plus bas.
   ========================================================================= */

// ---------- 0. DONNÉES D'EXEMPLE (utilisées par le bouton "essayer sans backend") ----------
const DEFAULT_DATA = {
  "adresse": "12 rue des Lilas, 33000 Bordeaux",
  "bien": { "type": "maison individuelle", "annee_construction": 1975, "coordonnees": { "lat": 44.8378, "lon": -0.5792 } },
  "geometry": {
    "footprint_shape": "rectangulaire",
    "largeur_m": 8.5, "longueur_m": 10.2, "orientation_deg": 15,
    "floors_count": 2, "hauteur_sous_plafond_m": 2.6,
    "roof_shape": "deux_pans", "pente_toit_deg": 35,
    "materiau_mur": "parpaing_enduit", "materiau_toiture": "tuiles_terre_cuite",
    "has_basement": true, "has_cellar": false,
    "has_garage": true, "garage_position": "ouest",
    "has_garden": true, "garden_surface_m2": 250
  },
  "score_global": 58,
  "zones": {
    "fondations": { "risque": 78, "niveau": "eleve", "alea_principal": "Retrait-gonflement des argiles", "justification": "Sol argileux identifié en zone d'aléa fort, aggravé par l'alternance sécheresse/humidité.", "recommandations": [
      { "travaux": "Renforcement des fondations par micropieux", "cout_estime": "9000-16000€", "gain_resilience": 30 },
      { "travaux": "Drainage périphérique", "cout_estime": "3000-6000€", "gain_resilience": 15 }
    ]},
    "murs_nord": { "risque": 35, "niveau": "modere", "alea_principal": "Infiltration", "justification": "Exposition nord avec humidité résiduelle plus fréquente.", "recommandations": [
      { "travaux": "Traitement hydrofuge de façade", "cout_estime": "1500-3000€", "gain_resilience": 12 }
    ]},
    "murs_sud": { "risque": 20, "niveau": "faible", "alea_principal": "Stress thermique", "justification": "Exposition sud correcte, matériaux jugés stables.", "recommandations": [] },
    "murs_est": { "risque": 28, "niveau": "faible", "alea_principal": "Vent", "justification": "Exposition modérée aux vents dominants.", "recommandations": [] },
    "murs_ouest": { "risque": 42, "niveau": "modere", "alea_principal": "Intempéries", "justification": "Façade la plus exposée aux intempéries selon l'historique CATNAT local.", "recommandations": [
      { "travaux": "Renforcement bardage", "cout_estime": "2000-4000€", "gain_resilience": 10 }
    ]},
    "toiture": { "risque": 55, "niveau": "modere", "alea_principal": "Canicule / stress thermique", "justification": "Isolation actuelle insuffisante face à l'augmentation prévue des épisodes caniculaires.", "recommandations": [
      { "travaux": "Isolation thermique renforcée", "cout_estime": "6000-11000€", "gain_resilience": 22 }
    ]},
    "sous_sol": { "risque": 65, "niveau": "eleve", "alea_principal": "Inondation / remontée de nappe", "justification": "Proximité d'un cours d'eau avec historique d'inondation dans le secteur.", "recommandations": [
      { "travaux": "Pose de batardeaux et clapet anti-retour", "cout_estime": "2500-5000€", "gain_resilience": 20 }
    ]}
  },
  "projection_2050": {
    "score_global": 81,
    "zones": {
      "fondations": { "risque": 92, "niveau": "critique", "alea_principal": "RGA aggravé", "justification": "Sécheresses prolongées prévues en 2050, risque de fissuration majeure.", "recommandations": [{ "travaux": "Renforcement fondations + surveillance annuelle", "cout_estime": "9000-16000€", "gain_resilience": 35 }] },
      "murs_nord":  { "risque": 48, "niveau": "modere", "alea_principal": "Infiltration accrue", "justification": "Augmentation des précipitations intenses en hiver.", "recommandations": [{ "travaux": "Traitement hydrofuge de façade", "cout_estime": "1500-3000€", "gain_resilience": 15 }] },
      "murs_sud":   { "risque": 40, "niveau": "modere", "alea_principal": "Stress thermique", "justification": "Canicules plus longues, exposition sud plus sensible.", "recommandations": [{ "travaux": "Volets isolants", "cout_estime": "1200-2500€", "gain_resilience": 10 }] },
      "murs_est":   { "risque": 38, "niveau": "modere", "alea_principal": "Vent renforcé", "justification": "Intensification des épisodes de vent fort.", "recommandations": [] },
      "murs_ouest": { "risque": 60, "niveau": "eleve", "alea_principal": "Intempéries renforcées", "justification": "Façade la plus exposée, aggravation attendue.", "recommandations": [{ "travaux": "Renforcement bardage renforcé", "cout_estime": "2000-4000€", "gain_resilience": 18 }] },
      "toiture":    { "risque": 80, "niveau": "eleve", "alea_principal": "Canicule prolongée", "justification": "Périodes de canicule estimées à plusieurs mois en 2050.", "recommandations": [{ "travaux": "Isolation thermique renforcée + ventilation", "cout_estime": "6000-11000€", "gain_resilience": 30 }] },
      "sous_sol":   { "risque": 85, "niveau": "critique", "alea_principal": "Inondation aggravée", "justification": "Augmentation de 30% des sinistres climatiques attendue d'ici 2050.", "recommandations": [{ "travaux": "Batardeaux + pompe de relevage", "cout_estime": "3500-7000€", "gain_resilience": 28 }] }
    }
  },
  "climat_2050": { "temperature_max_projetee_c": 41.5, "source": "Copernicus" }
};

const ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"];

// ---------- 1. FONCTION DE MAPPING RISQUE -> EFFET VISUEL (pure, déterministe) ----------
function mapRiskToEffect(zoneName, score) {
  const s = Math.max(0, Math.min(100, score));
  if (zoneName === "fondations") {
    let opacity = 0, layers = 0;
    if (s >= 60) { opacity = 0.55 + (s - 60) / 40 * 0.40; layers = s >= 85 ? 3 : 2; }
    else if (s >= 30) { opacity = 0.12 + (s - 30) / 30 * 0.35; layers = 1; }
    return { crackOpacity: Math.min(opacity, 0.95), crackLayers: layers };
  }
  if (zoneName === "sous_sol") {
    let ratio = 0;
    if (s >= 60) ratio = 0.5 + (s - 60) / 40 * 0.5;
    else if (s >= 30) ratio = (s - 30) / 30 * 0.5;
    return { waterHeightRatio: Math.min(ratio, 1) };
  }
  if (zoneName === "toiture") {
    let wear = 0;
    if (s >= 60) wear = 0.4 + (s - 60) / 40 * 0.6;
    else if (s >= 30) wear = (s - 30) / 30 * 0.4;
    return { tileWear: Math.min(wear, 1) };
  }
  if (zoneName.startsWith("murs_")) {
    let stain = 0;
    if (s >= 70) stain = 0.3 + (s - 70) / 30 * 0.5;
    else if (s >= 40) stain = (s - 40) / 30 * 0.3;
    return { humidityOpacity: Math.min(stain, 0.85) };
  }
  return {};
}

// ---------- 2. SCÈNE THREE.JS ----------
const container = document.getElementById('scene-container');
const scene = new THREE.Scene();
// Fond blanc : la scene du jumeau numerique s'aligne sur le reste de
// l'interface (fond blanc) plutot que sur un bleu marine sombre.
const FOND_SCENE = 0xffffff;
scene.background = new THREE.Color(FOND_SCENE);
// Distances recalculees par fitCameraToHouse en fonction de la taille du
// bati : ces valeurs ne sont que l'amorce avant le premier diagnostic.
scene.fog = new THREE.Fog(FOND_SCENE, 30, 70);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0x3a7bd5, 0x04070c, 0.7));
const rim = new THREE.DirectionalLight(0x4da6ff, 0.5); rim.position.set(-8, 10, -6); scene.add(rim);
const key = new THREE.DirectionalLight(0xbfe0ff, 0.4); key.position.set(8, 12, 8); scene.add(key);

const grid = new THREE.GridHelper(60, 60, 0x1560ff, 0x0d2647);
grid.material.transparent = true; grid.material.opacity = 0.45;
scene.add(grid);

const ringGeo = new THREE.RingGeometry(6.5, 6.7, 64);
const ringMat = new THREE.MeshBasicMaterial({ color: 0x4da6ff, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
const scanRing = new THREE.Mesh(ringGeo, ringMat);
scanRing.rotation.x = -Math.PI / 2; scanRing.position.y = 0.01;
scene.add(scanRing);

const WIRE_COLOR = 0x2f6f96;

// --- Réglage de la luminosité de la scène ---
// Les volumes de la maison sont des MeshBasicMaterial en blending normal
// (alpha classique) : ils n'ont PAS de normales éclairées et ignorent donc
// completement les HemisphereLight/DirectionalLight ajoutées plus haut.
// Leur lisibilité ne dépend que de leur opacité — c'est ce coefficient
// qu'il faut toucher pour éclaircir/foncer le rendu, pas l'intensité des
// lumières.
// Le blending etait additif a l'origine (scene de fond sombre) : sur fond
// blanc, l'additif se contente d'ajouter de la lumiere a du blanc deja
// sature, donc les couleurs de risque disparaissaient completement. On
// utilise maintenant un blending normal (alpha), qui teinte reellement le
// fond blanc et reste translucide.
const LUMINOSITE = 2.9;
const OPACITE_FILAIRE = 0.9;   // aretes : 0.85 a l'origine

function makeWireMat() { return new THREE.LineBasicMaterial({ color: WIRE_COLOR, transparent: true, opacity: OPACITE_FILAIRE }); }
function makeFillMat(color, opacity) {
  // Plafond a 0.62 : assez couvrant pour que la couleur de risque
  // (vert/orange/rouge) soit immediatement lisible sur fond blanc, tout en
  // restant translucide (on voit toujours le volume/le filaire au travers).
  const opacite = Math.min(0.62, (opacity ?? 0.16) * LUMINOSITE);
  return new THREE.MeshBasicMaterial({ color, transparent: true, opacity: opacite, side: THREE.DoubleSide, blending: THREE.NormalBlending, depthWrite: false });
}
function addPart(group, geometry, position, fillColor, opacity) {
  const fill = new THREE.Mesh(geometry, makeFillMat(fillColor, opacity));
  if (position) fill.position.copy(position);
  group.add(fill);
  const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), makeWireMat());
  if (position) wire.position.copy(position);
  group.add(wire);
  return fill;
}
function addRawPart(group, bufferGeometry, fillColor, opacity) {
  bufferGeometry.computeVertexNormals();
  const fill = new THREE.Mesh(bufferGeometry, makeFillMat(fillColor, opacity));
  group.add(fill);
  const wire = new THREE.LineSegments(new THREE.EdgesGeometry(bufferGeometry), makeWireMat());
  group.add(wire);
  return fill;
}

// ---------- 3. CANEVAS PROCÉDURAUX (fissures / auréoles) ----------
function makeCrackTexture(layers) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 512;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, 512, 512);
  ctx.strokeStyle = 'rgba(255,255,255,0.95)';
  ctx.shadowColor = 'rgba(255,80,60,0.9)'; ctx.shadowBlur = 4;
  const rand = mulberry32(42);
  for (let l = 0; l < Math.max(1, layers); l++) {
    let x = 80 + rand() * 350, y = 40;
    ctx.lineWidth = 2 + rand() * 2;
    ctx.beginPath(); ctx.moveTo(x, y);
    for (let i = 0; i < 14; i++) {
      x += (rand() - 0.5) * 70;
      y += 30 + rand() * 20;
      ctx.lineTo(x, Math.min(y, 500));
      if (rand() > 0.6) {
        const bx = x + (rand() - 0.5) * 60, by = y + rand() * 40;
        ctx.moveTo(x, y); ctx.lineTo(bx, Math.min(by, 500)); ctx.moveTo(x, y);
      }
    }
    ctx.stroke();
  }
  return new THREE.CanvasTexture(c);
}
function makeStainTexture() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 512;
  const ctx = c.getContext('2d');
  const grd = ctx.createRadialGradient(256, 380, 10, 256, 380, 260);
  grd.addColorStop(0, 'rgba(140,180,255,0.85)');
  grd.addColorStop(0.5, 'rgba(100,140,220,0.35)');
  grd.addColorStop(1, 'rgba(100,140,220,0)');
  ctx.fillStyle = grd; ctx.fillRect(0, 0, 512, 512);
  return new THREE.CanvasTexture(c);
}
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const crackTextures = { 1: makeCrackTexture(1), 2: makeCrackTexture(2), 3: makeCrackTexture(3) };
const stainTexture = makeStainTexture();

// ---------- 3bis. TEXTURES DE MATÉRIAU RÉEL (murs/toiture) ----------
// Motifs procéduraux sélectionnés par le SLUG DE MATÉRIAU RÉEL renvoyé par
// la BDNB (`geometry.materiau_mur` / `materiau_toiture`, cf.
// backend/app/digital_twin/geometry_builder.py::_slugify). Rien n'est
// inventé sur QUEL materiau utiliser — seul le rendu du motif est une
// approximation graphique. Quand le materiau est "indetermine" (valeur
// reelle et frequente de la BDNB) ou inconnu, le rendu reste un enduit
// neutre plutot que de deviner une texture specifique.
//
// Taille reelle (m) couverte par un motif avant repetition : pilote
// `texture.repeat`, pas les UV (deja en metres, voir quadsToGeometry).
const MATERIAL_TILE_M = { mur: 2.2, toit: 2.4 };
const materialTextureCache = {};

function getMaterialTexture(kind, materiauSlugBrut) {
  const slug = (materiauSlugBrut || 'indetermine').toLowerCase();
  const key = kind + ':' + slug;
  if (materialTextureCache[key]) return materialTextureCache[key];
  const canvas = kind === 'toit' ? drawRoofTexture(slug) : drawWallTexture(slug);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  const tuile = MATERIAL_TILE_M[kind] || 2.2;
  texture.repeat.set(1 / tuile, 1 / tuile);
  materialTextureCache[key] = texture;
  return texture;
}

// Variante pour le mode boîte (repli sans polygone réel) : BoxGeometry a
// des UV 0..1 par face, pas des mètres comme quadsToGeometry. On CLONE la
// texture (repeat indépendant) plutôt que de modifier `getMaterialTexture`
// en place, pour ne pas fausser le carrelage déjà calibré en mètres du
// mode emprise réelle, qui partage la même instance mise en cache.
function boxMaterialTexture(kind, materiauSlugBrut, faceLargeurM, faceHauteurM) {
  const base = getMaterialTexture(kind, materiauSlugBrut);
  const clone = base.clone();
  clone.needsUpdate = true;
  const tuile = MATERIAL_TILE_M[kind] || 2.2;
  clone.repeat.set(faceLargeurM / tuile, faceHauteurM / tuile);
  return clone;
}

function drawWallTexture(slug) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 256;
  const ctx = c.getContext('2d');
  const rand = mulberry32(7);

  if (slug.includes('brique')) {
    ctx.fillStyle = '#8a4a3a'; ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = 'rgba(230,220,205,0.55)'; ctx.lineWidth = 3;
    const briqueH = 22, briqueW = 56;
    for (let row = 0, y = 0; y < 256 + briqueH; row++, y += briqueH) {
      const decalage = (row % 2) * (briqueW / 2);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(256, y); ctx.stroke();
      for (let x = -decalage; x < 256 + briqueW; x += briqueW) {
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + briqueH); ctx.stroke();
        ctx.fillStyle = `rgba(0,0,0,${0.04 + rand() * 0.06})`;
        ctx.fillRect(x + 2, y + 2, briqueW - 4, briqueH - 4);
      }
    }
  } else if (slug.includes('pierre_de_taille') || slug.includes('meuliere')) {
    ctx.fillStyle = '#c9bd9e'; ctx.fillRect(0, 0, 256, 256);
    const blocH = 40, blocW = 84;
    ctx.strokeStyle = 'rgba(90,80,60,0.5)'; ctx.lineWidth = 2.5;
    for (let row = 0, y = 0; y < 256 + blocH; row++, y += blocH) {
      const decalage = (row % 2) * (blocW / 2);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(256, y); ctx.stroke();
      for (let x = -decalage; x < 256 + blocW; x += blocW) {
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + blocH); ctx.stroke();
        ctx.fillStyle = `rgba(120,105,80,${0.05 + rand() * 0.08})`;
        ctx.fillRect(x + 3, y + 3, blocW - 6, blocH - 6);
      }
    }
    if (slug.includes('meuliere')) {
      // Meuliere : moellons ronds (silex) plus irreguliers que la pierre de taille.
      for (let i = 0; i < 90; i++) {
        const r = 4 + rand() * 7;
        ctx.fillStyle = `rgba(70,60,45,${0.12 + rand() * 0.18})`;
        ctx.beginPath(); ctx.arc(rand() * 256, rand() * 256, r, 0, Math.PI * 2); ctx.fill();
      }
    }
  } else if (slug.includes('pan_de_bois')) {
    ctx.fillStyle = '#d9cba8'; ctx.fillRect(0, 0, 256, 256);   // torchis clair en remplissage
    ctx.strokeStyle = '#4a3323'; ctx.lineWidth = 10;
    ctx.strokeRect(5, 5, 246, 246);
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(256, 256); ctx.moveTo(256, 0); ctx.lineTo(0, 256); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(128, 0); ctx.lineTo(128, 256); ctx.moveTo(0, 128); ctx.lineTo(256, 128); ctx.stroke();
  } else if (slug.includes('torchis')) {
    ctx.fillStyle = '#d9cba8'; ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 260; i++) {
      ctx.fillStyle = `rgba(150,120,80,${0.05 + rand() * 0.1})`;
      ctx.fillRect(rand() * 256, rand() * 256, 1 + rand() * 2, 1 + rand() * 2);
    }
  } else if (slug.includes('bois')) {
    ctx.fillStyle = '#6b4a30'; ctx.fillRect(0, 0, 256, 256);
    const plancheW = 32;
    for (let x = 0; x < 256; x += plancheW) {
      ctx.fillStyle = `rgba(0,0,0,${0.05 + rand() * 0.05})`;
      ctx.fillRect(x, 0, 2, 256);
      for (let i = 0; i < 6; i++) {
        ctx.strokeStyle = `rgba(40,25,15,${0.15 + rand() * 0.15})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const xg = x + 4 + rand() * (plancheW - 8);
        ctx.moveTo(xg, 0); ctx.lineTo(xg + (rand() - 0.5) * 8, 256); ctx.stroke();
      }
    }
  } else {
    // parpaing_enduit, beton, indetermine et tout le reste : enduit neutre
    // -- le rendu ne pretend PAS connaitre un materiau que la donnee ne
    // fournit pas (INDETERMINE est une valeur reelle et frequente).
    ctx.fillStyle = '#c7c2b6'; ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 900; i++) {
      ctx.fillStyle = `rgba(0,0,0,${rand() * 0.035})`;
      ctx.fillRect(rand() * 256, rand() * 256, 1, 1);
    }
  }
  return c;
}

function drawRoofTexture(slug) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 256;
  const ctx = c.getContext('2d');
  const rand = mulberry32(11);

  if (slug.includes('ardoise')) {
    ctx.fillStyle = '#33404d'; ctx.fillRect(0, 0, 256, 256);
    const h = 26, w = 40;
    ctx.strokeStyle = 'rgba(10,15,20,0.6)'; ctx.lineWidth = 2;
    for (let row = 0, y = 0; y < 256 + h; row++, y += h * 0.72) {
      const decalage = (row % 2) * (w / 2);
      for (let x = -decalage; x < 256 + w; x += w) {
        ctx.beginPath();
        ctx.moveTo(x, y); ctx.lineTo(x + w / 2, y + h); ctx.lineTo(x + w, y);
        ctx.stroke();
        ctx.fillStyle = `rgba(255,255,255,${0.02 + rand() * 0.03})`;
        ctx.fill();
      }
    }
  } else if (slug.includes('tuile')) {
    ctx.fillStyle = '#a8502e'; ctx.fillRect(0, 0, 256, 256);
    const h = 30, w = 34;
    for (let row = 0, y = 0; y < 256 + h; row++, y += h * 0.62) {
      const decalage = (row % 2) * (w / 2);
      for (let x = -decalage; x < 256 + w; x += w) {
        ctx.fillStyle = `rgba(0,0,0,${0.08 + rand() * 0.06})`;
        ctx.beginPath(); ctx.arc(x + w / 2, y, w / 2 - 2, 0, Math.PI, false); ctx.fill();
        ctx.fillStyle = `rgba(255,200,150,${0.04 + rand() * 0.05})`;
        ctx.beginPath(); ctx.arc(x + w / 2, y - 2, w / 2 - 6, 0, Math.PI, false); ctx.fill();
      }
    }
  } else if (slug.includes('zinc')) {
    ctx.fillStyle = '#9aa3ab'; ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = 'rgba(50,55,60,0.5)'; ctx.lineWidth = 2;
    for (let x = 0; x < 256; x += 22) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 256); ctx.stroke(); }
  } else if (slug.includes('bac_acier')) {
    ctx.fillStyle = '#7c8790'; ctx.fillRect(0, 0, 256, 256);
    for (let x = 0; x < 256; x += 16) {
      const g = ctx.createLinearGradient(x, 0, x + 16, 0);
      g.addColorStop(0, 'rgba(0,0,0,0.18)'); g.addColorStop(0.5, 'rgba(255,255,255,0.10)'); g.addColorStop(1, 'rgba(0,0,0,0.18)');
      ctx.fillStyle = g; ctx.fillRect(x, 0, 16, 256);
    }
  } else if (slug.includes('vegetalise')) {
    ctx.fillStyle = '#3d6b3a'; ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 700; i++) {
      ctx.fillStyle = `rgba(${40 + rand() * 40},${90 + rand() * 60},${40 + rand() * 30},0.5)`;
      ctx.fillRect(rand() * 256, rand() * 256, 2, 2);
    }
  } else {
    // beton (toiture-terrasse) / indetermine : surface neutre, plate.
    ctx.fillStyle = '#9a978c'; ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 500; i++) {
      ctx.fillStyle = `rgba(0,0,0,${rand() * 0.04})`;
      ctx.fillRect(rand() * 256, rand() * 256, 1, 1);
    }
  }
  return c;
}

// ---------- 4. CONSTRUCTION PARAMÉTRIQUE DE LA MAISON ----------
let house = null, zoneGroups = {}, zoneFillMeshes = {}, interactiveMeshes = [];
let crackMesh = null, waterMesh = null, stainMeshes = {};
let houseDims = {};
let labelSprites = {}, leaderLines = {};
// Point + normale representatifs de chaque façade, renseignes uniquement en
// mode emprise reelle : sur un polygone quelconque, "le mur nord" n'est plus
// a z = -D/2, il faut retenir l'arete reellement construite pour y accrocher
// les etiquettes et les effets (auréoles d'humidite).
let zoneAnchors = {};
// Couche "structure" : volumes opaques et texturés par matériau réel
// (murs/toiture/fondations), ajoutée SOUS la couche translucide de scan de
// risque (zoneFillMeshes) sans y toucher — Three.js rend les objets
// opaques avant les transparents quel que soit l'ordre d'ajout à la scène,
// donc la texture apparaît "derrière" le halo coloré de risque, sans
// z-fighting ni changement du raycasting existant (cette couche n'est pas
// ajoutée à interactiveMeshes).
let structureMeshes = [];
// Portes/fenêtres/balcon réels (voir addOpenings) : simples meshes décor,
// même traitement que structureMeshes (non interactifs).
let openingMeshes = [];

function disposeHouse() {
  if (house) scene.remove(house);
  house = null; zoneGroups = {}; zoneFillMeshes = {}; interactiveMeshes = [];
  crackMesh = null; waterMesh = null; stainMeshes = {};
  labelSprites = {}; leaderLines = {}; zoneAnchors = {};
  structureMeshes = []; openingMeshes = [];
}

function registerFill(zoneName, fillMesh) {
  fillMesh.userData.zoneName = zoneName;
  zoneFillMeshes[zoneName].push(fillMesh);
  interactiveMeshes.push(fillMesh);
}

// Ajoute la couche opaque texturee (materiau reel) pour un volume donne.
// `geometry` est reutilisee telle quelle pour la couche de scan (aucune
// duplication de donnees) : computeVertexNormals est deja fait une fois par
// registerFill/addRawPart, appeler ceci AVANT ou APRES n'a pas d'incidence.
function addStructureLayer(group, geometry, texture) {
  const mat = new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(geometry, mat);
  group.add(mesh);
  structureMeshes.push(mesh);
  return mesh;
}

// ---------- 4a. EMPRISE RÉELLE (polygone BDNB) ----------
// `geometry.footprint` arrive deja en metres, dans le repere de la scene
// (x = Est, z = Sud, origine au centre du bati) : aucune reprojection ici,
// c'est `app/digital_twin/footprint.py` qui s'en charge cote backend.

function footprintPolygons(g) {
  const fp = g && g.footprint;
  if (!fp || !Array.isArray(fp.polygones)) return null;
  const polys = fp.polygones
    .map(p => ({
      ext: (p.exterieur || []).filter(pt => Array.isArray(pt) && pt.length >= 2).map(pt => [+pt[0], +pt[1]]),
      holes: (p.trous || []).map(t => t.filter(pt => Array.isArray(pt) && pt.length >= 2).map(pt => [+pt[0], +pt[1]])).filter(t => t.length >= 3)
    }))
    .filter(p => p.ext.length >= 3 && p.ext.every(pt => isFinite(pt[0]) && isFinite(pt[1])));
  return polys.length ? polys : null;
}

function polygonBounds(polys) {
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  polys.forEach(p => p.ext.forEach(([x, z]) => {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z);
  }));
  return { minX, maxX, minZ, maxZ, W: maxX - minX, D: maxZ - minZ };
}

// THREE.Shape vit dans le plan XY et s'extrude vers +Z. On construit donc la
// forme en (x, -z) puis on couche le mesh avec rotation.x = -90°, ce qui
// renvoie shape.y sur la scene z ET oriente l'extrusion vers le haut.
const SHAPE_ROT_X = -Math.PI / 2;
function toShape(ext, holes) {
  const shape = new THREE.Shape();
  ext.forEach((p, i) => i ? shape.lineTo(p[0], -p[1]) : shape.moveTo(p[0], -p[1]));
  shape.closePath();
  (holes || []).forEach(h => {
    const path = new THREE.Path();
    h.forEach((p, i) => i ? path.lineTo(p[0], -p[1]) : path.moveTo(p[0], -p[1]));
    path.closePath();
    shape.holes.push(path);
  });
  return shape;
}

// Dalle horizontale (fondations, plancher, toit-terrasse) suivant l'emprise.
function slabFromPolygons(polys, y, thickness) {
  const group = [];
  polys.forEach(p => {
    const geo = new THREE.ExtrudeGeometry(toShape(p.ext, p.holes), { depth: thickness, bevelEnabled: false });
    geo.rotateX(SHAPE_ROT_X);
    geo.translate(0, y, 0);
    group.push(geo);
  });
  return group;
}

// UV en METRES REELS (pas normalisees 0-1) : u = distance projetee sur l'axe
// a->b, v = hauteur. Les textures de materiau (getMaterialTexture) reglent
// leur propre `repeat` en consequence, ce qui les fait carreler a la bonne
// echelle quelle que soit la taille de la facade ou de l'etage.
function _uvAxis(a, b) {
  const dx = b[0] - a[0], dz = b[2] - a[2];
  const l = Math.hypot(dx, dz) || 1;
  return [dx / l, dz / l];
}
function _uvOf(p, origine, ux, uz) { return [(p[0] - origine[0]) * ux + (p[2] - origine[2]) * uz, p[1] - origine[1]]; }

// Variante 2D : `a`/`b` sont des points [x, z] du polygone (edgesByZone),
// PAS des sommets 3D [x, y, z] comme dans _uvAxis ci-dessus. Réutiliser
// _uvAxis ici lisait b[2]/a[2] (undefined sur un tableau à 2 éléments),
// donnait un axe non normalisé et plaçait portes/fenêtres hors du bâtiment
// (ex. x=334 sur un immeuble large de 45 m) — bug corrigé en distinguant
// clairement les deux cas plutôt qu'en partageant une seule fonction.
function _axis2D(a, b) {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const l = Math.hypot(dx, dz) || 1;
  return [dx / l, dz / l];
}

function quadsToGeometry(quads) {
  const verts = new Float32Array(quads.length * 18);
  const uvs = new Float32Array(quads.length * 12);
  quads.forEach((q, i) => {
    const [a, b, c, d] = q;
    verts.set([...a, ...b, ...c, ...a, ...c, ...d], i * 18);
    const [ux, uz] = _uvAxis(a, b);
    const uvA = _uvOf(a, a, ux, uz), uvB = _uvOf(b, a, ux, uz), uvC = _uvOf(c, a, ux, uz), uvD = _uvOf(d, a, ux, uz);
    uvs.set([...uvA, ...uvB, ...uvC, ...uvA, ...uvC, ...uvD], i * 12);
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.computeVertexNormals();
  return geo;
}

// Normale sortante d'une arete : le contour exterieur arrive en sens
// trigonometrique et les trous en sens horaire (garanti par le backend),
// donc (dz, -dx) pointe toujours vers l'exterieur de la matiere — y compris
// pour une cour interieure, ou elle pointe vers la cour.
function edgeNormal(p, q) {
  const dx = q[0] - p[0], dz = q[1] - p[1];
  const len = Math.hypot(dx, dz) || 1;
  return [dz / len, -dx / len];
}

function cardinalZone(normal) {
  const [nx, nz] = normal;
  if (Math.abs(nx) > Math.abs(nz)) return nx > 0 ? 'murs_est' : 'murs_ouest';
  return nz > 0 ? 'murs_sud' : 'murs_nord';
}

function ringEdges(ring) {
  return ring.map((p, i) => [p, ring[(i + 1) % ring.length]]);
}

function pointInRing(x, z, ring) {
  let inside = false;
  for (let i = 0, n = ring.length; i < n; i++) {
    const [x1, z1] = ring[i], [x2, z2] = ring[(i + 1) % n];
    if ((z1 > z) !== (z2 > z)) {
      const xCross = x1 + (z - z1) / (z2 - z1) * (x2 - x1);
      if (xCross > x) inside = !inside;
    }
  }
  return inside;
}

// Contour rentre d'une distance `d` (jointure en onglet). Sert a fabriquer
// une toiture a pans sur une emprise quelconque : le contour rentre devient
// le faitage, ce qui donne une croupe correcte sur un L ou un U la ou une
// simple boite ne savait produire que deux pans droits.
function insetRing(ring, d) {
  const n = ring.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    const prev = ring[(i - 1 + n) % n], cur = ring[i], next = ring[(i + 1) % n];
    const e1 = [cur[0] - prev[0], cur[1] - prev[1]];
    const e2 = [next[0] - cur[0], next[1] - cur[1]];
    const l1 = Math.hypot(e1[0], e1[1]), l2 = Math.hypot(e2[0], e2[1]);
    if (l1 < 1e-6 || l2 < 1e-6) return null;
    // normale rentrante = -(normale sortante)
    const n1 = [-e1[1] / l1, e1[0] / l1];
    const n2 = [-e2[1] / l2, e2[0] / l2];
    const bis = [n1[0] + n2[0], n1[1] + n2[1]];
    const bl = Math.hypot(bis[0], bis[1]);
    if (bl < 1e-6) return null;              // demi-tour : onglet indefini
    const m = [bis[0] / bl, bis[1] / bl];
    const cosHalf = n1[0] * m[0] + n1[1] * m[1];
    if (cosHalf < 0.2) return null;          // angle trop aigu : pic aberrant
    const scale = d / cosHalf;
    out.push([cur[0] + m[0] * scale, cur[1] + m[1] * scale]);
  }
  // Un contour rentre valide reste a l'interieur du contour d'origine ;
  // sinon l'emprise est trop etroite pour cette pente et on renonce.
  if (!out.every(([x, z]) => pointInRing(x, z, ring))) return null;
  return out;
}

function buildHouseFromFootprint(geometry, polys) {
  disposeHouse();
  const g = geometry || {};
  const bounds = polygonBounds(polys);
  const W = bounds.W, D = bounds.D;
  const floors = Math.max(1, Math.min(8, Math.round(g.floors_count ?? 1)));
  const levelH = clamp(g.hauteur_sous_plafond_m ?? 2.6, 2.0, 3.5);
  const roofShape = (g.roof_shape || 'deux_pans').toLowerCase();
  const penteDeg = clamp(g.pente_toit_deg ?? 35, 12, 55);
  const hasBasement = g.has_basement !== false;
  const estImmeuble = g.type_batiment === 'immeuble';

  house = new THREE.Group();
  scene.add(house);
  ZONE_NAMES.forEach(name => {
    const grp = new THREE.Group(); grp.name = name;
    house.add(grp); zoneGroups[name] = grp; zoneFillMeshes[name] = [];
  });

  const basementTopY = 0.4;
  const basementH = hasBasement ? 1.6 : 0.35;
  const basementCenterY = basementTopY - basementH / 2;
  const fondY = basementTopY + 0.15;
  const wallsStartY = basementTopY + 0.3;
  const eavesY = wallsStartY + floors * levelH;

  // -- textures de materiau reel (BDNB) : les fondations/sous-sol restent en
  // beton par convention (la BDNB ne donne pas de materiau de fondation
  // specifique — utiliser le materiau des murs serait une supposition, pas
  // une donnee).
  const wallTexture = getMaterialTexture('mur', g.materiau_mur);
  const roofTexture = getMaterialTexture('toit', g.materiau_toiture);
  const foundationTexture = getMaterialTexture('toit', 'beton');

  // -- sous-sol et fondations : extrusion de l'emprise reelle --
  slabFromPolygons(polys, basementTopY - basementH, basementH).forEach(geo => {
    addStructureLayer(zoneGroups.sous_sol, geo, foundationTexture);
    registerFill('sous_sol', addRawPart(zoneGroups.sous_sol, geo, 0x3fb950, 0.18));
  });
  slabFromPolygons(polys, fondY - 0.15, 0.3).forEach(geo => {
    addStructureLayer(zoneGroups.fondations, geo, foundationTexture);
    registerFill('fondations', addRawPart(zoneGroups.fondations, geo, 0x3fb950, 0.18));
  });

  // -- murs : une facade par arete, rattachee a sa zone cardinale --
  const wallQuads = {};       // zone -> etage -> quads
  // Aretes reelles par zone (independantes de l'etage) : servent a repartir
  // les ouvertures reelles (fenetres/porte) le long des vraies facades,
  // cf. addOpenings plus bas.
  const edgesByZone = {};
  ZONE_NAMES.filter(z => z.startsWith('murs_')).forEach(z => { wallQuads[z] = {}; edgesByZone[z] = []; });
  const anchorCandidates = {};

  polys.forEach(p => {
    const rings = [p.ext].concat(p.holes || []);
    rings.forEach(ring => {
      ringEdges(ring).forEach(([a, b]) => {
        const normal = edgeNormal(a, b);
        const zone = cardinalZone(normal);
        const longueur = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (longueur < 0.05) return;

        for (let i = 0; i < floors; i++) {
          const y0 = wallsStartY + i * levelH;
          const y1 = y0 + levelH;
          (wallQuads[zone][i] = wallQuads[zone][i] || []).push([
            [a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]]
          ]);
        }
        edgesByZone[zone].push({ a, b, normal, longueur });
        // La façade la plus longue de chaque orientation porte l'etiquette
        // et l'effet d'humidite : c'est la plus lisible a l'ecran.
        if (!anchorCandidates[zone] || longueur > anchorCandidates[zone].longueur) {
          anchorCandidates[zone] = {
            longueur,
            milieu: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
            normal
          };
        }
      });
    });
  });

  Object.entries(wallQuads).forEach(([zone, parEtage]) => {
    Object.values(parEtage).forEach(quads => {
      if (!quads.length) return;
      const geo = quadsToGeometry(quads);
      addStructureLayer(zoneGroups[zone], geo, wallTexture);
      registerFill(zone, addRawPart(zoneGroups[zone], geo, 0x3fb950, 0.16));
    });
  });

  Object.entries(anchorCandidates).forEach(([zone, info]) => {
    zoneAnchors[zone] = {
      position: new THREE.Vector3(info.milieu[0], wallsStartY + levelH / 2, info.milieu[1]),
      normal: new THREE.Vector3(info.normal[0], 0, info.normal[1])
    };
  });

  addOpenings(g, edgesByZone, { wallsStartY, levelH, floors });

  // -- planchers intermediaires : simple filaire suivant l'emprise --
  for (let i = 1; i < floors; i++) {
    const bandY = wallsStartY + i * levelH;
    polys.forEach(p => {
      [p.ext].concat(p.holes || []).forEach(ring => {
        const pts = ring.map(([x, z]) => new THREE.Vector3(x, bandY, z));
        pts.push(pts[0].clone());
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: WIRE_COLOR, transparent: true, opacity: 0.55 }));
        house.add(line);
      });
    });
  }

  // -- toiture --
  // Toit-terrasse pour les immeubles et les toits plats ; sinon, croupe
  // obtenue en rentrant le contour (voir insetRing). Une emprise a cour
  // interieure part aussi en terrasse : rentrer un contour troue n'a pas de
  // solution simple et fiable, et ces batis sont massivement en terrasse.
  const aCour = polys.some(p => (p.holes || []).length > 0);
  const toitPlat = estImmeuble || aCour || roofShape === 'plat' || roofShape === 'toit_plat';
  let ridgeY = eavesY;

  if (toitPlat) {
    slabFromPolygons(polys, eavesY, 0.25).forEach(geo => {
      addStructureLayer(zoneGroups.toiture, geo, foundationTexture); // etancheite terrasse : meme rendu neutre que le beton
      registerFill('toiture', addRawPart(zoneGroups.toiture, geo, 0x3fb950, 0.16));
    });
    ridgeY = eavesY + 0.25;
  } else {
    const penteRad = penteDeg * Math.PI / 180;
    polys.forEach(p => {
      const inset = Math.min(2.0, Math.max(0.8, Math.min(W, D) * 0.18));
      let creux = null, retenu = inset;
      for (let essai = 0; essai < 4 && !creux; essai++) {
        retenu = inset / Math.pow(2, essai);
        creux = insetRing(p.ext, retenu);
      }
      const rise = (creux ? retenu : 0) * Math.tan(penteRad);
      const sommetY = eavesY + rise;
      ridgeY = Math.max(ridgeY, sommetY);

      if (!creux) {
        // Emprise trop etroite ou trop torturee pour une croupe : terrasse.
        slabFromPolygons([p], eavesY, 0.25).forEach(geo => {
          addStructureLayer(zoneGroups.toiture, geo, foundationTexture);
          registerFill('toiture', addRawPart(zoneGroups.toiture, geo, 0x3fb950, 0.16));
        });
        return;
      }

      const pans = ringEdges(p.ext).map(([a, b], i) => {
        const j = (i + 1) % p.ext.length;
        return [
          [a[0], eavesY, a[1]], [b[0], eavesY, b[1]],
          [creux[j][0], sommetY, creux[j][1]], [creux[i][0], sommetY, creux[i][1]]
        ];
      });
      const roofGeo = quadsToGeometry(pans);
      addStructureLayer(zoneGroups.toiture, roofGeo, roofTexture);
      registerFill('toiture', addRawPart(zoneGroups.toiture, roofGeo, 0x3fb950, 0.16));

      const faitage = new THREE.ExtrudeGeometry(toShape(creux, []), { depth: 0.06, bevelEnabled: false });
      faitage.rotateX(SHAPE_ROT_X);
      faitage.translate(0, sommetY, 0);
      addStructureLayer(zoneGroups.toiture, faitage, roofTexture);
      registerFill('toiture', addRawPart(zoneGroups.toiture, faitage, 0x3fb950, 0.16));
    });
  }

  buildAnnexes(g, {
    minX: bounds.minX, maxX: bounds.maxX, minZ: bounds.minZ, maxZ: bounds.maxZ,
    W, D, wallsStartY, basementTopY
  });

  // Pas de rotation : l'orientation reelle est deja portee par les
  // coordonnees du polygone (contrairement au mode boite, ou elle doit etre
  // rejouee via orientation_deg).
  houseDims = { W, D, floors, levelH, wallsStartY, eavesY, ridgeY, basementCenterY, fondY, bounds };
}

// ---------- 4b. OUVERTURES RÉELLES (porte / fenêtres / balcon) ----------
//
// Couleur de menuiserie : seul signal disponible est le MATÉRIAU réel
// (`type_materiaux_menuiserie` — bois/pvc/alu/métal), pas une couleur RAL.
// La couleur choisie ici illustre le matériau réel, elle ne l'invente pas.
function menuiserieColor(materiauBrut) {
  const m = (materiauBrut || '').toLowerCase();
  if (m.includes('bois')) return 0x6b4a30;
  if (m.includes('pvc')) return 0xe8e6df;
  if (m.includes('alu') || m.includes('métal') || m.includes('metal')) return 0x5a6068;
  return 0xcfcac0; // materiau non renseigne : cadre neutre, pas une couleur devinee
}

// Fenêtre unique : vitrage sombre + cadre. `edgePos` est l'abscisse (mètres)
// depuis `a` le long de l'arête ; `normal` oriente le plan vers l'extérieur.
// `zone` : groupe (zoneGroups[zone]) auquel accrocher la fenêtre — PAS
// `house` directement. Au survol/clic, l'effet de mise en évidence
// (hoveredGroup.scale.set(1.02,...), cf. section raycasting) scale le
// GROUPE DE ZONE du mur, pas toute la maison ; une fenêtre ajoutée à
// `house` restait donc figée en place pendant que le mur se déplaçait
// légèrement autour de l'origine, et semblait se détacher ou disparaître.
// L'attacher au même groupe que le mur la fait bouger avec lui.
function addWindowMesh(zone, a, b, normal, edgePos, y, largeur, hauteur, cadreColor) {
  const [ux, uz] = _axis2D(a, b);
  const cx = a[0] + ux * edgePos, cz = a[1] + uz * edgePos;
  const group = new THREE.Group();
  group.position.set(cx, y, cz);
  group.lookAt(cx + normal[0], y, cz + normal[1]);

  const vitrage = new THREE.Mesh(
    new THREE.PlaneGeometry(largeur, hauteur),
    new THREE.MeshBasicMaterial({ color: 0x1a2430, side: THREE.DoubleSide })
  );
  vitrage.position.z = 0.03;
  group.add(vitrage);

  const cadre = new THREE.Mesh(
    new THREE.PlaneGeometry(largeur * 1.14, hauteur * 1.1),
    new THREE.MeshBasicMaterial({ color: cadreColor, side: THREE.DoubleSide })
  );
  // Cadre en retrait (z=0.025 < vitrage z=0.03) : la profondeur reelle fait
  // la superposition visuelle, pas l'ordre d'ajout au groupe.
  cadre.position.z = 0.025;
  group.add(cadre);

  zoneGroups[zone].add(group);
  openingMeshes.push(group);
}

// Porte d'entrée : placée au milieu de la plus longue arête de la façade
// orientée rue (`entree_facade`), au rez-de-chaussée. Aucune donnée BDNB ne
// précise le matériau/la couleur de porte — teinte neutre assumée, jamais
// présentée comme une donnée réelle (contrairement au côté choisi, lui basé
// sur le point d'adresse géocodé).
// `zone` : meme raison que dans addWindowMesh ci-dessus — la porte doit
// bouger avec le groupe de son mur au survol/clic, pas rester figee.
function addDoorMesh(zone, arete, wallsStartY) {
  const { a, b, normal } = arete;
  const largeur = 1.0, hauteur = 2.05;
  const milieu = Math.hypot(b[0] - a[0], b[1] - a[1]) / 2;
  const [ux, uz] = _axis2D(a, b);
  const cx = a[0] + ux * milieu, cz = a[1] + uz * milieu;
  const group = new THREE.Group();
  group.position.set(cx, wallsStartY + hauteur / 2, cz);
  group.lookAt(cx + normal[0], wallsStartY + hauteur / 2, cz + normal[1]);

  const porte = new THREE.Mesh(
    new THREE.PlaneGeometry(largeur, hauteur),
    new THREE.MeshBasicMaterial({ color: 0x4a3323, side: THREE.DoubleSide })
  );
  porte.position.z = 0.03;
  group.add(porte);

  const cadre = new THREE.Mesh(
    new THREE.PlaneGeometry(largeur * 1.16, hauteur * 1.06),
    new THREE.MeshBasicMaterial({ color: 0xe8e6df, side: THREE.DoubleSide })
  );
  cadre.position.z = 0.02;
  group.add(cadre);

  zoneGroups[zone].add(group);
  openingMeshes.push(group);
}

// `zone` : idem — dalle et garde-corps doivent suivre le mur porteur.
function addBalconyMesh(zone, arete, y) {
  const { a, b, normal } = arete;
  const largeur = Math.min(2.4, Math.hypot(b[0] - a[0], b[1] - a[1]) * 0.7);
  const milieu = Math.hypot(b[0] - a[0], b[1] - a[1]) / 2;
  const [ux, uz] = _axis2D(a, b);
  const cx = a[0] + ux * milieu, cz = a[1] + uz * milieu;
  const profondeur = 0.9;
  const grp = zoneGroups[zone];

  const dalle = new THREE.Mesh(
    new THREE.BoxGeometry(largeur, 0.08, profondeur),
    new THREE.MeshBasicMaterial({ color: 0x9a978c })
  );
  dalle.position.set(cx + normal[0] * profondeur / 2, y - 0.04, cz + normal[1] * profondeur / 2);
  grp.add(dalle); openingMeshes.push(dalle);

  const garde_corps = new THREE.Mesh(
    new THREE.BoxGeometry(largeur, 0.9, 0.04),
    new THREE.MeshBasicMaterial({ color: 0x2c3238 })
  );
  garde_corps.position.set(cx + normal[0] * profondeur, y + 0.45, cz + normal[1] * profondeur);
  garde_corps.lookAt(garde_corps.position.clone().add(new THREE.Vector3(normal[0], 0, normal[1])));
  grp.add(garde_corps); openingMeshes.push(garde_corps);
}

// Point d'entrée : porte (côté rue, si déterminable) + fenêtres (uniquement
// si le DPE de ce bien renseigne les baies vitrées) + balcon (si
// `presence_balcon` est réellement vrai). Aucun de ces trois éléments
// n'apparaît quand la donnée qui le justifie est absente — pas de
// génération par défaut.
function addOpenings(g, edgesByZone, dims) {
  const { wallsStartY, levelH, floors } = dims;
  const ouvertures = g.ouvertures || {};
  const entreeFacade = g.entree_facade || null;
  const cadreColor = menuiserieColor(ouvertures.menuiserie_materiau);

  if (entreeFacade && edgesByZone[entreeFacade] && edgesByZone[entreeFacade].length) {
    const aretes = edgesByZone[entreeFacade];
    const arete = aretes.reduce((best, e) => (e.longueur > best.longueur ? e : best), aretes[0]);
    addDoorMesh(entreeFacade, arete, wallsStartY);
  }

  const facadesVitrage = ouvertures.disponible ? new Set(ouvertures.facades_avec_vitrage || []) : new Set();

  if (facadesVitrage.size) {
    // Taille de fenêtre TYPE (1.2 x 1.4 m, ratio résidentiel courant) : seule
    // valeur non issue de la donnée du bâtiment dans ce calcul — la BDNB
    // fournit un RATIO de surface vitrée, pas une taille ni un nombre de
    // fenêtres. Assumée et documentée ici, pas mesurée pour ce bien précis.
    const FENETRE_L = 1.2, FENETRE_H = 1.4, MARGE = 0.5, ESPACEMENT_MIN = 1.4;

    const slots = []; // { zone, edge, floor }
    let longueurPonderee = 0;
    facadesVitrage.forEach(zone => {
      (edgesByZone[zone] || []).forEach(edge => {
        for (let floor = 0; floor < floors; floor++) {
          if (zone === entreeFacade && floor === 0) continue; // rez-de-chaussée réservé à la porte
          if (edge.longueur < MARGE * 2 + 0.3) continue;
          slots.push({ zone, edge, floor });
          longueurPonderee += edge.longueur;
        }
      });
    });
    if (slots.length && longueurPonderee > 0) {
      const ratio = ouvertures.ratio_vitrage ?? 0.15;
      const surfaceMurTotale = longueurPonderee * levelH;
      const surfaceVitreeCible = surfaceMurTotale * ratio;
      const densiteParMetre = (surfaceVitreeCible / (FENETRE_L * FENETRE_H)) / longueurPonderee;

      slots.forEach(({ zone, edge, floor }) => {
        const maxParEspacement = Math.floor((edge.longueur - 2 * MARGE) / ESPACEMENT_MIN) + 1;
        const nb = Math.max(0, Math.min(Math.round(edge.longueur * densiteParMetre), Math.max(1, maxParEspacement)));
        if (!nb) return;
        const y = wallsStartY + floor * levelH + levelH * 0.55;
        for (let k = 0; k < nb; k++) {
          const t = nb === 1 ? 0.5 : (k + 0.5) / nb;
          const pos = MARGE + t * (edge.longueur - 2 * MARGE);
          addWindowMesh(zone, edge.a, edge.b, edge.normal, pos, y, FENETRE_L, FENETRE_H, cadreColor);
        }
      });
    }
  }

  if (ouvertures.has_balcony === true) {
    // Aucune donnée BDNB ne précise la façade/l'étage du balcon : on le
    // rattache à la façade rue si elle a aussi des fenêtres réelles, sinon
    // à la première façade vitrée connue — approximation assumée, pas une
    // donnée par bâtiment.
    const zoneBalcon = (entreeFacade && facadesVitrage.has(entreeFacade))
      ? entreeFacade
      : (facadesVitrage.size ? Array.from(facadesVitrage)[0] : null);
    if (zoneBalcon && edgesByZone[zoneBalcon] && edgesByZone[zoneBalcon].length && floors >= 2) {
      const aretes = edgesByZone[zoneBalcon];
      const arete = aretes.reduce((best, e) => (e.longueur > best.longueur ? e : best), aretes[0]);
      const yBalcon = wallsStartY + (floors - 1) * levelH;
      addBalconyMesh(zoneBalcon, arete, yBalcon);
    }
  }
}

// Garage et jardin : decor commun aux deux modes de construction.
function buildAnnexes(g, dims) {
  const hasGarage = !!g.has_garage;
  const garagePos = g.garage_position || 'ouest';
  const hasGarden = !!g.has_garden;
  const decor = new THREE.Group(); house.add(decor);

  function addDecorPanel(geometry, position) {
    const fill = new THREE.Mesh(geometry, makeFillMat(0x5fb2ff, 0.22));
    fill.position.copy(position); decor.add(fill);
    const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), makeWireMat());
    wire.position.copy(position); decor.add(wire);
  }

  if (hasGarage) {
    const garageW = 3.0, garageD = 4.2, garageH = 2.4;
    let gx = 0, gz = 0;
    if (garagePos === 'ouest') gx = dims.minX - garageW / 2 - 0.05;
    else if (garagePos === 'est') gx = dims.maxX + garageW / 2 + 0.05;
    else if (garagePos === 'nord') gz = dims.minZ - garageD / 2 - 0.05;
    else gz = dims.maxZ + garageD / 2 + 0.05;
    const baseY = dims.wallsStartY - 0.3;
    addDecorPanel(new THREE.BoxGeometry(garageW, garageH, garageD), new THREE.Vector3(gx, baseY + garageH / 2, gz));
    addDecorPanel(new THREE.BoxGeometry(garageW + 0.3, 0.1, garageD + 0.3), new THREE.Vector3(gx, baseY + garageH + 0.05, gz));
  }

  if (hasGarden) {
    const side = hasGarage && garagePos === 'ouest' ? 1 : -1;
    const size = Math.sqrt(clamp(g.garden_surface_m2 ?? 100, 20, 2000));
    const gardenMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size),
      new THREE.MeshBasicMaterial({ color: 0x3fb950, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
    );
    gardenMesh.rotation.x = -Math.PI / 2;
    const x = side > 0 ? dims.maxX + size / 2 + 1.2 : dims.minX - size / 2 - 1.2;
    gardenMesh.position.set(x, 0.02, (dims.minZ + dims.maxZ) / 2);
    house.add(gardenMesh);
  }
}

function buildHouse(geometry) {
  const polys = footprintPolygons(geometry);
  if (polys) buildHouseFromFootprint(geometry, polys);
  else buildHouseFromBox(geometry);
  // buildLabels() desactive : les etiquettes rectangulaires noires flottant
  // au-dessus de la maison masquaient une partie du modele et faisaient
  // double emploi avec la couleur de risque deja portee par chaque zone.
  // Le score/detail de zone reste accessible au clic (cf. showZonePanel).
  buildEffectMeshes();
}

function buildHouseFromBox(geometry) {
  disposeHouse();
  const g = geometry || {};
  const W = clamp(g.largeur_m ?? 8, 3, 35);
  const D = clamp(g.longueur_m ?? 8, 3, 35);
  const floors = Math.max(1, Math.min(6, Math.round(g.floors_count ?? 1)));
  const levelH = clamp(g.hauteur_sous_plafond_m ?? 2.6, 2.0, 3.5);
  const roofShape = (g.roof_shape || 'deux_pans').toLowerCase();
  const penteDeg = clamp(g.pente_toit_deg ?? 35, 12, 55);
  const hasBasement = g.has_basement !== false;
  const hasGarage = !!g.has_garage;
  const garagePos = g.garage_position || 'ouest';
  const hasGarden = !!g.has_garden;
  const orientationDeg = g.orientation_deg ?? 0;

  house = new THREE.Group();
  scene.add(house);

  ZONE_NAMES.forEach(name => {
    const grp = new THREE.Group(); grp.name = name;
    house.add(grp); zoneGroups[name] = grp; zoneFillMeshes[name] = [];
  });

  const basementTopY = 0.4;
  const basementH = hasBasement ? 1.6 : 0.35;
  const basementCenterY = basementTopY - basementH / 2;
  const fondY = basementTopY + 0.15;
  const wallsStartY = basementTopY + 0.3;
  const eavesY = wallsStartY + floors * levelH;

  // Textures de materiau reel : memes textures que le mode emprise reelle,
  // mais CLONEES (boxMaterialTexture) pour regler leur `repeat` sur les UV
  // 0..1 par defaut de BoxGeometry sans modifier l'instance partagee (dont
  // le repeat est calibre pour des UV en metres, cf. quadsToGeometry).
  // Fenetres/porte non generees en mode boite : sans polygone reel, il n'y
  // a pas d'arete de facade fiable a laquelle les rattacher (voir
  // buildHouse plus haut, qui reserve ce mode aux biens sans geometrie
  // BDNB exploitable — un cas ou les champs DPE sont eux aussi rarement
  // disponibles en pratique).
  const boxWallTexture = boxMaterialTexture('mur', g.materiau_mur, W, levelH);
  const boxRoofTexture = boxMaterialTexture('toit', g.materiau_toiture, W, D);
  const boxFoundationTexture = boxMaterialTexture('toit', 'beton', W, D);

  const sousSolGeo = new THREE.BoxGeometry(W + 0.3, basementH, D + 0.3);
  addStructureLayer(zoneGroups.sous_sol, sousSolGeo, boxFoundationTexture).position.set(0, basementCenterY, 0);
  registerFill("sous_sol", addPart(zoneGroups.sous_sol,
    sousSolGeo, new THREE.Vector3(0, basementCenterY, 0), 0x3fb950, 0.18));

  const fondationsGeo = new THREE.BoxGeometry(W + 0.4, 0.3, D + 0.4);
  addStructureLayer(zoneGroups.fondations, fondationsGeo, boxFoundationTexture).position.set(0, fondY, 0);
  registerFill("fondations", addPart(zoneGroups.fondations,
    fondationsGeo, new THREE.Vector3(0, fondY, 0), 0x3fb950, 0.18));

  const wallThickness = 0.2;
  function buildWallLevels(zoneName, sizeFn, posFn) {
    for (let i = 0; i < floors; i++) {
      const y = wallsStartY + i * levelH + levelH / 2;
      const geo = sizeFn();
      const structMesh = addStructureLayer(zoneGroups[zoneName], geo, boxWallTexture);
      structMesh.position.copy(posFn(y));
      registerFill(zoneName, addPart(zoneGroups[zoneName], geo, posFn(y), 0x3fb950, 0.16));
    }
  }
  buildWallLevels("murs_nord", () => new THREE.BoxGeometry(W, levelH, wallThickness), y => new THREE.Vector3(0, y, -D / 2));
  buildWallLevels("murs_sud",  () => new THREE.BoxGeometry(W, levelH, wallThickness), y => new THREE.Vector3(0, y, D / 2));
  buildWallLevels("murs_est",  () => new THREE.BoxGeometry(wallThickness, levelH, D), y => new THREE.Vector3(W / 2, y, 0));
  buildWallLevels("murs_ouest",() => new THREE.BoxGeometry(wallThickness, levelH, D), y => new THREE.Vector3(-W / 2, y, 0));

  for (let i = 1; i < floors; i++) {
    const bandY = wallsStartY + i * levelH;
    const bandGeo = new THREE.BoxGeometry(W + 0.15, 0.06, D + 0.15);
    const bandFill = new THREE.Mesh(bandGeo, makeFillMat(0x5fb2ff, 0.25));
    bandFill.position.set(0, bandY, 0); house.add(bandFill);
    const bandWire = new THREE.LineSegments(new THREE.EdgesGeometry(bandGeo), makeWireMat());
    bandWire.position.copy(bandFill.position); house.add(bandWire);
  }

  const roofOverhang = 0.35;
  const roofHalfSpan = D / 2 + roofOverhang;
  let ridgeY = eavesY;
  // quadGeo/triGeo portent deja des UV en metres (comme quadsToGeometry) :
  // ces panneaux utilisent directement la texture partagee, pas le clone
  // "boite" ci-dessus (reserve aux BoxGeometry, UV 0..1).
  const roofTextureMeters = getMaterialTexture('toit', g.materiau_toiture);

  if (roofShape === 'plat' || roofShape === 'toit_plat') {
    const slabGeo = new THREE.BoxGeometry(W + 0.6, 0.25, D + 0.6);
    addStructureLayer(zoneGroups.toiture, slabGeo, boxRoofTexture).position.set(0, eavesY + 0.15, 0);
    registerFill("toiture", addPart(zoneGroups.toiture, slabGeo, new THREE.Vector3(0, eavesY + 0.15, 0), 0x3fb950, 0.16));
    ridgeY = eavesY + 0.25;
  } else if (roofShape === 'quatre_pans' || roofShape === 'croupe') {
    const penteRad = penteDeg * Math.PI / 180;
    const rise = roofHalfSpan * Math.tan(penteRad);
    ridgeY = eavesY + rise;
    const ridgeLen = Math.max(0.6, W - D);
    const ov = roofOverhang;
    const NW = [-(W / 2 + ov), eavesY, -(D / 2 + ov)], NE = [(W / 2 + ov), eavesY, -(D / 2 + ov)];
    const SW = [-(W / 2 + ov), eavesY, (D / 2 + ov)], SE = [(W / 2 + ov), eavesY, (D / 2 + ov)];
    const Rw = [-ridgeLen / 2, ridgeY, 0], Re = [ridgeLen / 2, ridgeY, 0];
    [quadGeo(NW, NE, Re, Rw), quadGeo(SE, SW, Rw, Re), triGeo(NW, SW, Rw), triGeo(SE, NE, Re)].forEach(geo => {
      addStructureLayer(zoneGroups.toiture, geo, roofTextureMeters);
      registerFill("toiture", addRawPart(zoneGroups.toiture, geo, 0x3fb950, 0.16));
    });
  } else {
    const penteRad = penteDeg * Math.PI / 180;
    const rise = roofHalfSpan * Math.tan(penteRad);
    ridgeY = eavesY + rise;
    const roofSlopeLength = Math.sqrt(roofHalfSpan * roofHalfSpan + rise * rise);
    const roofAngle = Math.atan2(rise, roofHalfSpan);
    const pentTexture = boxMaterialTexture('toit', g.materiau_toiture, W + 0.7, roofSlopeLength);
    function makeSlope(sign) {
      const geo = new THREE.BoxGeometry(W + 0.7, 0.12, roofSlopeLength);
      const rotation = sign * roofAngle;
      const position = new THREE.Vector3(0, (eavesY + ridgeY) / 2, sign * (roofHalfSpan / 2));

      const structMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: pentTexture, side: THREE.DoubleSide }));
      structMesh.rotation.x = rotation; structMesh.position.copy(position);
      zoneGroups.toiture.add(structMesh); structureMeshes.push(structMesh);

      const mesh = new THREE.Mesh(geo, makeFillMat(0x3fb950, 0.16));
      mesh.rotation.x = rotation; mesh.position.copy(position);
      zoneGroups.toiture.add(mesh);
      const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat());
      wire.rotation.copy(mesh.rotation); wire.position.copy(mesh.position);
      zoneGroups.toiture.add(wire);
      return mesh;
    }
    registerFill("toiture", makeSlope(1));
    registerFill("toiture", makeSlope(-1));
    function makeGable(zSide) {
      const halfW = W / 2;
      const geo = triGeo([-halfW, eavesY, zSide], [halfW, eavesY, zSide], [0, ridgeY, zSide]);
      addStructureLayer(zoneGroups.toiture, geo, roofTextureMeters);
      registerFill("toiture", addRawPart(zoneGroups.toiture, geo, 0x3fb950, 0.16));
    }
    makeGable(-D / 2); makeGable(D / 2);
  }

  const decor = new THREE.Group(); house.add(decor);
  function addDecorPanel(geometry, position, rotationY) {
    const fill = new THREE.Mesh(geometry, makeFillMat(0x5fb2ff, 0.22));
    fill.position.copy(position); if (rotationY) fill.rotation.y = rotationY;
    decor.add(fill);
    const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), makeWireMat());
    wire.position.copy(position); if (rotationY) wire.rotation.y = rotationY;
    decor.add(wire);
  }
  for (let i = 0; i < floors; i++) {
    const y = wallsStartY + i * levelH + levelH / 2;
    [-W * 0.22, W * 0.22].forEach(x => addDecorPanel(new THREE.BoxGeometry(0.9, levelH * 0.42, 0.06), new THREE.Vector3(x, y, D / 2 + 0.02)));
  }
  addDecorPanel(new THREE.BoxGeometry(0.9, 1.9, 0.06), new THREE.Vector3(0, wallsStartY - 0.3 + 1.0, D / 2 + 0.02));
  if (hasBasement) {
    [-W * 0.28, W * 0.28].forEach(x => addDecorPanel(new THREE.BoxGeometry(0.6, 0.35, 0.06), new THREE.Vector3(x, basementTopY - 0.25, D / 2 + 0.16)));
  }
  if (hasGarage) {
    const garageW = 3.0, garageD = 4.2, garageH = 2.4;
    let gx = 0, gz = 0;
    if (garagePos === 'ouest') { gx = -W / 2 - garageW / 2 - 0.05; }
    else if (garagePos === 'est') { gx = W / 2 + garageW / 2 + 0.05; }
    else if (garagePos === 'nord') { gz = -D / 2 - garageD / 2 - 0.05; }
    else { gz = D / 2 + garageD / 2 + 0.05; }
    addDecorPanel(new THREE.BoxGeometry(garageW, garageH, garageD), new THREE.Vector3(gx, wallsStartY - 0.3 + garageH / 2, gz));
    addDecorPanel(new THREE.BoxGeometry(garageW + 0.3, 0.1, garageD + 0.3), new THREE.Vector3(gx, wallsStartY - 0.3 + garageH + 0.05, gz));
  }
  if (hasGarden) {
    const side = hasGarage && (garagePos === 'ouest') ? 1 : -1;
    const size = Math.sqrt(clamp(g.garden_surface_m2 ?? 100, 20, 2000));
    const gardenGeo = new THREE.PlaneGeometry(size, size);
    const gardenMat = new THREE.MeshBasicMaterial({ color: 0x3fb950, transparent: true, opacity: 0.08, side: THREE.DoubleSide });
    const gardenMesh = new THREE.Mesh(gardenGeo, gardenMat);
    gardenMesh.rotation.x = -Math.PI / 2;
    gardenMesh.position.set(side * (W / 2 + size / 2 + 1.2), 0.02, 0);
    house.add(gardenMesh);
  }

  house.rotation.y = orientationDeg * Math.PI / 180;

  houseDims = { W, D, floors, levelH, wallsStartY, eavesY, ridgeY, basementCenterY, fondY };
}

function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
function quadGeo(a, b, c, d) {
  const geo = new THREE.BufferGeometry();
  const verts = new Float32Array([...a, ...b, ...c, ...a, ...c, ...d]);
  geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
  const [ux, uz] = _uvAxis(a, b);
  const uvA = _uvOf(a, a, ux, uz), uvB = _uvOf(b, a, ux, uz), uvC = _uvOf(c, a, ux, uz), uvD = _uvOf(d, a, ux, uz);
  geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([...uvA, ...uvB, ...uvC, ...uvA, ...uvC, ...uvD]), 2));
  return geo;
}
function triGeo(a, b, c) {
  const geo = new THREE.BufferGeometry();
  const verts = new Float32Array([...a, ...b, ...c]);
  geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
  const [ux, uz] = _uvAxis(a, b);
  const uvA = _uvOf(a, a, ux, uz), uvB = _uvOf(b, a, ux, uz), uvC = _uvOf(c, a, ux, uz);
  geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([...uvA, ...uvB, ...uvC]), 2));
  return geo;
}

// ---------- 5. EFFETS VISUELS PILOTÉS PAR LE RISQUE ----------
function buildEffectMeshes() {
  const { W, D, fondY, basementCenterY, bounds } = houseDims;
  // En mode emprise reelle, le bati n'est pas centre sur l'origine : les
  // effets doivent se caler sur ses bornes, pas sur ±W/2.
  const centreX = bounds ? (bounds.minX + bounds.maxX) / 2 : 0;
  const faceSudZ = bounds ? bounds.maxZ : D / 2;

  const crackGeo = new THREE.PlaneGeometry(W * 0.8, 0.5);
  const crackMat = new THREE.MeshBasicMaterial({ map: crackTextures[1], transparent: true, opacity: 0, depthWrite: false });
  crackMesh = new THREE.Mesh(crackGeo, crackMat);
  crackMesh.position.set(centreX, fondY, faceSudZ + 0.22);
  house.add(crackMesh);

  const waterGeo = new THREE.CircleGeometry(Math.max(W, D) * 0.9, 48);
  const waterMat = new THREE.MeshBasicMaterial({ color: 0x2fa9ff, transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false });
  waterMesh = new THREE.Mesh(waterGeo, waterMat);
  waterMesh.rotation.x = -Math.PI / 2;
  waterMesh.position.x = centreX;
  waterMesh.position.z = bounds ? (bounds.minZ + bounds.maxZ) / 2 : 0;
  waterMesh.position.y = basementCenterY - 5;
  waterMesh.userData.baseY = basementCenterY;
  waterMesh.userData.targetRatio = 0;
  house.add(waterMesh);

  stainMeshes = {};
  const wallY = houseDims.wallsStartY + houseDims.levelH / 2;
  const stainDefs = {
    murs_nord: { pos: new THREE.Vector3(centreX, wallY, (bounds ? bounds.minZ : -D / 2) - 0.03), rot: 0 },
    murs_sud:  { pos: new THREE.Vector3(centreX, wallY, (bounds ? bounds.maxZ : D / 2) + 0.03), rot: 0 },
    murs_est:  { pos: new THREE.Vector3((bounds ? bounds.maxX : W / 2) + 0.03, wallY, 0), rot: Math.PI / 2 },
    murs_ouest:{ pos: new THREE.Vector3((bounds ? bounds.minX : -W / 2) - 0.03, wallY, 0), rot: Math.PI / 2 }
  };
  Object.entries(stainDefs).forEach(([zone, def]) => {
    const geo = new THREE.PlaneGeometry(1.6, 1.6);
    const mat = new THREE.MeshBasicMaterial({ map: stainTexture, transparent: true, opacity: 0, depthWrite: false });
    const mesh = new THREE.Mesh(geo, mat);
    // Sur une emprise reelle, la façade retenue est celle effectivement
    // construite pour cette orientation : l'aureole se colle dessus, avec
    // sa vraie normale, plutot que sur une face de boite qui n'existe pas.
    const ancre = zoneAnchors[zone];
    if (ancre) {
      mesh.position.copy(ancre.position).addScaledVector(ancre.normal, 0.04);
      mesh.lookAt(mesh.position.clone().add(ancre.normal));
    } else {
      mesh.position.copy(def.pos); mesh.rotation.y = def.rot;
    }
    house.add(mesh);
    stainMeshes[zone] = mesh;
  });
}

function applyZoneEffect(zoneName, score) {
  const effect = mapRiskToEffect(zoneName, score);
  if (zoneName === "fondations" && crackMesh) {
    crackMesh.material.opacity = effect.crackOpacity || 0;
    crackMesh.material.map = crackTextures[Math.max(1, effect.crackLayers || 1)];
    crackMesh.material.needsUpdate = true;
  }
  if (zoneName === "sous_sol" && waterMesh) {
    waterMesh.userData.targetRatio = effect.waterHeightRatio || 0;
  }
  if (zoneName.startsWith("murs_") && stainMeshes[zoneName]) {
    stainMeshes[zoneName].material.opacity = effect.humidityOpacity || 0;
  }
}

const maxWaterRise = 2.4;
function animateEffects(dt, elapsed) {
  if (waterMesh) {
    const target = waterMesh.userData.baseY + waterMesh.userData.targetRatio * maxWaterRise;
    const bob = waterMesh.userData.targetRatio > 0.01 ? Math.sin(elapsed * 1.4) * 0.04 : 0;
    const hiddenY = waterMesh.userData.baseY - 5;
    const wantedY = waterMesh.userData.targetRatio > 0.01 ? target + bob : hiddenY;
    waterMesh.position.y += (wantedY - waterMesh.position.y) * 0.08;
  }
}

// ---------- 6. SCORE -> COULEUR + LABELS ----------
function scoreToColor(score) {
  if (score < 30) return 0x3fb950;
  if (score < 60) return 0xd29922;
  if (score < 80) return 0xdb6d28;
  return 0xda3633;
}
const ROOF_WEAR_COLOR = new THREE.Color(0x8a5a2b);
function animateColor(mesh, targetHex, duration = 500) {
  const mat = mesh.material;
  const startColor = mat.color.clone();
  const targetColor = new THREE.Color(targetHex);
  const startTime = performance.now();
  function step(now) {
    const t = Math.min((now - startTime) / duration, 1);
    mat.color.lerpColors(startColor, targetColor, t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
function updateZoneColor(zoneName, score, animated = true) {
  const meshes = zoneFillMeshes[zoneName];
  if (!meshes || !meshes.length) return;
  let color = new THREE.Color(scoreToColor(score));
  if (zoneName === 'toiture') {
    const wear = mapRiskToEffect('toiture', score).tileWear || 0;
    color = color.clone().lerp(ROOF_WEAR_COLOR, wear * 0.7);
  }
  const targetHex = color.getHex();
  meshes.forEach(m => animated ? animateColor(m, targetHex) : m.material.color.set(targetHex));
  updateZoneLabel(zoneName, score);
  applyZoneEffect(zoneName, score);
}

function buildLabels() {
  const { W, D, wallsStartY, levelH, floors, ridgeY, basementCenterY, bounds } = houseDims;
  const topY = wallsStartY + floors * levelH;
  const minX = bounds ? bounds.minX : -W / 2, maxX = bounds ? bounds.maxX : W / 2;
  const minZ = bounds ? bounds.minZ : -D / 2, maxZ = bounds ? bounds.maxZ : D / 2;
  const centreX = (minX + maxX) / 2, centreZ = (minZ + maxZ) / 2;
  const anchors = {
    fondations: new THREE.Vector3(maxX + 0.3, houseDims.fondY, maxZ + 0.3),
    murs_nord:  new THREE.Vector3(centreX, topY - levelH / 2, minZ),
    murs_sud:   new THREE.Vector3(centreX, topY - levelH / 2, maxZ),
    murs_est:   new THREE.Vector3(maxX, wallsStartY + levelH / 2, centreZ),
    murs_ouest: new THREE.Vector3(minX, wallsStartY + levelH / 2, centreZ),
    toiture:    new THREE.Vector3(centreX, ridgeY, centreZ),
    sous_sol:   new THREE.Vector3(minX - 0.3, basementCenterY, maxZ + 0.3)
  };
  // Sur une emprise reelle, on accroche l'etiquette de façade au mur
  // effectivement construit pour cette orientation (le milieu geometrique
  // peut tomber dans le vide, par exemple dans le creux d'un L).
  Object.keys(zoneAnchors).forEach(zone => {
    if (anchors[zone]) anchors[zone] = zoneAnchors[zone].position.clone().setY(anchors[zone].y);
  });
  const offsets = {
    fondations: new THREE.Vector3(1.8, 0.6, 1.8), murs_nord: new THREE.Vector3(0, 1.6, -1.4),
    murs_sud: new THREE.Vector3(0, 1.6, 1.4), murs_est: new THREE.Vector3(2.4, 1.2, 0),
    murs_ouest: new THREE.Vector3(-2.4, 1.2, 0), toiture: new THREE.Vector3(0, 1.6, 0),
    sous_sol: new THREE.Vector3(-1.8, 0.3, 1.8)
  };
  ZONE_NAMES.forEach(name => {
    const texture = makeLabelCanvasTexture(name, 0);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(material);
    const anchor = anchors[name].clone().add(offsets[name]);
    sprite.position.copy(anchor); sprite.scale.set(1.8, 0.55, 1);
    house.add(sprite); labelSprites[name] = sprite;
    const lineGeo = new THREE.BufferGeometry().setFromPoints([anchors[name], anchor]);
    const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: WIRE_COLOR, transparent: true, opacity: 0.5 }));
    house.add(line); leaderLines[name] = line;
  });
}
function makeLabelCanvasTexture(title, score) {
  const canvas = document.createElement('canvas'); canvas.width = 300; canvas.height = 90;
  const ctx = canvas.getContext('2d');
  const color = '#' + scoreToColor(score).toString(16).padStart(6, '0');
  ctx.fillStyle = 'rgba(10,16,26,0.9)'; ctx.strokeStyle = color; ctx.lineWidth = 3;
  roundRect(ctx, 4, 4, canvas.width - 8, canvas.height - 8, 12); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#cfe4ff'; ctx.font = '600 22px Segoe UI, sans-serif';
  ctx.fillText(title.replace('_', ' '), 20, 36);
  ctx.fillStyle = color; ctx.font = '700 26px Segoe UI, sans-serif';
  ctx.fillText(score + ' / 100', 20, 70);
  return new THREE.CanvasTexture(canvas);
}
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function updateZoneLabel(zoneName, score) {
  const sprite = labelSprites[zoneName]; if (!sprite) return;
  sprite.material.map = makeLabelCanvasTexture(zoneName, score);
  sprite.material.needsUpdate = true;
}

// ---------- 7. CONTRÔLE CAMÉRA (glisser = tourner, molette = zoom) ----------
const cameraTarget = new THREE.Vector3(0, 2.2, 0);
let radius = 17, theta = Math.PI / 4, phi = Math.PI / 3;
let targetTheta = theta, targetPhi = phi, targetRadius = radius;
let isDragging = false, lastX = 0, lastY = 0, idleTime = 0;

function updateCameraPosition(dt) {
  if (!isDragging) { idleTime += dt; if (idleTime > 2) targetTheta += dt * 0.05; }
  theta += (targetTheta - theta) * 0.1; phi += (targetPhi - phi) * 0.1; radius += (targetRadius - radius) * 0.1;
  camera.position.x = cameraTarget.x + radius * Math.sin(phi) * Math.sin(theta);
  camera.position.y = cameraTarget.y + radius * Math.cos(phi);
  camera.position.z = cameraTarget.z + radius * Math.sin(phi) * Math.cos(theta);
  camera.lookAt(cameraTarget);
}
renderer.domElement.addEventListener('mousedown', e => { isDragging = true; idleTime = 0; lastX = e.clientX; lastY = e.clientY; });
_mouseUpHandler = () => { isDragging = false; idleTime = 0; };
window.addEventListener('mouseup', _mouseUpHandler);
_mouseMoveHandler = e => {
  if (!isDragging) return;
  const dx = e.clientX - lastX, dy = e.clientY - lastY; lastX = e.clientX; lastY = e.clientY;
  targetTheta -= dx * 0.006; targetPhi = Math.max(0.35, Math.min(Math.PI / 2.1, targetPhi - dy * 0.006));
};
window.addEventListener('mousemove', _mouseMoveHandler);
renderer.domElement.addEventListener('wheel', e => { e.preventDefault(); targetRadius = Math.max(6, Math.min(140, targetRadius + e.deltaY * 0.01)); }, { passive: false });
function fitCameraToHouse() {
  const span = Math.max(houseDims.W || 8, houseDims.D || 8);
  const hauteur = houseDims.ridgeY || 6;
  // Un immeuble de 5 niveaux sur 40 m d'emprise ne tenait pas dans le cadrage
  // prevu pour une maison : la distance suit desormais la plus grande des
  // deux dimensions, emprise ou hauteur.
  const fit = clamp(Math.max(span * 1.9, hauteur * 2.4), 12, 110);
  radius = fit; targetRadius = fit;
  // Le brouillard etait fige a 20/55 unites, calibre pour une maison vue de
  // 17 unites. Sur un immeuble de 40 m recule a 110 unites, tout le bati
  // tombait au-dela de la distance de disparition et virait a la couleur de
  // fond : d'ou l'impression de ne plus rien voir. Les distances suivent
  // desormais le cadrage.
  if (scene.fog) { scene.fog.near = fit * 1.15; scene.fog.far = fit * 3.2; }

  // Grille et cercle de scan sont dimensionnes pour une maison : sur un
  // immeuble, la grille s'arretait sous le bati et l'anneau disparaissait a
  // l'interieur. Les deux suivent maintenant l'emprise.
  const echelleSol = clamp(span / 14, 1, 6);
  grid.scale.setScalar(echelleSol);
  scanRing.scale.setScalar(echelleSol);

  const b = houseDims.bounds;
  if (b) {
    const cx = (b.minX + b.maxX) / 2, cz = (b.minZ + b.maxZ) / 2;
    grid.position.set(cx, 0, cz);
    scanRing.position.set(cx, 0.01, cz);
  }
  cameraTarget.set(
    b ? (b.minX + b.maxX) / 2 : 0,
    Math.max(2.2, hauteur * 0.45),
    b ? (b.minZ + b.maxZ) / 2 : 0
  );
}

// ---------- 8. RAYCASTING (survol + clic) ----------
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let hoveredGroup = null;
function getIntersects(event) {
  mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  return raycaster.intersectObjects(interactiveMeshes);
}
// ---- Glow au survol : on booste l'opacite des fills du groupe survole ----
function setGroupGlow(group, on) {
  if (!group) return;
  group.traverse(obj => {
    if (obj.isMesh && obj.material && typeof obj.material.opacity === 'number') {
      if (obj.userData.baseOpacity === undefined) obj.userData.baseOpacity = obj.material.opacity;
      obj.material.opacity = on ? Math.min(0.95, obj.userData.baseOpacity * 1.9) : obj.userData.baseOpacity;
    }
  });
}

// ---- Tooltip flottant (nom de zone + niveau de risque) apres 1s de survol ----
let hoverTooltipTimer = null;
const zoneTooltipEl = document.getElementById('zone-tooltip');
function showZoneTooltip(zoneName, clientX, clientY) {
  if (!zoneTooltipEl) return;
  const data = currentZones && currentZones[zoneName];
  const niveau = data ? data.niveau : null;
  const niveauLabels = { faible: 'Risque faible', modere: 'Risque modéré', eleve: 'Risque élevé', critique: 'Risque critique' };
  const niveauColors = { faible: '#1F9D6C', modere: '#D98A2B', eleve: '#BF5E00', critique: '#C0392B' };
  const label = zoneName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  zoneTooltipEl.innerHTML = '<strong>' + label + '</strong>' +
    (niveau ? '<br><span style="color:' + (niveauColors[niveau] || '#8B959D') + ';">' + (niveauLabels[niveau] || niveau) + '</span>' : '');
  zoneTooltipEl.style.left = (clientX + 16) + 'px';
  zoneTooltipEl.style.top = (clientY + 16) + 'px';
  zoneTooltipEl.style.opacity = '1';
}
function hideZoneTooltip() {
  clearTimeout(hoverTooltipTimer);
  hoverTooltipTimer = null;
  if (zoneTooltipEl) zoneTooltipEl.style.opacity = '0';
}

// ---- Animation de clic : la zone soulevee/pulsee ----
const clickPulses = [];
function pulseZone(group) {
  if (!group) return;
  clickPulses.push({ group, t: 0, baseY: group.position.y });
}
function animateClickPulses(dt) {
  for (let i = clickPulses.length - 1; i >= 0; i--) {
    const p = clickPulses[i];
    p.t += dt / 0.35; // duree ~350ms
    if (p.t >= 1) {
      p.group.position.y = p.baseY;
      clickPulses.splice(i, 1);
      continue;
    }
    // aller-retour : monte puis redescend (sin sur 0..pi)
    const lift = Math.sin(Math.min(p.t, 1) * Math.PI) * 0.18; // ~2-3px a l'echelle de la scene
    p.group.position.y = p.baseY + lift;
  }
}

renderer.domElement.addEventListener('mousemove', event => {
  if (isDragging) { hideZoneTooltip(); return; }
  const intersects = getIntersects(event);
  const newGroup = intersects.length ? intersects[0].object.parent : null;
  if (hoveredGroup && hoveredGroup !== newGroup) {
    hoveredGroup.scale.set(1, 1, 1);
    setGroupGlow(hoveredGroup, false);
    hoveredGroup = null;
    renderer.domElement.style.cursor = interactiveMeshes.length ? 'grab' : 'default';
    hideZoneTooltip();
  }
  if (newGroup && newGroup !== hoveredGroup) {
    hoveredGroup = newGroup;
    hoveredGroup.scale.set(1.02, 1.02, 1.02);
    setGroupGlow(hoveredGroup, true);
    renderer.domElement.style.cursor = 'pointer';
    hideZoneTooltip();
    const zoneName = intersects[0].object.userData.zoneName;
    hoverTooltipTimer = setTimeout(() => showZoneTooltip(zoneName, event.clientX, event.clientY), 1000);
  } else if (newGroup && zoneTooltipEl && zoneTooltipEl.style.opacity === '1') {
    zoneTooltipEl.style.left = (event.clientX + 16) + 'px';
    zoneTooltipEl.style.top = (event.clientY + 16) + 'px';
  }
});
renderer.domElement.addEventListener('mouseleave', () => {
  if (hoveredGroup) { hoveredGroup.scale.set(1, 1, 1); setGroupGlow(hoveredGroup, false); hoveredGroup = null; }
  hideZoneTooltip();
});
renderer.domElement.addEventListener('click', event => {
  const intersects = getIntersects(event);
  if (intersects.length) {
    const group = intersects[0].object.parent;
    pulseZone(group);
    showZonePanel(intersects[0].object.userData.zoneName);
  }
});

// ---------- 9. ÉTAT APPLICATIF ----------
let rawData = null;
let currentZones = null;
let currentYear = 2025;
// false tant que /diagnostic/fast a ete utilise et que /diagnostic/recommandations
// n'a pas encore repondu (cf. formulaire d'adresse) : permet d'afficher
// "Analyse en cours" plutot que "Aucune recommandation" pendant ce court
// intervalle. true immediatement pour les jeux de donnees deja complets
// (demo, JSON importe) qui n'ont pas de second appel a attendre.
let recommandationsReady = true;

function loadDataset(data) {
  rawData = data;
  recommandationsReady = !data._resume;
  buildHouse(data.geometry);
  fitCameraToHouse();
  document.getElementById('scene-container').classList.add('scene-ready');
  document.getElementById('addr-line').textContent = data.adresse || '—';
  const climat = data.climat;
  const climPanel = document.getElementById('climat-panel');
  const climToggleBtn = document.getElementById('btn-climat-toggle');
  if (climat && climat['2050']) {
    const p2050 = climat['2050'];
    // Le pic absolu (temperature_max_projetee_c = temperature_max_absolue_c de l'API) a la priorite
    const picTemp = p2050.temperature_max_projetee_c;
    if (typeof picTemp === 'number') {
      document.getElementById('temp-value').textContent = picTemp.toFixed(1) + ' °C';
    } else if (typeof p2050.temperature_max_moyenne_c === 'number') {
      document.getElementById('temp-value').textContent = p2050.temperature_max_moyenne_c.toFixed(1) + ' °C (moy.)';
    }
    document.getElementById('climat-sources-badge').textContent = climat.source || '—';
    climPanel.style.marginTop = '10px';
    climPanel.style.paddingTop = '10px';
    climPanel.style.borderTop = '1px solid #DCE6EC';
    climPanel.style.fontSize = '12px';
    climPanel.style.color = '#4E5860';
    climPanel.style.lineHeight = '1.5';
    if (climToggleBtn) climToggleBtn.style.display = 'inline-block';
  } else if (climToggleBtn) {
    climToggleBtn.style.display = 'none';
  }

  // Badges sources conditionnelles
  if (data._sources && data._sources.climat_copernicus) {
    document.getElementById('copernicus-badge').style.display = 'block';
  }
  if (data.marche && data.marche.dvf_disponible) {
    document.getElementById('dvf-badge').style.display = 'block';
  }
  document.getElementById('info-panel').style.display = 'none';
  setYear(2025, true);
}

// ---- Chargement en 2 temps (maison immediate, recommandations en fond) ----
// /diagnostic/fast renvoie la maison + les scores de risque (donc les
// couleurs des zones) sans attendre le RAG recommandations ni
// l'interpretation LLM, qui sont a eux deux la quasi-totalite des dizaines
// de secondes d'un /diagnostic classique. Une fois la maison affichee, on
// appelle /diagnostic/recommandations en tache de fond avec le bloc
// "_resume" renvoye par /diagnostic/fast (building_data/risk_scores deja
// collectes, pas besoin de relancer la collecte reseau) puis on fusionne
// les recommandations des qu'elles arrivent.
function setRecoStatus(loading) {
  const el = document.getElementById('reco-status');
  if (el) el.style.display = loading ? 'flex' : 'none';
}

function mergeRecommandations(fullContract) {
  if (!fullContract || !fullContract.zones || !rawData) return;
  Object.keys(fullContract.zones).forEach(zoneName => {
    if (!rawData.zones[zoneName]) return;
    const src = fullContract.zones[zoneName];
    const dst = rawData.zones[zoneName];
    dst.recommandations = src.recommandations || [];
    dst.conclusion = src.conclusion || '';
    dst.facteurs_aggravants = src.facteurs_aggravants || [];
    dst.facteurs_attenuants = src.facteurs_attenuants || [];
    dst.vulnerabilite = src.vulnerabilite || dst.vulnerabilite;
  });
  recommandationsReady = true;

  // Le panneau de score global ne bouge pas (les recommandations n'altèrent
  // pas les scores de risque) : on ne rafraîchit que la zone actuellement
  // affichée (onglets + cartes de recommandations + diagnostic textuel).
  if (currentYear === 2025) {
    currentZones = JSON.parse(JSON.stringify(rawData.zones));
    const infoPanel = document.getElementById('info-panel');
    // Garde nulle : si l'utilisateur a quitté la scène pendant la fusion en
    // arrière-plan, le panneau n'existe plus — ne pas planter la fusion.
    if (infoPanel && infoPanel.style.display === 'block' && infoPanel.dataset.zone) {
      showZonePanel(infoPanel.dataset.zone);
    }
  }
}

function fetchRecommandations(apiBase, fastContract) {
  const resume = fastContract && fastContract._resume;
  if (!resume) { recommandationsReady = true; return; }
  setRecoStatus(true);
  fetch(apiBase + '/diagnostic/recommandations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      building_data: resume.building_data,
      risk_scores: resume.risk_scores,
      formulaire: resume.formulaire,
    }),
  })
    .then(async response => {
      if (!response.ok) {
        const bodyText = await response.text();
        throw new Error(`${response.status} ${response.statusText} — ${bodyText.slice(0, 300)}`);
      }
      return response.json();
    })
    .then(fullContract => {
      mergeRecommandations(fullContract);
      setRecoStatus(false);
    })
    .catch(err => {
      console.error('Échec de la récupération des recommandations :', err);
      recommandationsReady = true;
      setRecoStatus(false);
    });
}

function setYear(year, force) {
  if (year === currentYear && !force) return;
  currentYear = year;
  document.getElementById('btn-2025').classList.toggle('active', year === 2025);
  document.getElementById('btn-2050').classList.toggle('active', year === 2050);
  const source = year === 2050 ? rawData.projection_2050.zones : rawData.zones;
  const scoreGlobal = year === 2050 ? rawData.projection_2050.score_global : rawData.score_global;
  currentZones = JSON.parse(JSON.stringify(source));
  document.getElementById('score-value').textContent = scoreGlobal;
  window.currentGlobalScore = scoreGlobal;
  ZONE_NAMES.forEach(name => { if (currentZones[name]) updateZoneColor(name, currentZones[name].risque, !force); });
  const infoPanel = document.getElementById('info-panel');
  if (infoPanel.style.display === 'block' && infoPanel.dataset.zone) showZonePanel(infoPanel.dataset.zone);
}
const _h2025 = () => setYear(2025);
const _h2050 = () => setYear(2050);
const _btn2025El = document.getElementById('btn-2025');
const _btn2050El = document.getElementById('btn-2050');
_btn2025El.addEventListener('click', _h2025);
_btn2050El.addEventListener('click', _h2050);
_elementHandlers.push({ el: _btn2025El, type: 'click', fn: _h2025 }, { el: _btn2050El, type: 'click', fn: _h2050 });

const climToggleBtnEl = document.getElementById('btn-climat-toggle');
if (climToggleBtnEl) {
  climToggleBtnEl.style.display = 'none';
  climToggleBtnEl.addEventListener('click', () => {
    const panel = document.getElementById('climat-panel');
    const open = panel.style.display === 'block';
    panel.style.display = open ? 'none' : 'block';
    climToggleBtnEl.style.background = open ? '#F1F6F9' : 'var(--brand-light)';
    climToggleBtnEl.style.borderColor = open ? '#DCE6EC' : 'var(--brand)';
  });
}

// ---- Filtre du panneau d'info par niveau de risque ----
document.querySelectorAll('.risk-filter-btn').forEach(btn => {
  const fn = () => {
    infoRiskFilter = btn.dataset.filter;
    document.querySelectorAll('.risk-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
    const infoPanel = document.getElementById('info-panel');
    if (infoPanel.dataset.zone) showZonePanel(infoPanel.dataset.zone);
  };
  btn.addEventListener('click', fn);
  _elementHandlers.push({ el: btn, type: 'click', fn });
});

// ---- Export PDF (impression du panneau d'info) ----
const exportPdfBtn = document.getElementById('info-export-pdf');
if (exportPdfBtn) {
  const fn = () => window.print();
  exportPdfBtn.addEventListener('click', fn);
  _elementHandlers.push({ el: exportPdfBtn, type: 'click', fn });
}// Construit la phrase "coût estimé" complète à partir de l'objet
// cout_estime produit par l'agent recommandations : montant_min/max/devise/unite
// + infos de contexte (date_estimation, zone_geo, hypotheses).
function formatCoutEstime(cout) {
  if (!cout || (cout.montant_min == null && cout.montant_max == null)) return null;
  const min = cout.montant_min, max = cout.montant_max, dev = cout.devise || '€';
  const range = (min != null && max != null && min !== max) ? `entre ${min} et ${max}` : `environ ${min ?? max}`;
  let txt = `<b>Coût estimé : ${range} ${escapeHtml(dev)}</b>${cout.unite ? ' ' + escapeHtml(cout.unite) : ''}`;
  const contexte = [];
  if (cout.zone_geo) contexte.push(escapeHtml(cout.zone_geo));
  if (cout.date_estimation) contexte.push(`estimation ${escapeHtml(cout.date_estimation)}`);
  if (contexte.length) txt += ` <span class="reco-meta-sub">(${contexte.join(', ')})</span>`;
  if (cout.hypotheses) txt += `<div class="reco-meta-sub">Hypothèses : ${escapeHtml(cout.hypotheses)}</div>`;
  return txt;
}

// Helpers partagés (chat + devis) pour lire indifféremment le schéma réel
// (mesure/cout_estime objet/aide/sources) et le schéma d'exemple
// (travaux/cout_estime chaîne/gain_resilience).
function recoLabel(r) { return r.mesure || r.travaux || 'Travaux recommandés'; }
function recoCostRange(r) {
  const c = r.cout_estime;
  if (c && typeof c === 'object') {
    const min = c.montant_min, max = c.montant_max;
    if (min == null && max == null) return { min: 0, max: 0, label: '—' };
    const dev = c.devise || '€';
    const label = (min != null && max != null && min !== max) ? `${min}–${max} ${dev}` : `environ ${min ?? max} ${dev}`;
    return { min: min ?? max ?? 0, max: max ?? min ?? 0, label };
  }
  if (typeof c === 'string') {
    const parts = c.replace(/€/g, '').split('-').map(n => parseInt(n, 10));
    if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) return { min: parts[0], max: parts[1], label: c };
    return { min: 0, max: 0, label: c || '—' };
  }
  return { min: 0, max: 0, label: '—' };
}
function recoGain(r) { return typeof r.gain_resilience === 'number' ? r.gain_resilience : 10; }

async function rechercherArtisans(zoneName, data, container, button) {
  const apiBaseInput = document.getElementById('api-base-input');
  const apiBase = (apiBaseInput && apiBaseInput.value || window.TYPHOON_API).trim();
  return matchArtisans({
    apiBase,
    adresse: (rawData && rawData.adresse) || '',
    zoneName,
    data,
    container,
    button,
  });
}

let infoRiskFilter = 'tous';

function showZonePanel(zoneName) {
  let data = currentZones[zoneName];
  // Si la zone demand\u00e9e ne correspond plus au filtre actif, on bascule sur la premi\u00e8re zone qui matche.
  if (infoRiskFilter !== 'tous' && data && data.niveau !== infoRiskFilter) {
    const fallback = Object.keys(currentZones).find(z => currentZones[z].niveau === infoRiskFilter);
    if (fallback) { zoneName = fallback; data = currentZones[zoneName]; }
  }
  if (!data) return;
  const panel = document.getElementById('info-panel');
  panel.style.display = 'block'; panel.dataset.zone = zoneName;
  window.dispatchEvent(new CustomEvent('typhoon:zoneSelected', { detail: { zoneName: zoneName } }));

  // ---- Build zone tabs (respecte le filtre par niveau de risque) ----
  const tabsContainer = document.getElementById('info-zone-tabs');
  tabsContainer.innerHTML = '';
  const zoneNames = Object.keys(currentZones);
  zoneNames.forEach(z => {
    const zData = currentZones[z];
    if (infoRiskFilter !== 'tous' && zData.niveau !== infoRiskFilter) return;
    const tab = document.createElement('span');
    tab.className = 'info-zone-tab' + ((z === zoneName) ? ' active' : '');
    if (!zData.recommandations || !zData.recommandations.length) tab.classList.add('tab-empty');
    const label = z.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const n = (zData.recommandations || []).length;
    tab.innerHTML = label + (n > 0 ? '<span class="tab-count">' + n + '</span>' : '');
    tab.onclick = () => showZonePanel(z);
    tabsContainer.appendChild(tab);
  });
  if (!tabsContainer.children.length) {
    tabsContainer.innerHTML = '<span style="font-size:11px;color:var(--muted);font-style:italic;">Aucune zone \u00e0 ce niveau de risque.</span>';
  }

  // ---- Zone header ----
  document.getElementById('info-title').textContent = zoneName.replace(/_/g, ' ');
  const badge = document.getElementById('info-badge');
  badge.textContent = data.niveau.toUpperCase() + ' \u2014 ' + data.risque + '/100';
  const scoreColorHex = '#' + scoreToColor(data.risque).toString(16).padStart(6, '0');
  badge.style.background = scoreColorHex;
  const scoreFill = document.getElementById('info-score-bar-fill');
  scoreFill.style.width = Math.max(2, Math.min(100, data.risque)) + '%';
  scoreFill.style.background = scoreColorHex;
  document.getElementById('info-alea').innerHTML = '<b>Al\u00e9a :</b> ' + escapeHtml(data.alea_principal);
  document.getElementById('info-justif').textContent = data.justification;

  // ---- Diagnostic compact ----
  const conclusionDiv = document.getElementById('info-conclusion');
  const diagnosticHeader = document.getElementById('info-diagnostic-header');
  const etatDiv = document.getElementById('info-etat');
  const aggravantsDiv = document.getElementById('info-aggravants');
  const attenuantsDiv = document.getElementById('info-attenuants');
  if (data.conclusion) {
    let zoneLabel = zoneName.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
    diagnosticHeader.textContent = 'Diagnostic ' + zoneLabel;
    etatDiv.textContent = 'Etat : ' + data.conclusion;
    conclusionDiv.style.display = 'block';
    aggravantsDiv.innerHTML = '';
    if (data.facteurs_aggravants && data.facteurs_aggravants.length) {
      let h = '<div style="font-size:10.5px;font-weight:600;color:#C0392B;margin-bottom:3px;">Aggravants</div><div style="font-size:11px;color:#4B5760;line-height:1.5;">';
      for (let i = 0; i < data.facteurs_aggravants.length; i++) {
        h += '<div style="display:flex;align-items:flex-start;gap:5px;margin-bottom:2px;"><span style="color:#C0392B;flex-shrink:0;">\u2022</span><span>' + escapeHtml(data.facteurs_aggravants[i]) + '</span></div>';
      }
      h += '</div>';
      aggravantsDiv.innerHTML = h;
    }
    attenuantsDiv.innerHTML = '';
    if (data.facteurs_attenuants && data.facteurs_attenuants.length) {
      let h = '<div style="font-size:10.5px;font-weight:600;color:#1F9D6C;margin-bottom:3px;">Att\u00e9nuants</div><div style="font-size:11px;color:#4B5760;line-height:1.5;">';
      for (let j = 0; j < data.facteurs_attenuants.length; j++) {
        h += '<div style="display:flex;align-items:flex-start;gap:5px;margin-bottom:2px;"><span style="color:#1F9D6C;flex-shrink:0;">\u2022</span><span>' + escapeHtml(data.facteurs_attenuants[j]) + '</span></div>';
      }
      h += '</div>';
      attenuantsDiv.innerHTML = h;
    }
  } else {
    conclusionDiv.style.display = 'none';
  }

  // ---- Cost summary ----
  const costSummary = document.getElementById('info-cost-summary');
  const recos = data.recommandations || [];
  let totalMin = 0, totalMax = 0, aideTotal = 0;
  recos.forEach(r => {
    const c = parseCoutEstime(r.cout_estime);
    if (c.min > 0) totalMin += c.min;
    if (c.max > 0) totalMax += c.max;
    if (r.aide && r.aide.dispositif) aideTotal += c.min * 0.3;
  });
  if (totalMin > 0 || totalMax > 0) {
    document.getElementById('cs-total').textContent = totalMin.toLocaleString('fr-FR') + ' \u2014 ' + totalMax.toLocaleString('fr-FR') + ' \u20ac';
    document.getElementById('cs-aides').textContent = '~' + Math.round(aideTotal).toLocaleString('fr-FR') + ' \u20ac';
    const reste = totalMin - aideTotal;
    document.getElementById('cs-reste').textContent = Math.max(0, reste).toLocaleString('fr-FR') + ' \u20ac';
    const pct = totalMax > 0 ? Math.min(100, Math.round((aideTotal / totalMax) * 100)) : 0;
    document.getElementById('cs-progress').style.width = pct + '%';
    costSummary.classList.add('visible');
  } else {
    costSummary.classList.remove('visible');
  }

  // ---- Recommendations (accordion cards) ----
  const recosDiv = document.getElementById('info-recos');
  recosDiv.innerHTML = '';

  if (!recos.length) {
    const empty = document.createElement('div');
    empty.className = 'reco-empty';
    empty.textContent = recommandationsReady
      ? 'Aucune recommandation pour cette zone.'
      : 'Analyse des recommandations en cours…';
    recosDiv.appendChild(empty);
    return;
  }

  // ---- Regroupement par type de travaux (isolation, structure, \u00e9tanch\u00e9it\u00e9, etc.) ----
  const groups = new Map();
  recos.forEach(r => {
    const key = r.type ? r.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Autres travaux';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  });

  groups.forEach((groupRecos, groupLabel) => {
    if (groups.size > 1) {
      const groupHeader = document.createElement('div');
      groupHeader.className = 'reco-group-label';
      groupHeader.textContent = groupLabel + ' (' + groupRecos.length + ')';
      recosDiv.appendChild(groupHeader);
    }

    groupRecos.forEach((r) => {
      const card = document.createElement('div');
      card.className = 'reco-card';

      const mesure = r.mesure || r.travaux || 'Travaux recommand\u00e9s';
      const risqueConcerne = r.risque_concerne || (Array.isArray(r.sources) && r.sources.length ? r.sources[0].source_id : '') || '';
      const cout = parseCoutEstime(r.cout_estime);

      // Priority badge based on risk level
      const niveau = data.niveau || 'modere';
      let priorite = 'moyenne';
      let prioriteLabel = 'Moyenne';
      if (niveau === 'critique' || niveau === 'eleve') { priorite = 'haute'; prioriteLabel = 'Haute'; }
      else if (niveau === 'faible') { priorite = 'faible'; prioriteLabel = 'Faible'; }

      const coutLabel = cout.min > 0 || cout.max > 0
        ? cout.label
        : (typeof r.cout_estime === 'string' ? r.cout_estime : '');

      card.innerHTML = '<div class="reco-card-header" onclick="toggleRecoCard(this)">'
        + '<svg class="reco-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l4 4-4 4"/></svg>'
        + '<div class="reco-title-wrap"><span class="reco-title">' + escapeHtml(mesure) + '</span>'
        + (coutLabel ? '<span class="reco-sub">' + escapeHtml(coutLabel) + '</span>' : '')
        + '</div>'
        + '<span class="reco-priority-badge ' + priorite + '">' + prioriteLabel + '</span>'
        + '</div>'
        + '<div class="reco-card-body">'
        + (risqueConcerne ? '<div class="reco-risque-tag">' + escapeHtml(risqueConcerne) + '</div>' : '')
        + (r.explication ? '<div class="reco-explication">' + escapeHtml(r.explication) + '</div>' : '')
        + (r.type ? '<div class="reco-meta"><strong>Type :</strong> ' + escapeHtml(r.type.replace(/_/g, ' ')) + '</div>' : '')
        + (coutLabel ? '<div class="reco-meta"><strong>Cout estime :</strong> ' + escapeHtml(coutLabel) + '</div>' : '')
        + (r.gain_resilience ? '<div class="reco-meta"><strong>Gain resilience :</strong> +' + r.gain_resilience + '</div>' : '')
        + (r.aide && (r.aide.dispositif || r.aide.conditions) ? '<div class="reco-aide"><b>' + escapeHtml(r.aide.dispositif || 'Aide potentielle') + '</b>'
          + (r.aide.conditions ? '<div style="font-size:11px;color:#8A5A10;margin-top:3px;">' + escapeHtml(r.aide.conditions) + '</div>' : '')
          + (r.aide.statut ? '<div style="font-size:10px;color:#B96A18;margin-top:2px;">Statut : ' + escapeHtml(r.aide.statut.replace(/_/g, ' ')) + '</div>' : '')
          + '</div>' : '')
        + (Array.isArray(r.sources) && r.sources.length ? '<div class="reco-sources">Sources : ' + r.sources.map(s => s.source_id || s.fiche_id).filter(Boolean).join(', ') + '</div>' : '')
        + '</div>';

      recosDiv.appendChild(card);
    });
  });

  const artisanButton = document.createElement('button');
  artisanButton.type = 'button';
  artisanButton.className = 'artisan-search-btn';
  artisanButton.textContent = 'Rechercher des artisans correspondants';
  const artisanResults = document.createElement('div');
  artisanResults.className = 'artisan-results';
  artisanButton.addEventListener('click', () => {
    // Transmet l'adresse et les recommandations du diagnostic (toutes zones
    // confondues, pas seulement la zone actuellement affichee) a la page
    // artisans via sessionStorage, pour que le contenu (ex. etude RGA) soit
    // bien present a l'arrivee sur ../artisans/index.html.
    //
    // Important : on garde la zone et les risques d'origine de chaque
    // mesure (pas seulement r.type, qui vaut toujours la constante
    // "recommandation_source" et ne decrit pas le domaine des travaux) car
    // le classifieur backend (_classifier_recommandation) s'appuie d'abord
    // sur les risques ("retrait_gonflement_argiles", "sismique"...) pour
    // reconnaitre des mesures comme le RGA quand le texte de la mesure ne
    // contient aucun mot-cle explicite.
    const adresseDiag = (rawData && rawData.adresse) || '';
    const recommandationsStructurees = [];
    const zonesSource = currentZones || {};
    // Chaque zone porte son aléa principal dans `alea_principal` (chaîne,
    // ex. "Retrait-gonflement des argiles"), pas dans un tableau `risques` —
    // cf. rechercherArtisans() plus haut qui envoie déjà `[data.alea_principal]`
    // au même backend. C'est ce texte qui contient les mots-clés ("argile",
    // "sismique", "radon"...) dont le classifieur a besoin.
    // Le classifieur backend (_classifier_recommandation) compare les
    // sous-chaines sans re-normaliser zone/risques (seule la mesure est
    // passee en minuscules cote serveur) : on met donc nous-memes tout en
    // minuscules ici pour ne pas dependre de la casse d'alea_principal.
    Object.entries(zonesSource).forEach(([zoneName, z]) => {
      const risques = z.alea_principal ? [String(z.alea_principal).toLowerCase()] : [];
      (z.recommandations || []).forEach(r => {
        const mesure = r.mesure || r.travaux;
        if (mesure) recommandationsStructurees.push({ mesure: mesure, zone: zoneName.toLowerCase(), risques: risques });
      });
    });
    // Repli si currentZones est vide pour une raison quelconque : au moins
    // la zone actuellement affichee (deja disponible via la fermeture de
    // showZonePanel, avec son propre alea_principal).
    if (!recommandationsStructurees.length) {
      const risquesZoneActuelle = data.alea_principal ? [String(data.alea_principal).toLowerCase()] : [];
      recos.forEach(r => {
        const mesure = r.mesure || r.travaux;
        if (mesure) recommandationsStructurees.push({ mesure: mesure, zone: String(zoneName).toLowerCase(), risques: risquesZoneActuelle });
      });
    }
    try {
      sessionStorage.setItem('typhoon_artisan_handoff', JSON.stringify({
        adresse: adresseDiag,
        recommandationsStructurees: recommandationsStructurees,
      }));
    } catch (e) {
      // sessionStorage indisponible : on navigue quand meme, avec les
      // valeurs par defaut de la page artisans.
    }
    window.location.assign('/artisans');
  });
  recosDiv.appendChild(artisanButton);
  recosDiv.appendChild(artisanResults);
}

function toggleRecoCard(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.reco-chevron');
  if (body) body.classList.toggle('open');
  if (chevron) chevron.classList.toggle('open');
}

function parseCoutEstime(c) {
  if (!c) return { min: 0, max: 0, label: '\u2014' };
  if (typeof c === 'string') {
    const parts = c.split('-');
    if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) return { min: parseInt(parts[0]), max: parseInt(parts[1]), label: c };
    return { min: 0, max: 0, label: c };
  }
  if (typeof c === 'object') {
    const min = parseInt(c.montant_min) || 0;
    const max = parseInt(c.montant_max) || 0;
    return { min, max, label: (min || max) ? (min + ' \u2014 ' + max + ' \u20ac') : '\u2014' };
  }
  return { min: 0, max: 0, label: '\u2014' };
}
// ---------- 10. BOUCLE DE RENDU ----------
let lastTime = performance.now();
function animate(now) {
  _rafId = requestAnimationFrame(animate);
  const dt = Math.min((now - lastTime) / 1000, 0.1); lastTime = now;
  const elapsed = now / 1000;
  updateCameraPosition(dt);
  animateEffects(dt, elapsed);
  animateClickPulses(dt);
  renderer.render(scene, camera);
}
_rafId = requestAnimationFrame(animate);

_resizeHandler = () => {
  camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
};
window.addEventListener('resize', _resizeHandler);

// ---------- 11. DÉMARRAGE ----------
// Repli démo par défaut (comportement d'origine) : le moteur charge le jeu
// de données d'exemple tant que le front ne fournit pas de diagnostic réel.
loadDataset(DEFAULT_DATA);

_canvas = renderer.domElement;
_renderer = renderer;
}

export function disposeScene() {
  cancelAnimationFrame(_rafId);
  if (_resizeHandler) window.removeEventListener('resize', _resizeHandler);
  if (_mouseUpHandler) window.removeEventListener('mouseup', _mouseUpHandler);
  if (_mouseMoveHandler) window.removeEventListener('mousemove', _mouseMoveHandler);
  _elementHandlers.forEach(({ el, type, fn }) => el.removeEventListener(type, fn));
  _elementHandlers.length = 0;
  if (_canvas && _canvas.parentElement) _canvas.parentElement.removeChild(_canvas);
  if (_renderer) {
    _renderer.dispose();
    // Libération agressive du contexte GPU sur démontage (certains navigateurs
    // gardent le contexte en vie après dispose() seul).
    try { _renderer.forceContextLoss(); } catch (e) { /* non bloquant */ }
    _renderer = null;
  }
  _canvas = null; _resizeHandler = null; _mouseUpHandler = null; _mouseMoveHandler = null;
}

// ===========================================================================
// EXPORT — matchArtisans
//
// Recherche d'artisans autonome (paramètres explicites) : il sert la page
// /artisans, qui n'a PAS de moteur 3D monté. Même requête /artisans/match
// que rechercherArtisans() du moteur, mais sans dépendre de l'état du
// moteur (le moteur reste un port direct, ses fonctions sont privées).
// ===========================================================================

// Recherche d'artisans autonome (même requête /artisans/match que
// rechercherArtisans() du moteur, mais sans dépendre de l'état du moteur) :
// adresse et données de zone passées explicitement. Rend les résultats dans
// `container` (groupes par métier, cartes entreprises, notes d'avertissement).
export async function matchArtisans({
  apiBase,
  adresse,
  zoneName,
  data,
  container,
  button,
  limite = 5,
}) {
  if (button) {
    button.disabled = true;
    button.textContent = 'Recherche dans les annuaires officiels…';
  }
  if (container) container.innerHTML = '';
  try {
    const response = await fetch(apiBase + '/artisans/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        adresse: adresse || '',
        limite,
        zones: [{
          zone: zoneName,
          risques: [data && data.alea_principal ? data.alea_principal : ''],
          recommandations: (data && data.recommandations) || [],
        }],
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Erreur HTTP ${response.status}`);
    const groupes = payload.recommandations_traitees || [];
    if (!groupes.length) {
      if (container) {
        container.className = 'artisan-results artisan-empty';
        container.textContent =
          'Aucun métier n’a pu être associé automatiquement à ces recommandations.';
      }
      return;
    }
    if (container) container.className = 'artisan-results';
    groupes.forEach(groupe => {
      if (!container) return;
      const section = document.createElement('div');
      section.className = 'artisan-group';
      const heading = document.createElement('div');
      heading.className = 'artisan-group-head';
      const title = document.createElement('div');
      title.className = 'artisan-group-title';
      title.textContent = groupe.libelle || groupe.domaine_recherche || groupe.cle;
      const category = document.createElement('span');
      category.className = 'artisan-group-badge';
      category.textContent = groupe.categorie === 'rge' ? 'RGE' : 'Métier local';
      heading.appendChild(title);
      heading.appendChild(category);
      section.appendChild(heading);
      if (groupe.erreur) {
        const error = document.createElement('div');
        error.className = 'artisan-error';
        error.textContent = groupe.erreur;
        section.appendChild(error);
      }
      (groupe.entreprises || []).forEach(entreprise => {
        const card = document.createElement('div');
        card.className = 'artisan-card';
        const cardTop = document.createElement('div');
        cardTop.className = 'artisan-card-top';
        const name = document.createElement('div');
        name.className = 'artisan-name';
        name.textContent = entreprise.nom_entreprise || 'Entreprise';
        const score = document.createElement('div');
        score.className = 'artisan-score';
        score.innerHTML = `${Number(entreprise.score_objectif_sur_100) || 0}<small>/100</small>`;
        cardTop.appendChild(name);
        cardTop.appendChild(score);
        card.appendChild(cardTop);

        const meta = document.createElement('div');
        meta.className = 'artisan-meta';
        const addressText = [entreprise.adresse, entreprise.code_postal, entreprise.commune]
          .filter(Boolean)
          .join(' ');
        if (addressText) {
          const row = document.createElement('div');
          row.className = 'artisan-meta-row';
          row.innerHTML =
            `<span class="artisan-meta-icon">⌖</span><span>${escapeHtml(addressText)}</span>`;
          meta.appendChild(row);
        }
        if (entreprise.telephone || entreprise.email) {
          const row = document.createElement('div');
          row.className = 'artisan-meta-row';
          row.innerHTML =
            `<span class="artisan-meta-icon">✆</span><span>${escapeHtml(
              [entreprise.telephone, entreprise.email].filter(Boolean).join(' · '),
            )}</span>`;
          meta.appendChild(row);
        }
        card.appendChild(meta);

        const actions = document.createElement('div');
        actions.className = 'artisan-actions';
        if (entreprise.telephone) {
          const phone = document.createElement('a');
          phone.href = `tel:${String(entreprise.telephone).replace(/[^\d+]/g, '')}`;
          phone.className = 'artisan-action primary';
          phone.textContent = '✆ Appeler';
          actions.appendChild(phone);
        }
        if (entreprise.email) {
          const email = document.createElement('a');
          email.href = `mailto:${entreprise.email}`;
          email.className = 'artisan-action';
          email.textContent = '✉ Envoyer un e-mail';
          actions.appendChild(email);
        }
        if (addressText) {
          const directions = document.createElement('a');
          directions.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
            addressText,
          )}`;
          directions.target = '_blank';
          directions.rel = 'noopener';
          directions.className = 'artisan-action';
          directions.textContent = '⌖ Itinéraire';
          actions.appendChild(directions);
        }
        if (entreprise.site_officiel) {
          const site = document.createElement('a');
          site.href = entreprise.site_officiel;
          site.target = '_blank';
          site.rel = 'noopener';
          site.className = 'artisan-action';
          site.textContent = '↗ Site officiel';
          actions.appendChild(site);
        }
        if (actions.childElementCount) card.appendChild(actions);

        if (!entreprise.site_officiel) {
          const missing = document.createElement('div');
          missing.className = 'artisan-site-missing';
          missing.textContent = entreprise.telephone || entreprise.email
            ? 'Contact direct disponible sans site officiel.'
            : 'Aucun contact direct vérifiable trouvé pour cette entreprise.';
          card.appendChild(missing);
        }
        section.appendChild(card);
      });
      container.appendChild(section);
    });
    const warning = document.createElement('small');
    warning.className = 'artisan-note';
    warning.textContent = [payload.avertissement_score, payload.avertissement_sites]
      .filter(Boolean)
      .join(' ');
    container.appendChild(warning);
    // Recommandations non classifiées : ne pas les laisser disparaître
    // silencieusement — note explicite quand le classifieur n'a rien matché.
    const nonClassees = payload.recommandations_non_classifiees;
    if (Array.isArray(nonClassees) && nonClassees.length > 0) {
      const note = document.createElement('div');
      note.className = 'artisan-note';
      note.textContent = `${nonClassees.length} recommandation(s) n’ont pas pu être associées à un métier (${nonClassees
        .map(r => r.zone || r.mesure || '?')
        .slice(0, 3)
        .join(', ')}${nonClassees.length > 3 ? ', …' : ''}).`;
      container.appendChild(note);
    }
  } catch (error) {
    if (container) {
      container.className = 'artisan-results artisan-error';
      container.textContent = `Recherche indisponible : ${error.message}`;
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Rechercher des artisans correspondants';
    }
  }
}

