// =============================================================================
//   TYPHOON — /zone : « Simulation catastrophe » — vue 3D physique (étape 4,
//   troisième onglet, à côté du Jumeau 3D et de la Vue terrain 3D).
//
//   PORTAGE du pipeline de rendu de Mehdi (maison-desastres-jumeau.html) :
//     - buildHouse() : construction réelle pilotée par la géométrie — arêtes
//       de l'emprise (footprint BDNB, ou rectangle des dimensions réelles),
//       murs par étage, porte d'entrée avec vantail, fenêtres procédurales,
//       gouttières, cave + fondations enterrées dans la terre, toit à deux
//       pans (tuiles faîtières, pignons, cheminée) ou toit plat, dalles
//       d'étage. Plus de « boîtes D03 schématiques ».
//     - makeMaterials() : matériaux PBR mappés depuis les slugs BDNB
//       (PAL_MUR / PAL_TOIT) + chargement de textures fail-soft (fichier
//       absent → la couleur PBR reste en place, aucun plantage).
//     - Lighting : hémisphère + soleil directionnel avec ombres douces,
//       ACESFilmicToneMapping (le même rendu que le fichier de référence).
//     - Physique cannon-es + système de dommages des 6 catastrophes :
//       tornade, inondation, météores, incendie, séisme, grêle. Les blocs
//       sont statiques au repos et s'activent (deviennent dynamiques) quand
//       un désastre les arrache / les projette / les brûle / les fragilise.
//
//   Adaptation au contrat live : au lieu du DIAGNOSTICS codé en dur de Mehdi,
//   le moteur consomme `adaptedDiagnostic` (diagnosticAdapter.ts) :
//     - geometry.largeur_m / longueur_m / floors_count / hauteur_sous_plafond_m
//       / roof_shape / pente_toit_deg / materiau_mur / materiau_toiture /
//       has_basement / entree_facade (+ footprint polygonal quand le backend
//       le fournit)
//     - zones[].risque → coloration « Vue risque » (vert → rouge, comme
//       l'original) via le bouton dédié de la barre d'outils.
//
//   Chargé à la demande (React.lazy depuis ZoneBIM) : three + cannon-es ne
//   sont téléchargés qu'au premier clic sur l'onglet (même discipline que
//   CesiumViewer).
//
//   ⚠ Moteur visuel pédagogique — PAS une modélisation physique réglementaire
//   (aucune étude de génie civil / hydraulique / sismique).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import * as CANNON from 'cannon-es';
import type { AdapterResult, DiagnosticGeometry } from '../zone/diagnosticAdapter';
import { D03 } from '../zone/config';

/* ════════════════════════════════════════════════════════════════════════════
   Scénarios simulables — miroir visuel des aléas du rapport.
   ════════════════════════════════════════════════════════════════════════════ */

type ScenarioCode = 'tornado' | 'flood' | 'meteors' | 'fire' | 'seisme' | 'grele';

const ALL_SCENARIOS: ScenarioCode[] = ['tornado', 'flood', 'meteors', 'fire', 'seisme', 'grele'];

const SCENARIOS: Array<{ code: ScenarioCode; libelle: string; icon: string; hint: string }> = [
  {
    code: 'tornado',
    libelle: 'Tornade',
    icon: 'cyclone',
    hint: 'Tornade qui balaie le quartier — les éléments proches sont aspirés et projetés en l’air',
  },
  {
    code: 'flood',
    libelle: 'Inondation',
    icon: 'flood',
    hint: 'Montée des eaux continue — les éléments immergés s’allègent et dérivent (flottabilité)',
  },
  {
    code: 'meteors',
    libelle: 'Météores',
    icon: 'meteor',
    hint: 'Pluie de météores — impacts et explosions qui projettent les blocs, cratères au sol',
  },
  {
    code: 'fire',
    libelle: 'Incendie',
    icon: 'whatshot',
    hint: 'Le feu part de la toiture, se propage aux murs voisins et consume chaque élément',
  },
  {
    code: 'seisme',
    libelle: 'Séisme',
    icon: 'earthquake',
    hint: 'Secousses telluriques — les blocs se délogent et s’effondrent, caméra secouée',
  },
  {
    code: 'grele',
    libelle: 'Grêle',
    icon: 'ac_unit',
    hint: 'Grêlons qui martèlent la toiture — ternissement des tuiles, vitres qui éclatent',
  },
];

const STEP = 1 / 60;

/* ════════════════════════════════════════════════════════════════════════════
   Helpers géométriques (portage direct du fichier de référence)
   ════════════════════════════════════════════════════════════════════════════ */

const R = Math.random;
const RANGE = (a: number, b: number): number => a + R() * (b - a);

interface Edge {
  x0: number;
  z0: number;
  x1: number;
  z1: number;
  dx: number;
  dz: number;
  len: number;
  nx: number;
  nz: number;
}

interface FootprintPoly {
  exterieur: Array<[number, number]>;
  trous?: Array<Array<[number, number]>>;
}
interface FootprintLike {
  polygones?: FootprintPoly[];
}

function signedArea(ring: Array<[number, number]>): number {
  let s = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, z1] = ring[i];
    const [x2, z2] = ring[(i + 1) % ring.length];
    s += x1 * z2 - x2 * z1;
  }
  return s / 2;
}

function edgesFromRing(ring: Array<[number, number]>): Edge[] {
  const edges: Edge[] = [];
  let ext = ring.map((p) => [p[0], p[1]] as [number, number]);
  if (signedArea(ext) < 0) ext.reverse();
  const n = ext.length;
  for (let i = 0; i < n; i++) {
    const [x0, z0] = ext[i];
    const [x1, z1] = ext[(i + 1) % n];
    const dx = x1 - x0;
    const dz = z1 - z0;
    const len = Math.hypot(dx, dz);
    if (len < 0.4) continue;
    edges.push({ x0, z0, x1, z1, dx, dz, len, nx: dz / len, nz: -dx / len });
  }
  return edges;
}

function edgesFromFootprint(fp: FootprintLike | null | undefined): Edge[] {
  const edges: Edge[] = [];
  if (!fp) return edges;
  for (const poly of fp.polygones || []) {
    edges.push(...edgesFromRing(poly.exterieur));
  }
  return edges;
}

function facadeOrientation(nx: number, nz: number): string {
  const b = ((Math.atan2(nx, -nz) * 180) / Math.PI + 360) % 360;
  if (b >= 45 && b < 135) return 'murs_est';
  if (b >= 135 && b < 225) return 'murs_sud';
  if (b >= 225 && b < 315) return 'murs_ouest';
  return 'murs_nord';
}

function dominantAxisDeg(edges: Edge[]): number {
  let sc = 0;
  let ss = 0;
  for (const e of edges) {
    const a = Math.atan2(e.dz, e.dx);
    sc += e.len * Math.cos(4 * a);
    ss += e.len * Math.sin(4 * a);
  }
  return (((Math.atan2(ss, sc) / 4) * 180) / Math.PI) % 90;
}

function centroidOf(edges: Edge[]): { x: number; z: number } {
  let cx = 0;
  let cz = 0;
  let w = 0;
  for (const e of edges) {
    cx += (e.x0 + e.x1) * e.len;
    cz += (e.z0 + e.z1) * e.len;
    w += 2 * e.len;
  }
  return w ? { x: cx / w, z: cz / w } : { x: 0, z: 0 };
}

function norm3(v: number[]): number[] {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}
function cross3(a: number[], b: number[]): number[] {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** Forme du bâtiment (pour dalles / toit plat) : footprint réel ou rectangle
    construit depuis les dimensions BDNB (repli quand le backend ne fournit
    pas d'emprise polygonale). */
function shapeFromGeometry(g: DiagnosticGeometry): THREE.Shape {
  const fp = g.footprint as FootprintLike | null | undefined;
  if (fp && fp.polygones && fp.polygones.length > 0) {
    const poly = fp.polygones[0];
    const ext = poly.exterieur.map((p) => [p[0], p[1]] as [number, number]);
    if (signedArea(ext) < 0) ext.reverse();
    const shape = new THREE.Shape();
    shape.moveTo(ext[0][0], -ext[0][1]);
    for (let i = 1; i < ext.length; i++) shape.lineTo(ext[i][0], -ext[i][1]);
    for (const trou of poly.trous || []) {
      let h = trou.map((p) => [p[0], p[1]] as [number, number]);
      if (signedArea(h) > 0) h.reverse();
      const path = new THREE.Path();
      path.moveTo(h[0][0], -h[0][1]);
      for (let i = 1; i < h.length; i++) path.lineTo(h[i][0], -h[i][1]);
      shape.holes.push(path);
    }
    return shape;
  }
  const W = Math.max(1, g.largeur_m ?? 8);
  const L = Math.max(1, g.longueur_m ?? 8);
  const shape = new THREE.Shape();
  shape.moveTo(-W / 2, -L / 2);
  shape.lineTo(W / 2, -L / 2);
  shape.lineTo(W / 2, L / 2);
  shape.lineTo(-W / 2, L / 2);
  return shape;
}

/* ════════════════════════════════════════════════════════════════════════════
   Matériaux PBR (slugs BDNB → couleur) + textures fail-soft
   ════════════════════════════════════════════════════════════════════════════ */

const PAL_MUR: Record<string, string> = {
  brique: '#b87352',
  pierre: '#d1c7b3',
  meuliere: '#ccc4a3',
  parpaing: '#bdb8ad',
  agglomere: '#bdb8ad',
  beton: '#a8a8ad',
  bois: '#8f6b47',
  pan_de_bois: '#8f6b47',
  torchis: '#b89e7a',
};
const PAL_TOIT: Record<string, string> = {
  ardoise: '#525259',
  tuile: '#a34d33',
  zinc: '#8c949c',
  bac_acier: '#757a82',
  beton: '#8f8f94',
  vegetalise: '#597554',
};
const TEX_MUR: Record<string, string> = {
  brique: 'mur_brique.jpg',
  pierre: 'mur_pierre.jpg',
  meuliere: 'mur_meuliere.jpg',
  parpaing: 'mur_agglomere.jpg',
  agglomere: 'mur_agglomere.jpg',
  beton: 'mur_beton.jpg',
  bois: 'mur_bois.jpg',
};
const TEX_TOIT: Record<string, string> = {
  ardoise: 'toit_ardoises.jpg',
  tuile: 'toit_tuiles.jpg',
  zinc: 'toit_zinc.jpg',
  beton: 'toit_beton.jpg',
};

function slugKey(slug: string | null | undefined, map: Record<string, string>): string | null {
  const s = String(slug || '').toLowerCase().replace(/[\s-]+/g, '_');
  for (const k of Object.keys(map)) if (s.includes(k)) return k;
  return null;
}
function matColor(slug: string | null | undefined, palette: Record<string, string>, defaut: string): string {
  const k = slugKey(slug, palette);
  return k ? palette[k] : defaut;
}

/** Chargement fail-soft : fichier absent (404) → aucun effet, la couleur PBR
    du matériau reste en place. Les textures ne sont pas livrées avec l'app
    React (elles vivaient dans le dossier `typhoon-dt/textures/` du fichier
    de référence) — le rendu reste correct sans elles. */
function loadTex(name: string, repeat: number, onLoad: (t: THREE.Texture) => void): void {
  if (!name) return;
  new THREE.TextureLoader().load(
    'typhoon-dt/textures/' + name,
    (t) => {
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(repeat, repeat);
      t.encoding = THREE.sRGBEncoding;
      onLoad(t);
    },
    undefined,
    () => {}
  );
}

interface MaterialsBundle {
  door: THREE.MeshStandardMaterial;
  frame: THREE.MeshStandardMaterial;
  sill: THREE.MeshStandardMaterial;
  glass: THREE.MeshStandardMaterial;
  concrete: THREE.MeshStandardMaterial;
  slab: THREE.MeshStandardMaterial;
}

/* ════════════════════════════════════════════════════════════════════════════
   Particules (shader maison — tornade, météores, feu, fumée, éclats…)
   ════════════════════════════════════════════════════════════════════════════ */

const VERT = `
  attribute float aSize; attribute float aAlpha; attribute vec3 aColor;
  varying float vA; varying vec3 vC;
  void main(){ vA=aAlpha; vC=aColor;
    vec4 mv = modelViewMatrix * vec4(position,1.0);
    gl_PointSize = aSize * (260.0 / max(1.0, -mv.z));
    gl_Position = projectionMatrix * mv; }`;
const FRAG = `
  varying float vA; varying vec3 vC;
  void main(){ vec2 uv = gl_PointCoord - 0.5; float d = length(uv);
    float a = smoothstep(0.5, 0.05, d) * vA; if (a < 0.01) discard;
    gl_FragColor = vec4(vC, a); }`;

class Particles {
  private max: number;
  private additive: boolean;
  private gravity: boolean;
  private aliveCount = 0;
  private pos: Float32Array;
  private vel: Float32Array;
  private life: Float32Array;
  private maxL: Float32Array;
  private size: Float32Array;
  private col: Float32Array;
  private alpha: Float32Array;
  private cursor = 0;
  private geo: THREE.BufferGeometry;
  points: THREE.Points;

  constructor(max: number, additive = false, gravity = false) {
    this.max = max;
    this.additive = additive;
    this.gravity = gravity;
    this.pos = new Float32Array(max * 3);
    this.vel = new Float32Array(max * 3);
    this.life = new Float32Array(max);
    this.maxL = new Float32Array(max);
    this.size = new Float32Array(max);
    this.col = new Float32Array(max * 3);
    this.alpha = new Float32Array(max);
    this.geo = new THREE.BufferGeometry();
    this.geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    this.geo.setAttribute('aColor', new THREE.BufferAttribute(this.col, 3));
    this.geo.setAttribute('aSize', new THREE.BufferAttribute(this.size, 1));
    this.geo.setAttribute('aAlpha', new THREE.BufferAttribute(this.alpha, 1));
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      vertexShader: VERT,
      fragmentShader: FRAG,
    });
    this.points = new THREE.Points(this.geo, mat);
    this.points.frustumCulled = false;
  }

  addToScene(scene: THREE.Scene): void {
    scene.add(this.points);
  }

  spawn(x: number, y: number, z: number, vx: number, vy: number, vz: number, life: number, size: number, r: number, g: number, b: number): void {
    if (this.aliveCount >= this.max * 0.94) return;
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.max;
    this.pos[i * 3] = x;
    this.pos[i * 3 + 1] = y;
    this.pos[i * 3 + 2] = z;
    this.vel[i * 3] = vx;
    this.vel[i * 3 + 1] = vy;
    this.vel[i * 3 + 2] = vz;
    this.life[i] = life;
    this.maxL[i] = life;
    this.size[i] = size;
    this.col[i * 3] = r;
    this.col[i * 3 + 1] = g;
    this.col[i * 3 + 2] = b;
    this.alpha[i] = 0.01;
    this.aliveCount++;
  }

  update(dt: number): void {
    const g = this.gravity ? -4.5 : 0;
    this.aliveCount = 0;
    for (let i = 0; i < this.max; i++) {
      if (this.life[i] <= 0) {
        this.alpha[i] = 0;
        this.size[i] = 0.01;
        continue;
      }
      this.life[i] -= dt;
      if (this.life[i] <= 0) {
        this.alpha[i] = 0;
        this.size[i] = 0.01;
        continue;
      }
      this.aliveCount++;
      const age = this.maxL[i] - this.life[i];
      this.pos[i * 3] += this.vel[i * 3] * dt;
      this.pos[i * 3 + 1] += (this.vel[i * 3 + 1] + g) * dt;
      this.pos[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
      this.alpha[i] = Math.min(1, age * 5) * Math.min(1, this.life[i] * 5);
      this.size[i] *= 1 + dt * 0.9;
    }
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.aSize.needsUpdate = true;
    this.geo.attributes.aAlpha.needsUpdate = true;
  }

  reset(): void {
    this.life.fill(0);
    this.aliveCount = 0;
    this.geo.attributes.aAlpha.needsUpdate = true;
    this.geo.attributes.aSize.needsUpdate = true;
  }

  dispose(): void {
    if (this.points.parent) this.points.parent.remove(this.points);
    this.geo.dispose();
    (this.points.material as THREE.Material).dispose();
  }
}

/* ════════════════════════════════════════════════════════════════════════════
   Blocs physiques (murs, fondations, toiture, fenêtres…) — statiques au
   repos, activés (dynamiques) par les catastrophes.
   ════════════════════════════════════════════════════════════════════════════ */

interface Block {
  mesh: THREE.Object3D;
  body: CANNON.Body;
  mass: number;
  zone: string;
  kind: string;
  burning?: boolean;
  charred?: boolean;
  health?: number;
  origColor?: THREE.Color;
  spreadTimer?: number;
  smokeTimer?: number;
  flameTimer?: number;
  light?: THREE.PointLight | null;
  _shattered?: boolean;
  riskCloned?: boolean;
  baseColor?: THREE.Color;
}

interface BuildInfo {
  eaveH: number;
  ridgeH: number;
  halfW: number;
  edges: Edge[];
  C: { x: number; z: number };
}

interface EngineOpts {
  getIntensity: () => number;
}

/* ════════════════════════════════════════════════════════════════════════════
   Moteur 3D + physique (une instance par montage du composant)
   ════════════════════════════════════════════════════════════════════════════ */

class DisasterEngine {
  private container: HTMLDivElement;
  private diag: AdapterResult;
  private opts: EngineOpts;

  private renderer!: THREE.WebGLRenderer;
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private world!: CANNON.World;
  private matBlock!: CANNON.Material;
  private matGround!: CANNON.Material;

  private blocks: Block[] = [];
  private visuals: THREE.Object3D[] = [];
  private neighbors = new Map<Block, Block[]>();

  /* Matériaux PBR du bâtiment (slugs BDNB) */
  private mats: MaterialsBundle | null = null;
  private wallMat: THREE.MeshStandardMaterial | null = null;
  private roofMat: THREE.MeshStandardMaterial | null = null;

  /* Particules */
  private sysSwirl!: Particles;
  private sysDebris!: Particles;
  private sysFire!: Particles;
  private sysSmoke!: Particles;
  private sysTrail!: Particles;
  private sysBurst!: Particles;
  private sysBoom!: Particles;
  private sysSteam!: Particles;
  private sysAll: Particles[] = [];

  /* Tornade */
  private tornado = { active: false, cx: 0, cz: 0 };
  private funnel!: THREE.Mesh;
  private funnelInner!: THREE.Mesh;
  private funnelBase!: THREE.Mesh;
  private funnelRings: number[] = [];
  private funnelSegs: number[] = [];

  /* Inondation */
  private flood = { active: false, level: -0.6, max: 14, speed: 0.2 };
  private waterGeo!: THREE.PlaneGeometry;
  private water!: THREE.Mesh;

  /* Météores */
  private meteors = { active: false, timer: 1.2 };
  private meteorList: Array<{ mesh: THREE.Mesh; x: number; y: number; z: number; vx: number; vy: number; vz: number }> = [];
  private craters: THREE.Mesh[] = [];
  private meteorMat!: THREE.MeshStandardMaterial;
  private meteorGeo!: THREE.SphereGeometry;
  private flashLight!: THREE.PointLight;

  /* Séisme / grêle / incendie */
  private seisme = { active: false, timer: 0 };
  private grele = { active: false, timer: 0 };
  private hailList: Array<{ mesh: THREE.Mesh; x: number; y: number; z: number; vy: number }> = [];
  private fire = { active: false, burning: [] as Block[] };
  private fireLights: THREE.PointLight[] = [];

  /* Divers */
  private riskView = false;
  private shake = 0;
  private buildInfo: BuildInfo | null = null;

  private clock = new THREE.Clock();
  private acc = 0;
  private raf = 0;
  private ro?: ResizeObserver;
  private disposed = false;

  constructor(container: HTMLDivElement, diag: AdapterResult, opts: EngineOpts) {
    this.container = container;
    this.diag = diag;
    this.opts = opts;
  }

  /* ── Initialisation : rendu, scène, lumières, monde physique, maison ── */
  init(): void {
    const container = this.container;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 420;

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.renderer.outputEncoding = THREE.sRGBEncoding;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x9fc4e8);
    this.scene.fog = new THREE.Fog(0x9fc4e8, 250, 2300);

    this.camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 400);
    this.camera.position.set(24, 14, 30);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 4, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 5;
    this.controls.maxDistance = 1500;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05;

    /* Lighting (idem référence) : hémisphère + soleil directionnel ombré */
    const hemi = new THREE.HemisphereLight(0xbfd8ff, 0x7a5a3a, 1.1);
    this.scene.add(hemi);
    const sun = new THREE.DirectionalLight(0xfff2d8, 2.4);
    sun.position.set(16, 24, 12);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -22;
    sun.shadow.camera.right = 22;
    sun.shadow.camera.top = 22;
    sun.shadow.camera.bottom = -22;
    sun.shadow.camera.far = 70;
    this.scene.add(sun);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.25));

    /* Sol (la texture d'herbe du fichier de référence n'est pas livrée ici →
       fail-soft : couleur unie) */
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(2400, 2400),
      new THREE.MeshStandardMaterial({ color: 0x6f9556, roughness: 1 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    this.scene.add(ground);

    /* Monde physique (matériaux de contact bloc/sol) */
    this.world = new CANNON.World({ gravity: new CANNON.Vec3(0, -9.82, 0) });
    this.world.broadphase = new CANNON.SAPBroadphase(this.world);
    this.world.allowSleep = true;
    (this.world.solver as CANNON.GSSolver).iterations = 12;
    this.world.defaultContactMaterial.friction = 0.5;
    this.world.defaultContactMaterial.restitution = 0.05;
    this.matBlock = new CANNON.Material('block');
    this.matGround = new CANNON.Material('ground');
    this.world.addContactMaterial(
      new CANNON.ContactMaterial(this.matBlock, this.matGround, { friction: 0.9, restitution: 0.05 })
    );
    this.world.addContactMaterial(
      new CANNON.ContactMaterial(this.matBlock, this.matBlock, { friction: 0.65, restitution: 0.05 })
    );
    const planeBody = new CANNON.Body({ mass: 0, material: this.matGround });
    planeBody.addShape(new CANNON.Plane());
    planeBody.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
    this.world.addBody(planeBody);

    /* Surface d'eau (inondation) — sous le sol au départ, visible en crue */
    this.waterGeo = new THREE.PlaneGeometry(240, 240, 48, 48);
    this.waterGeo.rotateX(-Math.PI / 2);
    this.water = new THREE.Mesh(
      this.waterGeo,
      new THREE.MeshStandardMaterial({ color: 0x2a7fd4, transparent: true, opacity: 0.72, roughness: 0.15, metalness: 0.1 })
    );
    this.water.position.y = this.flood.level;
    this.scene.add(this.water);

    /* Particules */
    this.sysSwirl = new Particles(650, true);
    this.sysDebris = new Particles(260, false, true);
    this.sysFire = new Particles(380, true);
    this.sysSmoke = new Particles(320);
    this.sysTrail = new Particles(260, true);
    this.sysBurst = new Particles(380, true, true);
    this.sysBoom = new Particles(160);
    this.sysSteam = new Particles(180);
    this.sysAll = [this.sysSwirl, this.sysDebris, this.sysFire, this.sysSmoke, this.sysTrail, this.sysBurst, this.sysBoom, this.sysSteam];
    for (const s of this.sysAll) s.addToScene(this.scene);

    /* Entonnoir de tornade (maillé procéduralement dans updateFunnel) */
    this.funnel = new THREE.Mesh(
      new THREE.CylinderGeometry(4, 0.7, 16, 24, 12, true),
      new THREE.MeshBasicMaterial({ color: 0x7c828c, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false })
    );
    this.funnelInner = new THREE.Mesh(
      new THREE.CylinderGeometry(2.1, 0.35, 16, 24, 12, true),
      new THREE.MeshBasicMaterial({ color: 0x636a75, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false })
    );
    this.funnelBase = new THREE.Mesh(
      new THREE.CircleGeometry(1.6, 28),
      new THREE.MeshBasicMaterial({ color: 0x555b66, transparent: true, opacity: 0.16, depthWrite: false })
    );
    this.funnelBase.rotation.x = -Math.PI / 2;
    this.funnel.visible = this.funnelInner.visible = this.funnelBase.visible = false;
    this.scene.add(this.funnel, this.funnelInner, this.funnelBase);
    const F_RS = 24;
    for (const mesh of [this.funnel, this.funnelInner]) {
      const n = mesh.geometry.attributes.position.count;
      for (let i = 0; i < n; i++) {
        this.funnelRings.push(Math.floor(i / (F_RS + 1)));
        this.funnelSegs.push(i % (F_RS + 1));
      }
    }

    /* Météores : matériau + lumière de flash */
    this.meteorMat = new THREE.MeshStandardMaterial({ color: 0x33221a, emissive: 0xff7722, emissiveIntensity: 2.2 });
    this.meteorGeo = new THREE.SphereGeometry(0.42, 16, 16);
    this.flashLight = new THREE.PointLight(0xffd9a0, 0, 40);
    this.scene.add(this.flashLight);

    /* Incendie : pool de lumières de flamme */
    for (let i = 0; i < 8; i++) {
      const l = new THREE.PointLight(0xff8a3a, 0, 7, 2);
      this.scene.add(l);
      this.fireLights.push(l);
    }

    /* Construction du bâtiment depuis le contrat adapté */
    this.buildInfo = this.buildHouse();
    this.flood.max = Math.max(this.buildInfo.ridgeH * 1.35, 4);
    this.computeNeighbors();
    this.frameCamera();

    this.ro = new ResizeObserver(() => this.onResize());
    this.ro.observe(container);

    this.raf = requestAnimationFrame(this.loop);
  }

  /* ── Arêtes de l'emprise : footprint réel, sinon rectangle BDNB ── */
  private geometryEdges(g: DiagnosticGeometry): Edge[] {
    const fromFootprint = edgesFromFootprint(g.footprint as FootprintLike | undefined);
    if (fromFootprint.length > 0) return fromFootprint;
    const W = Math.max(1, g.largeur_m ?? 8);
    const L = Math.max(1, g.longueur_m ?? 8);
    return edgesFromRing([
      [-W / 2, -L / 2],
      [W / 2, -L / 2],
      [W / 2, L / 2],
      [-W / 2, L / 2],
    ]);
  }

  /* ── Matériaux PBR du bâtiment (slugs BDNB → couleurs + textures fail-soft) ── */
  private makeMaterials(g: DiagnosticGeometry): MaterialsBundle {
    this.wallMat = new THREE.MeshStandardMaterial({
      color: matColor(g.materiau_mur, PAL_MUR, '#ccc4a3'),
      roughness: 0.92,
      metalness: 0.0,
    });
    this.roofMat = new THREE.MeshStandardMaterial({
      color: matColor(g.materiau_toiture, PAL_TOIT, '#525259'),
      roughness: 0.6,
      metalness: 0.05,
    });
    const wtex = TEX_MUR[slugKey(g.materiau_mur, TEX_MUR) ?? ''];
    const rtex = TEX_TOIT[slugKey(g.materiau_toiture, TEX_TOIT) ?? ''];
    loadTex(wtex, 3, (t) => {
      if (this.wallMat) {
        this.wallMat.map = t;
        this.wallMat.needsUpdate = true;
      }
    });
    loadTex(rtex, 3, (t) => {
      if (this.roofMat) {
        this.roofMat.map = t;
        this.roofMat.needsUpdate = true;
      }
    });
    return {
      door: new THREE.MeshStandardMaterial({ color: 0x8a5a33, roughness: 0.85, metalness: 0 }),
      frame: new THREE.MeshStandardMaterial({ color: 0x5b4632, roughness: 0.75, metalness: 0.05 }),
      sill: new THREE.MeshStandardMaterial({ color: 0xcfc9bc, roughness: 0.8, metalness: 0 }),
      glass: new THREE.MeshStandardMaterial({ color: 0xb8dcff, roughness: 0.06, metalness: 0.25, transparent: true, opacity: 0.5 }),
      concrete: new THREE.MeshStandardMaterial({ color: 0x9a968c, roughness: 0.95, metalness: 0 }),
      slab: new THREE.MeshStandardMaterial({ color: 0xb8b2a6, roughness: 0.9, metalness: 0, side: THREE.DoubleSide }),
    };
  }

  /* ── Bloc physique statique (activé par les désastres) ── */
  private addBlock(
    x: number,
    y: number,
    z: number,
    geo: THREE.BufferGeometry,
    hw: [number, number, number],
    mat: THREE.Material,
    mass: number,
    euler: [number, number, number] | null,
    zone: string,
    kind: string
  ): Block {
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    if (euler) mesh.rotation.set(euler[0], euler[1], euler[2]);
    this.scene.add(mesh);
    const body = new CANNON.Body({ mass: 0, material: this.matBlock, type: CANNON.Body.STATIC });
    body.addShape(new CANNON.Box(new CANNON.Vec3(hw[0], hw[1], hw[2])));
    body.position.set(x, y, z);
    if (euler) body.quaternion.setFromEuler(euler[0], euler[1], euler[2]);
    body.allowSleep = true;
    body.sleepSpeedLimit = 0.3;
    body.sleepTimeLimit = 1.0;
    this.world.addBody(body);
    const b: Block = { mesh, body, mass, zone, kind };
    this.blocks.push(b);
    return b;
  }

  /* ── Construction du bâtiment (portage de buildHouse) ── */
  private buildHouse(): BuildInfo {
    const g: DiagnosticGeometry = this.diag.geometry || {};
    this.mats = this.makeMaterials(g);
    const edges = this.geometryEdges(g);
    const floors = Math.max(1, Math.min(6, g.floors_count ?? 2));
    const floorH = Math.max(2.2, g.hauteur_sous_plafond_m ?? 2.6);
    const eaveH = floors * floorH;
    const C = centroidOf(edges);
    const axis = dominantAxisDeg(edges);
    const perpW = (deg: number): number => {
      const a = (deg * Math.PI) / 180;
      const ux2 = Math.cos(a);
      const uz2 = Math.sin(a);
      let hw = 0;
      for (const e of edges)
        hw = Math.max(
          hw,
          Math.abs((e.x0 - C.x) * uz2 - (e.z0 - C.z) * ux2),
          Math.abs((e.x1 - C.x) * uz2 - (e.z1 - C.z) * ux2)
        );
      return hw;
    };
    const useAxis = perpW(axis) <= perpW(axis + 90) ? axis : axis + 90;
    const ux = Math.cos((useAxis * Math.PI) / 180);
    const uz = Math.sin((useAxis * Math.PI) / 180);
    const halfW = Math.max(1, perpW(useAxis));
    const rise = Math.max(2, halfW * Math.tan(((g.pente_toit_deg ?? 35) * Math.PI) / 180));
    const ridgeH = eaveH + rise;

    const CELL = 1.2;
    const WALL_TH = 0.5;

    /* ---- Murs (par étage, le long de chaque arête de l'emprise réelle) ---- */
    for (const e of edges) {
      const n = Math.max(1, Math.round(e.len / CELL));
      const bl = e.len / n;
      const yaw = Math.atan2(-e.dz, e.dx);
      for (let k = 0; k < floors; k++) {
        const cy = k * floorH + floorH / 2;
        for (let i = 0; i < n; i++) {
          const t = (i + 0.5) / n;
          const px = e.x0 + e.dx * t;
          const pz = e.z0 + e.dz * t;
          this.addBlock(
            px,
            cy,
            pz,
            new THREE.BoxGeometry(bl - 0.03, floorH - 0.03, WALL_TH),
            [bl / 2, floorH / 2, WALL_TH / 2],
            this.wallMat as THREE.MeshStandardMaterial,
            20,
            [0, yaw, 0],
            facadeOrientation(e.nx, e.nz),
            'wall'
          );
        }
      }
    }

    /* ---- Porte d'entrée (façade la plus longue si entree_facade absent) ---- */
    let entree: string | null = String(g.entree_facade || '').replace('murs_', '') ? g.entree_facade as string : null;
    if (!entree) {
      let bestEdge: Edge | null = null;
      let bestLen = 0;
      for (const e of edges) if (e.len > bestLen) {
        bestEdge = e;
        bestLen = e.len;
      }
      if (bestEdge) entree = facadeOrientation(bestEdge.nx, bestEdge.nz);
    }
    if (entree) {
      const doorOrient = String(entree).replace('murs_', '');
      let best: Edge | null = null;
      let bestLen = 0;
      for (const e of edges) if (facadeOrientation(e.nx, e.nz) === entree && e.len > bestLen) {
        best = e;
        bestLen = e.len;
      }
      if (best) {
        const n = Math.max(1, Math.round(best.len / CELL));
        const mid = Math.floor(n / 2);
        const t = (mid + 0.5) / n;
        const px = best.x0 + best.dx * t;
        const pz = best.z0 + best.dz * t;
        const yaw = Math.atan2(-best.dz, best.dx);
        // REMPLACE la cellule de mur (supprime le bloc qui chevauche) — deux
        // solides statiques profondément imbriqués explosent sous un désastre.
        const overlap = this.blocks.findIndex(
          (b) =>
            b.kind === 'wall' &&
            Math.abs(b.body.position.x - px) < 0.1 &&
            Math.abs(b.body.position.z - pz) < 0.1 &&
            Math.abs(b.body.position.y - floorH / 2) < 0.1
        );
        if (overlap >= 0) {
          const w = this.blocks[overlap];
          this.scene.remove(w.mesh);
          this.world.removeBody(w.body);
          this.blocks.splice(overlap, 1);
        }
        this.addBlock(
          px,
          floorH / 2,
          pz,
          new THREE.BoxGeometry(best.len / n - 0.03, floorH - 0.03, WALL_TH + 0.04),
          [best.len / n / 2, floorH / 2, WALL_TH / 2],
          this.mats!.door,
          20,
          [0, yaw, 0],
          'murs_' + doorOrient,
          'door'
        );
        // vantail : bloc physique (la porte s'arrache avec la maison) + poignée + vitrage
        const leaf = this.addBlock(
          px + best.nx * 0.34,
          1.15,
          pz + best.nz * 0.34,
          new THREE.BoxGeometry(1.25, 2.3, 0.08),
          [0.625, 1.15, 0.04],
          this.mats!.door,
          12,
          [0, yaw, 0],
          'murs_' + doorOrient,
          'doorleaf'
        );
        const knob = new THREE.Mesh(
          new THREE.SphereGeometry(0.05, 10, 10),
          new THREE.MeshStandardMaterial({ color: 0xdfcba8, roughness: 0.3, metalness: 0.9 })
        );
        knob.position.set(0.3, -0.18, -0.06);
        leaf.mesh.add(knob);
        const pane = new THREE.Mesh(new THREE.BoxGeometry(0.68, 0.5, 0.03), this.mats!.glass);
        pane.position.set(0, 0.58, -0.04);
        leaf.mesh.add(pane);
        // perron : deux marches devant l'entrée
        this.addBlock(
          px + best.nx * 0.62,
          0.075,
          pz + best.nz * 0.62,
          new THREE.BoxGeometry(2.1, 0.15, 0.4),
          [1.05, 0.075, 0.2],
          this.mats!.slab,
          30,
          [0, yaw, 0],
          'fondations',
          'step'
        );
        this.addBlock(
          px + best.nx * 1.07,
          0.15,
          pz + best.nz * 1.07,
          new THREE.BoxGeometry(2.1, 0.3, 0.4),
          [1.05, 0.15, 0.2],
          this.mats!.slab,
          30,
          [0, yaw, 0],
          'fondations',
          'step'
        );
      }
    }

    /* ---- Gouttières + descente d'eau (détail de façade, visuel) ---- */
    const gutMat = new THREE.MeshStandardMaterial({ color: 0x5f6672, roughness: 0.35, metalness: 0.75 });
    for (const e of edges) {
      const dir = new THREE.Vector3(e.dx, 0, e.dz).normalize();
      const gut = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, e.len, 8), gutMat);
      gut.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      gut.position.set((e.x0 + e.x1) / 2 + e.nx * 0.36, eaveH + 0.16, (e.z0 + e.z1) / 2 + e.nz * 0.36);
      gut.castShadow = true;
      this.scene.add(gut);
      this.visuals.push(gut);
    }
    if (edges.length > 0) {
      const e0 = edges[0];
      const down = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, eaveH + 0.25, 8), gutMat);
      down.position.set(e0.x0 + e0.nx * 0.36, (eaveH + 0.25) / 2, e0.z0 + e0.nz * 0.36);
      down.castShadow = true;
      this.scene.add(down);
      this.visuals.push(down);
    }

    /* ---- Fenêtres (procédurales : cadre, vitre, croisillons, appui, volets) ---- */
    for (const e of edges) {
      const n = Math.max(1, Math.min(3, Math.round(e.len / 4.5)));
      const yaw = Math.atan2(-e.dz, e.dx);
      const isEntry = entree !== null && facadeOrientation(e.nx, e.nz) === entree;
      for (let k = 0; k < floors; k++) {
        const cy = k * floorH + floorH * 0.55;
        for (let i = 0; i < n; i++) {
          const t = (i + 0.5) / n;
          if (isEntry && k === 0 && Math.abs(t - 0.5) < 0.18) continue; // la porte occupe le milieu
          const wx = e.x0 + e.dx * t + e.nx * 0.35;
          const wz = e.z0 + e.dz * t + e.nz * 0.35;
          this.makeWindow(wx, cy, wz, yaw, facadeOrientation(e.nx, e.nz));
        }
      }
    }

    /* ---- Cave / fondations (has_basement) ---- */
    const baseY = g.has_basement ? [-0.6, -1.6] : [-0.25];
    const zones = g.has_basement ? ['sous_sol', 'fondations'] : ['fondations'];
    for (const e of edges) {
      const n = Math.max(1, Math.round(e.len / CELL));
      const bl = e.len / n;
      const yaw = Math.atan2(-e.dz, e.dx);
      for (let i = 0; i < n; i++) {
        const t = (i + 0.5) / n;
        const px = e.x0 + e.dx * t;
        const pz = e.z0 + e.dz * t;
        baseY.forEach((y, idx) => {
          const h = idx === 0 ? 1.0 : 0.7;
          this.addBlock(
            px,
            y,
            pz,
            new THREE.BoxGeometry(bl - 0.03, h - 0.03, WALL_TH + (idx === 1 ? 0.25 : 0)),
            [bl / 2, h / 2, (WALL_TH + (idx === 1 ? 0.25 : 0)) / 2],
            this.mats!.concrete,
            30,
            [0, yaw, 0],
            zones[idx],
            'foundation'
          );
        });
      }
    }

    /* ---- Terre autour des fondations : la cave est ENTERRÉE comme en réalité ---- */
    {
      let bx0 = Infinity;
      let bx1 = -Infinity;
      let bz0 = Infinity;
      let bz1 = -Infinity;
      for (const e of edges) {
        bx0 = Math.min(bx0, e.x0, e.x1);
        bx1 = Math.max(bx1, e.x0, e.x1);
        bz0 = Math.min(bz0, e.z0, e.z1);
        bz1 = Math.max(bz1, e.z0, e.z1);
      }
      const W = bx1 - bx0 + 4;
      const D = bz1 - bz0 + 4;
      const top = -0.03;
      const bot = -2.7;
      const th = 2;
      const soil = new THREE.MeshStandardMaterial({ color: 0x7a5a3a, roughness: 1 });
      const earthBox = (w: number, h: number, d: number, x: number, y: number, z: number): void => {
        const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), soil);
        m.position.set(x, y, z);
        m.receiveShadow = true;
        this.scene.add(m);
        this.visuals.push(m);
      };
      const cy = (top + bot) / 2;
      const ch = top - bot;
      const mcx = (bx0 + bx1) / 2;
      const mcz = (bz0 + bz1) / 2;
      earthBox(W, ch, th, mcx, cy, bz0 - 1);
      earthBox(W, ch, th, mcx, cy, bz1 + 1);
      earthBox(th, ch, D, bx0 - 1, cy, mcz);
      earthBox(th, ch, D, bx1 + 1, cy, mcz);
      earthBox(W, 0.7, D, mcx, bot - 0.35, mcz);
    }

    /* ---- Toit à deux pans : versants pleins, pignons fermés, tuiles
           faîtières et cheminée (ou toit plat) ---- */
    if (String(g.roof_shape || 'deux_pans') === 'deux_pans') {
      let tmin = Infinity;
      let tmax = -Infinity;
      for (const e of edges) {
        const a = (e.x0 - C.x) * ux + (e.z0 - C.z) * uz;
        const b = (e.x1 - C.x) * ux + (e.z1 - C.z) * uz;
        if (a < tmin) tmin = a;
        if (b > tmax) tmax = b;
      }
      const span = Math.max(1, tmax - tmin);
      const cols = Math.max(2, Math.round(span / CELL));
      const rows = Math.max(2, Math.round(halfW / 1.2));
      const slopeLen = Math.hypot(rise, halfW);
      const lenX = span / cols - 0.04;
      const lenZ = slopeLen / rows - 0.04;
      const perp = [-uz, 0, ux];
      const X = [ux, 0, uz];

      for (const side of [-1, 1]) {
        const sDir = norm3([-perp[0] * side, rise / halfW, -perp[2] * side]);
        let N = cross3(X, sDir);
        if (N[1] < 0) N = [-N[0], -N[1], -N[2]];
        const Z = norm3(cross3(X, N));
        for (let j = 0; j < rows; j++) {
          const d = (side * halfW * (j + 0.5)) / rows;
          const y = ridgeH - (rise * Math.abs(d)) / halfW;
          for (let i = 0; i < cols; i++) {
            const t = tmin + (i + 0.5) * (span / cols);
            const mat = (this.roofMat as THREE.MeshStandardMaterial).clone();
            mat.color.offsetHSL(0, 0, (R() - 0.5) * 0.06);
            const b = this.addBlock(
              C.x + ux * t + perp[0] * d,
              y,
              C.z + uz * t + perp[2] * d,
              new THREE.BoxGeometry(lenX, 0.32, lenZ),
              [lenX / 2, 0.16, lenZ / 2],
              mat,
              8,
              null,
              'toiture',
              'roof'
            );
            const m = new THREE.Matrix4().makeBasis(
              new THREE.Vector3(X[0], X[1], X[2]),
              new THREE.Vector3(N[0], N[1], N[2]),
              new THREE.Vector3(Z[0], Z[1], Z[2])
            );
            b.mesh.quaternion.setFromRotationMatrix(m);
            b.body.quaternion.set(b.mesh.quaternion.x, b.mesh.quaternion.y, b.mesh.quaternion.z, b.mesh.quaternion.w);
          }
        }
      }

      /* pignons fermés : triangles aux deux extrémités du faîtage */
      const gRows = Math.max(2, Math.round(rise / 1.2));
      const gH = rise / gRows - 0.04;
      for (const tEnd of [tmin - 0.3, tmax + 0.3]) {
        for (let j = 0; j < gRows; j++) {
          const f = (j + 0.5) / gRows;
          const w = Math.max(0.3, 2 * halfW * (1 - f) - 0.04);
          const b = this.addBlock(
            C.x + ux * tEnd,
            eaveH + rise * f,
            C.z + uz * tEnd,
            new THREE.BoxGeometry(w, gH, WALL_TH + 0.06),
            [w / 2, gH / 2, (WALL_TH + 0.06) / 2],
            this.wallMat as THREE.MeshStandardMaterial,
            10,
            null,
            'toiture',
            'roof'
          );
          const m = new THREE.Matrix4().makeBasis(
            new THREE.Vector3(-perp[0], 0, -perp[2]),
            new THREE.Vector3(0, 1, 0),
            new THREE.Vector3(ux, 0, uz)
          );
          b.mesh.quaternion.setFromRotationMatrix(m);
          b.body.quaternion.set(b.mesh.quaternion.x, b.mesh.quaternion.y, b.mesh.quaternion.z, b.mesh.quaternion.w);
        }
      }

      /* tuiles faîtières le long du faîtage */
      const nCap = Math.max(3, Math.round(span / 0.7));
      const capYaw = Math.atan2(-uz, ux);
      for (let i = 0; i < nCap; i++) {
        const t = tmin + (i + 0.5) * (span / nCap);
        this.addBlock(
          C.x + ux * t,
          ridgeH + 0.05,
          C.z + uz * t,
          new THREE.BoxGeometry(span / nCap - 0.05, 0.2, 0.7),
          [(span / nCap - 0.05) / 2, 0.1, 0.35],
          this.roofMat as THREE.MeshStandardMaterial,
          6,
          [0, capYaw, 0],
          'toiture',
          'roof'
        );
      }

      /* cheminée sur le faîte */
      {
        const t = tmin + span * 0.35;
        const cx = C.x + ux * t;
        const cz = C.z + uz * t;
        this.addBlock(cx, ridgeH + 0.6, cz, new THREE.BoxGeometry(1.2, 0.9, 1.2), [0.6, 0.45, 0.6], this.mats!.concrete, 16, null, 'toiture', 'roof');
        this.addBlock(cx, ridgeH + 1.3, cz, new THREE.BoxGeometry(1.0, 0.5, 1.0), [0.5, 0.25, 0.5], this.mats!.concrete, 10, null, 'toiture', 'roof');
      }
    } else {
      /* Toit plat (immeuble) */
      const geo = new THREE.ShapeGeometry(shapeFromGeometry(g));
      geo.rotateX(-Math.PI / 2);
      const flat = new THREE.Mesh(geo, this.roofMat as THREE.MeshStandardMaterial);
      flat.position.y = ridgeH;
      flat.receiveShadow = true;
      this.scene.add(flat);
      this.visuals.push(flat);
    }

    /* ---- Dalles d'étage (visuelles) : Shape → ShapeGeometry ---- */
    const shape = shapeFromGeometry(g);
    const levels: number[] = g.has_basement ? [-1.0 + 0.02] : [];
    for (let k = 0; k < floors; k++) levels.push(k * floorH + 0.02);
    for (const y of levels) this.addSlabVisual(shape, y);

    return { eaveH, ridgeH, halfW, edges, C };
  }

  private addSlabVisual(shape: THREE.Shape, y: number): void {
    const geo = new THREE.ShapeGeometry(shape);
    geo.rotateX(-Math.PI / 2);
    const mesh = new THREE.Mesh(geo, this.mats!.slab);
    mesh.position.y = y;
    mesh.receiveShadow = true;
    this.scene.add(mesh);
    this.visuals.push(mesh);
  }

  /* ── Fenêtre procédurale : cadre, vitre, croisillons, appui, volets ── */
  private makeWindow(wx: number, wy: number, wz: number, yaw: number, zone: string): void {
    const g = new THREE.Group();
    const W = 1.5;
    const H = 1.3;
    const T = 0.14;
    const frame = new THREE.Mesh(new THREE.BoxGeometry(W, H, T), this.mats!.frame);
    frame.castShadow = true;
    frame.receiveShadow = true;
    const glass = new THREE.Mesh(new THREE.BoxGeometry(W - 0.2, H - 0.2, 0.05), this.mats!.glass);
    glass.position.z = T / 2 + 0.02;
    const barV = new THREE.Mesh(new THREE.BoxGeometry(0.07, H - 0.25, 0.08), this.mats!.frame);
    const barH = new THREE.Mesh(new THREE.BoxGeometry(W - 0.25, 0.07, 0.08), this.mats!.frame);
    const sill = new THREE.Mesh(new THREE.BoxGeometry(W + 0.2, 0.09, 0.2), this.mats!.sill);
    sill.position.set(0, -H / 2 - 0.02, 0.04);
    sill.castShadow = true;
    const shutter = new THREE.Mesh(new THREE.BoxGeometry(0.45, H - 0.05, 0.06), this.mats!.frame);
    shutter.castShadow = true;
    const shutterL = shutter.clone();
    shutterL.position.set(-0.6, 0, -0.1);
    const shutterR = shutter.clone();
    shutterR.position.set(0.6, 0, -0.1);
    g.add(frame, glass, barV, barH, sill, shutterL, shutterR);
    g.position.set(wx, wy, wz);
    g.rotation.y = yaw;
    g.userData.isWindow = true;
    this.scene.add(g);
    // corps physique : la fenêtre est un vrai bloc (arrachée / projetée / brisée)
    const body = new CANNON.Body({ mass: 0, material: this.matBlock, type: CANNON.Body.STATIC });
    body.addShape(new CANNON.Box(new CANNON.Vec3(W / 2, H / 2, T / 2)));
    body.position.set(wx, wy, wz);
    body.quaternion.setFromEuler(0, yaw, 0);
    body.allowSleep = true;
    body.sleepSpeedLimit = 0.3;
    body.sleepTimeLimit = 1.0;
    this.world.addBody(body);
    const b: Block = { mesh: g, body, mass: 3, zone: zone || 'murs_nord', kind: 'window' };
    this.blocks.push(b);
  }

  /* Fenêtre brisée (météore proche / propagation d'incendie) : vol en éclats */
  private shatterWindow(b: Block): void {
    if (!b || b._shattered) return;
    b._shattered = true;
    b.charred = true;
    this.scene.remove(b.mesh);
    b.mesh.traverse((o) => {
      if ((o as THREE.Mesh).geometry) (o as THREE.Mesh).geometry.dispose();
    });
    this.world.removeBody(b.body);
    const i = this.blocks.indexOf(b);
    if (i >= 0) this.blocks.splice(i, 1);
    const p = b.mesh.position;
    for (let s2 = 0; s2 < 9; s2++) {
      this.sysDebris.spawn(
        p.x,
        p.y,
        p.z,
        RANGE(-7, 7),
        RANGE(-3, 6),
        RANGE(-7, 7),
        RANGE(0.5, 1.1),
        RANGE(0.12, 0.3),
        0.72 + R() * 0.15,
        0.82 + R() * 0.15,
        1
      );
    }
  }

  /* ── Activation d'un bloc (statique → dynamique avec sa masse réelle) ── */
  private activate(b: Block): void {
    if (b.body.type !== CANNON.Body.DYNAMIC) {
      b.body.mass = b.mass;
      b.body.type = CANNON.Body.DYNAMIC;
      b.body.updateMassProperties();
    }
    b.body.wakeUp();
  }

  /* ══════════════════════════════════════════════════════════════════════════
     TORNADE
     ══════════════════════════════════════════════════════════════════════════ */

  private updateFunnel(t: number): void {
    if (!this.tornado.active) return;
    const cx = this.tornado.cx;
    const cz = this.tornado.cz;
    this.funnel.position.set(cx, 8, cz);
    this.funnelInner.position.set(cx, 8, cz);
    this.funnelBase.position.set(cx, 0.06, cz);
    this.funnel.rotation.x = Math.sin(t * 2.1) * 0.05;
    this.funnel.rotation.z = Math.cos(t * 1.7) * 0.05;
    const swirl = (mesh: THREE.Mesh, r0: number, r1: number, amp: number): void => {
      const pos = mesh.geometry.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        const h = this.funnelRings[i] / 13;
        const rr = THREE.MathUtils.lerp(r0, r1, h) + Math.sin(t * 4 + h * 6) * amp;
        const a = (this.funnelSegs[i] / 24) * Math.PI * 2 + Math.sin(t * 2.5 + h * 7) * 0.4 * h;
        pos.setXYZ(i, Math.cos(a) * rr, h * 16, Math.sin(a) * rr);
      }
      pos.needsUpdate = true;
      mesh.geometry.computeVertexNormals();
    };
    swirl(this.funnel, 0.7, 4, 0.2);
    swirl(this.funnelInner, 0.35, 2.1, 0.12);
    const s = 1.4 + Math.sin(t * 5) * 0.15;
    this.funnelBase.scale.set(s, s, s);
  }

  private updateTornado(t: number, dt: number): void {
    if (!this.tornado.active) return;
    const I = this.opts.getIntensity();
    const T = t * 0.45;
    // la tornade balaie le quartier (rayon élargi) : elle arrache les éléments
    this.tornado.cx = Math.sin(T) * 40 + Math.sin(T * 0.33) * 10;
    this.tornado.cz = Math.cos(T * 0.75) * 44 + Math.sin(T * 1.7) * 10;
    const cx = this.tornado.cx;
    const cz = this.tornado.cz;
    const R_INF = 13;
    for (const b of this.blocks) {
      const dx = b.body.position.x - cx;
      const dz = b.body.position.z - cz;
      const d = Math.sqrt(dx * dx + dz * dz);
      if (d < R_INF && d > 0.001) {
        this.activate(b);
        const fall = 1 - d / R_INF;
        const tx = -dz / d;
        const tz = dx / d;
        const swirl = (13 * fall + 3.5) * Math.min(1, fall * 2 + 0.3);
        const vx = tx * swirl - (dx / d) * 1.6 * fall;
        const vz = tz * swirl - (dz / d) * 1.6 * fall;
        const vy = 10 * fall + 6;
        const k = 0.18 * I;
        b.body.velocity.x += (vx - b.body.velocity.x) * k;
        b.body.velocity.z += (vz - b.body.velocity.z) * k;
        b.body.velocity.y += (vy - b.body.velocity.y) * 0.24;
        b.body.angularVelocity.y += 2.2 * dt * 10;
        b.body.wakeUp();
      }
    }
    for (let i = 0; i < 3; i++) {
      const h = R() * 16;
      const rr = R() * 3.2;
      const a = R() * Math.PI * 2 + t * 4;
      this.sysSwirl.spawn(
        cx + Math.cos(a) * rr,
        h,
        cz + Math.sin(a) * rr,
        -Math.sin(a) * 4 + (R() - 0.5),
        3.5 + R() * 2,
        Math.cos(a) * 4 + (R() - 0.5),
        RANGE(1, 1.8),
        RANGE(0.25, 0.6),
        0.45 + R() * 0.1,
        0.47 + R() * 0.1,
        0.52 + R() * 0.1
      );
    }
    if (R() < 0.6) {
      this.sysDebris.spawn(
        cx + RANGE(-1.8, 1.8),
        0.4,
        cz + RANGE(-1.8, 1.8),
        RANGE(-3, 3),
        RANGE(4, 10),
        RANGE(-3, 3),
        RANGE(0.8, 1.6),
        RANGE(0.25, 0.5),
        0.5 + R() * 0.15,
        0.42 + R() * 0.12,
        0.3 + R() * 0.1
      );
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     INONDATION
     ══════════════════════════════════════════════════════════════════════════ */

  private waveHeight(x: number, z: number, t: number): number {
    return (
      Math.sin(x * 0.55 + t * 1.9) * 0.32 +
      Math.sin(z * 0.45 + t * 2.3) * 0.28 +
      Math.sin((x + z) * 0.3 + t * 1.1) * 0.18
    );
  }

  private updateWater(t: number, dt: number): void {
    const I = this.opts.getIntensity();
    const pos = this.waterGeo.attributes.position;
    for (let i = 0; i < pos.count; i++) pos.setY(i, this.waveHeight(pos.getX(i), pos.getZ(i), t));
    pos.needsUpdate = true;
    this.waterGeo.computeVertexNormals();
    if (!this.flood.active && this.flood.level < -0.4) return;
    if (this.flood.active) {
      this.flood.level = Math.min(this.flood.max, this.flood.level + dt * 0.2 * I);
      if (R() < 0.4)
        this.sysSteam.spawn(
          RANGE(-6, 6),
          this.flood.level + 0.1,
          RANGE(-10, 10),
          RANGE(-0.4, 0.4),
          RANGE(0.3, 1),
          RANGE(-0.4, 0.4),
          RANGE(0.5, 1.1),
          RANGE(0.18, 0.4),
          0.75 + R() * 0.2,
          0.85 + R() * 0.15,
          1
        );
    }
    this.water.position.y = this.flood.level;
    for (const b of this.blocks) {
      const p = b.body.position;
      const shape0 = b.body.shapes[0] as CANNON.Box | undefined;
      const halfH = shape0 && shape0.halfExtents ? shape0.halfExtents.y : 0.4;
      const bottom = p.y - halfH;
      const top = p.y + halfH;
      const level = this.flood.level + this.waveHeight(p.x, p.z, t);
      if (level <= bottom + 0.1) continue;
      this.activate(b);
      const frac = Math.min(1, (level - bottom) / (top - bottom));
      const push = b.body.mass * 9.82 * 1.65 * frac * (0.6 + 0.4 * I);
      b.body.applyForce(new CANNON.Vec3(0, push, 0));
      b.body.linearDamping = 0.25 + 0.5 * frac;
      b.body.angularDamping = 0.6 * frac + 0.1;
      b.body.wakeUp();
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     MÉTÉORES
     ══════════════════════════════════════════════════════════════════════════ */

  private spawnMeteor(): void {
    const tx = RANGE(-45, 45);
    const tz = RANGE(-60, 60);
    const sx = tx + RANGE(-16, 16);
    const sz = tz + RANGE(-16, 16);
    const mesh = new THREE.Mesh(this.meteorGeo, this.meteorMat);
    const dir = new THREE.Vector3(tx - sx, 0.15 - 34, tz - sz).normalize().multiplyScalar(52);
    this.meteorList.push({ mesh, x: sx, y: 34, z: sz, vx: dir.x, vy: dir.y, vz: dir.z });
    this.scene.add(mesh);
  }

  private explode(x: number, y: number, z: number): void {
    const I = this.opts.getIntensity();
    this.flashLight.position.set(x, y, z);
    this.flashLight.color.set(0xffd9a0);
    this.flashLight.intensity = 260;
    for (let i = 0; i < 42; i++) {
      const a = R() * Math.PI * 2;
      const u = R() * 2 - 1;
      const sp = RANGE(7, 15);
      this.sysBurst.spawn(
        x,
        y,
        z,
        Math.cos(a) * Math.sqrt(1 - u * u) * sp,
        u * sp * 0.7 + 3,
        Math.sin(a) * Math.sqrt(1 - u * u) * sp,
        RANGE(0.4, 0.9),
        RANGE(0.7, 1.4),
        1,
        0.35 + R() * 0.2,
        0.1 + R() * 0.15
      );
    }
    for (let i = 0; i < 18; i++) {
      this.sysBoom.spawn(
        x + RANGE(-0.6, 0.6),
        y + RANGE(0, 0.5),
        z + RANGE(-0.6, 0.6),
        RANGE(-1.5, 1.5),
        RANGE(1, 3),
        RANGE(-1.5, 1.5),
        RANGE(1.2, 2.4),
        RANGE(0.8, 1.6),
        0.3 + R() * 0.1,
        0.3 + R() * 0.1,
        0.3 + R() * 0.1
      );
    }
    const crater = new THREE.Mesh(
      new THREE.CircleGeometry(0.7, 24),
      new THREE.MeshBasicMaterial({ color: 0x241a12, transparent: true, opacity: 0.4, depthWrite: false })
    );
    crater.rotation.x = -Math.PI / 2;
    crater.rotation.z = R() * Math.PI;
    const s = RANGE(0.8, 1.6);
    crater.scale.set(s, s, 1);
    crater.position.set(x, 0.03, z);
    this.scene.add(crater);
    this.craters.push(crater);
    if (this.craters.length > 24) {
      const old = this.craters.shift() as THREE.Mesh;
      this.scene.remove(old);
      old.geometry.dispose();
      (old.material as THREE.Material).dispose();
    }
    for (let bi = this.blocks.length - 1; bi >= 0; bi--) {
      const b = this.blocks[bi];
      const p = b.body.position;
      const dx = p.x - x;
      const dy = p.y - y;
      const dz = p.z - z;
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (d < 14 && d > 0.01) {
        if (b.kind === 'window' && d < 6.5) {
          this.shatterWindow(b);
          continue;
        }
        this.activate(b);
        const f = 1 - d / 14;
        b.body.applyImpulse(
          new CANNON.Vec3((dx / d) * 17 * f * I, (dy / d) * 17 * f * I + 5 * f, (dz / d) * 17 * f * I),
          new CANNON.Vec3(RANGE(-0.3, 0.3), RANGE(-0.3, 0.3), RANGE(-0.3, 0.3))
        );
        b.body.angularVelocity.set(RANGE(-6, 6) * I, RANGE(-6, 6) * I, RANGE(-6, 6) * I);
      }
    }
    this.shake += 0.5 * I;
  }

  private updateMeteors(dt: number): void {
    const I = this.opts.getIntensity();
    this.flashLight.intensity *= Math.exp(-9 * dt);
    if (this.flashLight.intensity < 0.5) this.flashLight.intensity = 0;
    if (this.meteors.active) {
      this.meteors.timer -= dt;
      if (this.meteors.timer <= 0) {
        this.spawnMeteor();
        this.meteors.timer = RANGE(1.3, 2.4) / I;
      }
    }
    for (let i = this.meteorList.length - 1; i >= 0; i--) {
      const m = this.meteorList[i];
      m.x += m.vx * dt;
      m.y += m.vy * dt;
      m.z += m.vz * dt;
      m.mesh.position.set(m.x, m.y, m.z);
      this.sysTrail.spawn(
        m.x,
        m.y,
        m.z,
        RANGE(-0.6, 0.6),
        RANGE(-0.6, 0.6),
        RANGE(-0.6, 0.6),
        RANGE(0.3, 0.55),
        RANGE(0.9, 1.5),
        1,
        0.55 + R() * 0.25,
        0.15 + R() * 0.15
      );
      if (Math.abs(m.x) < 8 && Math.abs(m.z) < 16 && m.y < 11 && m.y > 1.2) {
        this.explode(m.x, m.y, m.z);
        this.scene.remove(m.mesh);
        m.mesh.geometry.dispose();
        this.meteorList.splice(i, 1);
        continue;
      }
      if (m.y <= 0.18) {
        this.explode(m.x, 0.2, m.z);
        this.scene.remove(m.mesh);
        m.mesh.geometry.dispose();
        this.meteorList.splice(i, 1);
      }
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     SÉISME
     ══════════════════════════════════════════════════════════════════════════ */

  private updateSeisme(dt: number): void {
    if (!this.seisme.active) return;
    const I = this.opts.getIntensity();
    this.seisme.timer -= dt;
    if (this.seisme.timer <= 0) {
      this.seisme.timer = RANGE(0.9, 1.8);
      const amp = RANGE(1.2, 2.6) * I;
      this.shake += amp;
      for (let i = 0; i < 18; i++) {
        this.sysBurst.spawn(
          RANGE(-16, 16),
          RANGE(0, 0.6),
          RANGE(-24, 24),
          RANGE(-2.5, 2.5),
          RANGE(0.5, 3),
          RANGE(-2.5, 2.5),
          RANGE(0.4, 0.9),
          RANGE(0.5, 1.2),
          0.6,
          0.5,
          0.4
        );
      }
      const cibles = this.blocks.filter((b) => b.body.type === CANNON.Body.STATIC && b.kind !== 'window');
      for (let k = 0; k < Math.min(3, cibles.length); k++) {
        const b = cibles[Math.floor(R() * cibles.length)];
        this.activate(b);
        b.body.applyImpulse(
          new CANNON.Vec3(RANGE(-2, 2), RANGE(1.5, 4), RANGE(-2, 2)),
          new CANNON.Vec3(RANGE(-0.2, 0.2), RANGE(-0.2, 0.2), RANGE(-0.2, 0.2))
        );
        b.body.angularVelocity.set(RANGE(-4, 4), RANGE(-4, 4), RANGE(-4, 4));
      }
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     GRÊLE
     ══════════════════════════════════════════════════════════════════════════ */

  private hailMat = new THREE.MeshStandardMaterial({ color: 0xdfeaff, roughness: 0.15, metalness: 0.1, transparent: true, opacity: 0.95 });
  private hailGeo = new THREE.SphereGeometry(0.16, 10, 10);

  private spawnHail(): void {
    const sx = RANGE(-15, 15);
    const sz = RANGE(-24, 24);
    const mesh = new THREE.Mesh(this.hailGeo, this.hailMat);
    this.hailList.push({ mesh, x: sx, y: RANGE(14, 20), z: sz, vy: RANGE(-22, -14) });
    this.scene.add(mesh);
  }

  private updateGrele(dt: number): void {
    const I = this.opts.getIntensity();
    if (this.grele.active) {
      this.grele.timer -= dt;
      if (this.grele.timer <= 0) {
        this.grele.timer = RANGE(0.15, 0.3) / I;
        for (let i = 0; i < 10; i++) this.spawnHail();
      }
    }
    for (let i = this.hailList.length - 1; i >= 0; i--) {
      const h = this.hailList[i];
      h.y += h.vy * dt;
      h.mesh.position.set(h.x, h.y, h.z);
      if (h.y <= 0.08) {
        this.scene.remove(h.mesh);
        h.mesh.geometry.dispose();
        this.hailList.splice(i, 1);
        for (let k = 0; k < 5; k++) {
          this.sysBurst.spawn(
            h.x,
            h.y,
            h.z,
            RANGE(-1.2, 1.2),
            RANGE(0.4, 2),
            RANGE(-1.2, 1.2),
            RANGE(0.05, 0.12),
            RANGE(0.15, 0.35),
            0.85,
            0.92,
            1
          );
        }
        /* la toiture non protégée se dégrade : ternit à chaque impact (plafonné) */
        const roof = this.blocks.find(
          (b) =>
            b.kind === 'roof' &&
            Math.abs(b.body.position.x - h.x) < 1 &&
            Math.abs(b.body.position.z - h.z) < 1 &&
            b.body.position.y > 2
        );
        if (roof) {
          const mat = (roof.mesh as THREE.Mesh).material as THREE.MeshStandardMaterial;
          if (!mat.userData.hail) mat.userData.hail = 0;
          if ((mat.userData.hail as number) < 40) {
            mat.userData.hail++;
            mat.color.multiplyScalar(0.992);
          }
        }
        /* les vitres peuvent éclater sous la grêle */
        const win = this.blocks.find(
          (b) =>
            b.kind === 'window' &&
            Math.abs(b.body.position.x - h.x) < 0.8 &&
            Math.abs(b.body.position.z - h.z) < 0.8 &&
            b.body.position.y > 1.5
        );
        if (win && R() < 0.12) this.shatterWindow(win);
      }
    }
    if (this.hailList.length > 260) {
      const old = this.hailList.shift() as { mesh: THREE.Mesh };
      this.scene.remove(old.mesh);
      old.mesh.geometry.dispose();
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     INCENDIE
     ══════════════════════════════════════════════════════════════════════════ */

  private computeNeighbors(): void {
    this.neighbors = new Map();
    for (const a of this.blocks) {
      const list: Block[] = [];
      for (const b of this.blocks) {
        if (a === b) continue;
        if (a.body.position.distanceTo(b.body.position) < 1.5) list.push(b);
      }
      this.neighbors.set(a, list);
    }
  }

  private ignite(b: Block): void {
    if (b.burning || b.charred) return;
    if (b.kind === 'window') {
      this.shatterWindow(b);
      return;
    }
    if (this.fire.burning.length >= 120) return;
    b.burning = true;
    b.health = 100;
    const mesh = b.mesh as THREE.Mesh;
    const mat = mesh.material as THREE.MeshStandardMaterial;
    b.origColor = mat.color ? mat.color.clone() : new THREE.Color(0xffffff);
    mesh.material = mat.clone();
    b.spreadTimer = 0.8;
    b.smokeTimer = 0;
    b.flameTimer = 0;
    b.light = null;
    for (const l of this.fireLights) {
      if (!l.userData.used) {
        b.light = l;
        l.userData.used = true;
        break;
      }
    }
    this.fire.burning.push(b);
  }

  private updateBurnVisual(b: Block, t: number, dt: number): void {
    const hf = Math.max(0, (b.health ?? 0) / 100);
    const mat = (b.mesh as THREE.Mesh).material as THREE.MeshStandardMaterial;
    const c = mat.color;
    c.copy(b.origColor || new THREE.Color(0xffffff)).lerp(new THREE.Color(0x1c1a18), 1 - hf);
    mat.emissive = mat.emissive || new THREE.Color(0);
    mat.emissive.set(0xff5500).multiplyScalar(hf * 0.7);
    b.flameTimer = (b.flameTimer ?? 0) - dt;
    if (b.flameTimer <= 0) {
      b.flameTimer = 0.035;
      const p = b.mesh.position;
      this.sysFire.spawn(
        p.x + RANGE(-0.25, 0.25),
        p.y + 0.4,
        p.z + RANGE(-0.25, 0.25),
        RANGE(-0.4, 0.4),
        RANGE(1.8, 3.4),
        RANGE(-0.4, 0.4),
        RANGE(0.4, 0.85),
        RANGE(0.55, 0.9),
        0.9 + R() * 0.1,
        RANGE(0.35, 0.55),
        0.08
      );
    }
    b.smokeTimer = (b.smokeTimer ?? 0) - dt;
    if (b.smokeTimer <= 0) {
      b.smokeTimer = 0.25;
      const p = b.mesh.position;
      this.sysSmoke.spawn(
        p.x + RANGE(-0.2, 0.2),
        p.y + 0.5,
        p.z + RANGE(-0.2, 0.2),
        RANGE(-0.3, 0.3),
        RANGE(1.2, 2),
        RANGE(-0.3, 0.3),
        RANGE(1.2, 2.2),
        RANGE(0.45, 0.8),
        0.28 + R() * 0.05,
        0.28 + R() * 0.05,
        0.3 + R() * 0.05
      );
    }
    if (b.light) {
      b.light.position.copy(b.mesh.position).y += 0.4;
      b.light.intensity = (26 + Math.sin(t * 40 + (b.health ?? 0)) * 9 + R() * 6) * hf;
    }
  }

  private char(b: Block): void {
    b.charred = true;
    b.burning = false;
    const mat = (b.mesh as THREE.Mesh).material as THREE.MeshStandardMaterial;
    mat.emissive.set(0x000000);
    mat.color.set(0x23201c);
    this.activate(b);
    b.body.applyImpulse(new CANNON.Vec3(RANGE(-0.3, 0.3), 0.9, RANGE(-0.3, 0.3)));
    const p = b.mesh.position;
    for (let i = 0; i < 4; i++) {
      this.sysSmoke.spawn(
        p.x + RANGE(-0.2, 0.2),
        p.y + 0.5,
        p.z + RANGE(-0.2, 0.2),
        RANGE(-0.5, 0.5),
        RANGE(1.5, 3),
        RANGE(-0.5, 0.5),
        RANGE(1.5, 2.6),
        RANGE(0.7, 1.2),
        0.25,
        0.25,
        0.27
      );
    }
    if (b.light) {
      b.light.intensity = 0;
      b.light.userData.used = false;
      b.light = null;
    }
  }

  private updateFire(t: number, dt: number): void {
    if (!this.fire.active) {
      /* Désactivé : les blocs déjà en feu continuent de se consumer (plus vite) */
      for (const b of this.fire.burning) {
        b.health = (b.health ?? 0) - dt * 20;
        this.updateBurnVisual(b, t, dt);
        if ((b.health ?? 0) <= 0) this.char(b);
      }
      this.fire.burning = this.fire.burning.filter((b) => !b.charred);
    }
    const I = this.opts.getIntensity();
    for (let i = this.fire.burning.length - 1; i >= 0; i--) {
      const b = this.fire.burning[i];
      b.health = (b.health ?? 0) - dt * 20;
      if ((b.health ?? 0) < 65) {
        b.spreadTimer = (b.spreadTimer ?? 0) - dt;
        if (b.spreadTimer <= 0) {
          b.spreadTimer = RANGE(0.5, 1);
          for (const n of this.neighbors.get(b) || []) {
            if (!n.burning && !n.charred && R() < 0.5 * I) this.ignite(n);
          }
        }
      }
      this.updateBurnVisual(b, t, dt);
      if ((b.health ?? 0) <= 0) this.char(b);
    }
    this.fire.burning = this.fire.burning.filter((b) => !b.charred);
  }

  /* ══════════════════════════════════════════════════════════════════════════
     Vue risque : coloration vert → rouge depuis zones[].risque
     ══════════════════════════════════════════════════════════════════════════ */

  setRiskView(on: boolean): void {
    this.riskView = on;
    for (const b of this.blocks) {
      if (b.kind === 'window') continue; // les fenêtres gardent leur vitrage
      const mesh = b.mesh as THREE.Mesh;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (!mat || !mat.color) continue;
      if (on && !b.riskCloned) {
        b.riskCloned = true;
        b.baseColor = mat.color.clone();
        mesh.material = mat.clone();
      }
      const c = (mesh.material as THREE.MeshStandardMaterial).color;
      if (on) {
        const r = this.diag.zones?.[b.zone]?.risque ?? 0;
        c.setHSL((1 - r / 100) * 0.33, 0.75, 0.55);
      } else if (b.riskCloned) {
        c.copy(b.baseColor as THREE.Color);
        const m2 = mesh.material as THREE.MeshStandardMaterial;
        if (m2.emissive) m2.emissive.set(0x000000);
      }
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════
     Contrôle des catastrophes
     ══════════════════════════════════════════════════════════════════════════ */

  private isActive(code: ScenarioCode): boolean {
    switch (code) {
      case 'tornado':
        return this.tornado.active;
      case 'flood':
        return this.flood.active;
      case 'meteors':
        return this.meteors.active;
      case 'fire':
        return this.fire.active;
      case 'seisme':
        return this.seisme.active;
      case 'grele':
        return this.grele.active;
    }
  }

  setDisaster(code: ScenarioCode, on: boolean): void {
    if (this.isActive(code) !== on) this.toggleDisaster(code);
  }

  stopAllDisasters(): void {
    for (const c of ALL_SCENARIOS) if (this.isActive(c)) this.toggleDisaster(c);
  }

  /** Diagnostic (tests/preview) : état interne de la simulation. */
  debugState(): Record<string, unknown> {
    return {
      dynamicBlocks: this.blocks.filter((b) => b.body.type === CANNON.Body.DYNAMIC).length,
      blocks: this.blocks.length,
      activeScenario: ALL_SCENARIOS.find((c) => this.isActive(c)) ?? null,
      floodLevel: Math.round(this.flood.level * 100) / 100,
      floodMax: Math.round(this.flood.max * 100) / 100,
      burning: this.fire.burning.length,
      meteors: this.meteorList.length,
      hail: this.hailList.length,
      shaking: Math.round(this.shake * 1000) / 1000,
    };
  }

  private toggleDisaster(code: ScenarioCode): void {
    if (code === 'tornado') {
      this.tornado.active = !this.tornado.active;
      this.funnel.visible = this.funnelInner.visible = this.funnelBase.visible = this.tornado.active;
    } else if (code === 'flood') {
      this.flood.active = !this.flood.active;
      if (this.flood.active && this.flood.level < -0.4) this.flood.level = -0.3;
    } else if (code === 'meteors') {
      this.meteors.active = !this.meteors.active;
      if (this.meteors.active) this.meteors.timer = 0.8;
    } else if (code === 'fire') {
      this.fire.active = !this.fire.active;
      if (this.fire.active && this.fire.burning.length === 0) {
        const starter = this.blocks.find((b) => b.kind === 'roof') || this.blocks.find((b) => b.kind === 'wall');
        if (starter) this.ignite(starter);
        else this.fire.active = false;
      }
    } else if (code === 'seisme') {
      this.seisme.active = !this.seisme.active;
      if (this.seisme.active) {
        this.seisme.timer = 0.4;
        this.shake += 0.6;
      }
    } else if (code === 'grele') {
      this.grele.active = !this.grele.active;
      if (this.grele.active) this.grele.timer = 0.3;
    }
  }

  /* ── Cadrage caméra sur la maison construite ── */
  private frameCamera(): void {
    const info = this.buildInfo;
    if (!info) return;
    const top = info.ridgeH;
    const r = Math.max(info.halfW * 3.4, top * 2.4, 14);
    this.controls.target.set(0, top * 0.55, 0);
    const az = 0.85;
    this.camera.position.set(Math.sin(az) * r, top * 0.95, Math.cos(az) * r);
    this.camera.lookAt(this.controls.target);
  }

  /* ── Boucle de rendu ── */
  private loop = (): void => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.loop);

    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.elapsedTime;
    this.acc += dt;
    while (this.acc >= STEP) {
      this.world.step(STEP);
      this.acc -= STEP;
    }

    this.updateTornado(t, dt);
    this.updateWater(t, dt);
    this.updateMeteors(dt);
    this.updateFire(t, dt);
    this.updateSeisme(dt);
    this.updateGrele(dt);
    this.updateFunnel(t);

    for (const b of this.blocks) {
      b.mesh.position.set(b.body.position.x, b.body.position.y, b.body.position.z);
      b.mesh.quaternion.set(b.body.quaternion.x, b.body.quaternion.y, b.body.quaternion.z, b.body.quaternion.w);
    }
    for (const s of this.sysAll) s.update(dt);

    this.controls.update();
    this.applyShake(dt);
    this.renderer.render(this.scene, this.camera);
  };

  private applyShake(dt: number): void {
    if (this.shake > 0.001) {
      this.camera.position.x += (R() - 0.5) * this.shake;
      this.camera.position.y += (R() - 0.5) * this.shake;
      this.camera.position.z += (R() - 0.5) * this.shake;
      this.shake *= Math.exp(-2.8 * dt);
    }
  }

  private onResize(): void {
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro?.disconnect();
    this.controls?.dispose();
    for (const s of this.sysAll) s.dispose();
    this.scene?.traverse((obj) => {
      const o = obj as THREE.Mesh;
      if (o.geometry) o.geometry.dispose();
      const m = o.material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(m)) m.forEach((x) => x.dispose());
      else if (m) m.dispose();
    });
    if (this.renderer) {
      this.renderer.dispose();
      if (this.renderer.domElement.parentElement === this.container) {
        this.container.removeChild(this.renderer.domElement);
      }
    }
  }
}

/* ════════════════════════════════════════════════════════════════════════════
   Composant React
   ════════════════════════════════════════════════════════════════════════════ */

export function DisasterView({ adaptedDiagnostic }: { adaptedDiagnostic: AdapterResult }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<DisasterEngine | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioCode | null>(null);
  const [risk, setRisk] = useState(false);
  const [intensite, setIntensite] = useState(1);
  const [resetKey, setResetKey] = useState(0);

  const scenarioRef = useRef<ScenarioCode | null>(null);
  const intensiteRef = useRef(1);
  intensiteRef.current = intensite;
  const readyRef = useRef(false);

  /* Création du moteur (une fois par diagnostic / réinitialisation). */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    /* Nouveau diagnostic ou reset → catastrophe coupée. */
    scenarioRef.current = null;
    setScenario(null);

    let disposed = false;
    readyRef.current = false;
    const engine = new DisasterEngine(container, adaptedDiagnostic, {
      getIntensity: () => intensiteRef.current,
    });
    engineRef.current = engine;

    try {
      engine.init();
      if (!disposed) {
        readyRef.current = true;
        setReady(true);
      }
      (window as unknown as Record<string, unknown>).__disasterDbg = () => ({
        ready: readyRef.current,
        scenario: scenarioRef.current,
        hasEngine: Boolean(engineRef.current),
        engine: engineRef.current ? engineRef.current.debugState() : null,
      });
    } catch (err) {
      console.error('[disaster] échec d’initialisation de la simulation :', err);
      if (!disposed) setError('Impossible d’initialiser la simulation 3D (WebGL indisponible ?).');
    }

    return () => {
      disposed = true;
      readyRef.current = false;
      engine.dispose();
      engineRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adaptedDiagnostic, resetKey]);

  const launch = (code: ScenarioCode) => {
    const engine = engineRef.current;
    if (!engine || !readyRef.current) return;
    const next = scenarioRef.current === code ? null : code;
    if (scenarioRef.current && scenarioRef.current !== code) engine.stopAllDisasters();
    if (next === null) {
      engine.setDisaster(code, false);
    } else {
      engine.setDisaster(code, true);
    }
    scenarioRef.current = next;
    setScenario(next);
  };

  const toggleRisk = () => {
    const engine = engineRef.current;
    if (!engine || !readyRef.current) return;
    const next = !risk;
    setRisk(next);
    engine.setRiskView(next);
  };

  return (
    <div className="disaster-panel">
      <div className="disaster-toolbar" role="group" aria-label="Simulations de catastrophe">
        <span className="disaster-toolbar-title">
          <md-icon>crisis_alert</md-icon>
          <span>Simulation catastrophe</span>
        </span>
        {SCENARIOS.map((s) => (
          <button
            key={s.code}
            type="button"
            className={`disaster-btn${scenario === s.code ? ' active' : ''}`}
            disabled={scenario !== null && scenario !== s.code}
            title={s.hint}
            aria-pressed={scenario === s.code}
            onClick={() => launch(s.code)}
          >
            <md-icon>{s.icon}</md-icon>
            <span>{s.libelle}</span>
          </button>
        ))}
        <span className="disaster-spacer" />
        <button
          type="button"
          className={`disaster-btn${risk ? ' active' : ''}`}
          title="Colorer les éléments selon le niveau de risque de leur zone (vert = faible → rouge = élevé)"
          aria-pressed={risk}
          onClick={toggleRisk}
        >
          <md-icon>palette</md-icon>
          <span>Vue risque</span>
        </button>
        <span className="disaster-legend" aria-hidden="true">
          {D03.map((b) => (
            <span key={b.key} className="disaster-legend-item">
              <span className="disaster-legend-dot" style={{ background: b.color }} />
              {b.label}
            </span>
          ))}
        </span>
        <label className="disaster-intensity">
          <span>Intensité</span>
          <input
            type="range"
            min={0.3}
            max={1.6}
            step={0.05}
            value={intensite}
            aria-label="Intensité de la catastrophe"
            onChange={(e) => setIntensite(Number(e.target.value))}
          />
          <span className="disaster-intensity-val">{Math.round(intensite * 100)}%</span>
        </label>
        <button
          type="button"
          className="disaster-btn reset"
          title="Reconstruire le bâtiment et arrêter la simulation"
          onClick={() => setResetKey((k) => k + 1)}
        >
          <md-icon>restart_alt</md-icon>
          <span>Réinitialiser</span>
        </button>
      </div>

      <div className="disaster-wrap">
        <div ref={containerRef} className="disaster-canvas" />
        {!ready && !error && (
          <div className="disaster-loading" role="status" aria-live="polite">
            <md-icon>view_in_ar</md-icon>
            <span>Initialisation de la simulation 3D…</span>
            <md-linear-progress indeterminate />
          </div>
        )}
        {error && (
          <div className="disaster-error" role="alert">
            <md-icon>error</md-icon>
            <span>{error}</span>
          </div>
        )}
      </div>

      <p className="disaster-note" role="note">
        <md-icon>info</md-icon>
        <span>
          Bâtiment reconstruit depuis l'emprise réelle (dimensions, matériaux, toiture, cave) et rendu en
          physique cannon-es. Les 6 catastrophes arrachent, emportent, brûlent ou fragilisent les éléments ;
          la « Vue risque » colore chaque élément selon le score de sa zone (vert → rouge).{' '}
          <strong>Simulation visuelle pédagogique — ne remplace pas une étude d'ingénierie.</strong>
        </span>
      </p>
    </div>
  );
}

export default DisasterView;
