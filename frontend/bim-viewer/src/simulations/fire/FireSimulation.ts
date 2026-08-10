/**
 * Feu — incendie qui INTERAGIT avec le bâtiment, pas seulement des particules :
 *
 *  - PROPAGATION par étage : le feu démarre au RDC et monte niveau par niveau
 *    (vitesse dérivée de `level`) — les foyers de flammes sont allumés en
 *    conséquence (drawRange piloté par le nombre d'étages enflammés) ;
 *  - DÉGÂTS : les murs de chaque étage carbonisent (couleur → charbon,
 *    rugosité), le vitrage s'embrase (émission orange) puis « casse »
 *    (opacité → 0), la toiture s'enflamme aux niveaux élevés ;
 *  - FUMÉE : panache de particules montant au-dessus du toit.
 *
 * Les matériaux sont mutés puis restaurés à la désactivation/dispose
 * (snapshot des valeurs de base au bind).
 */

import * as THREE from "three";
import { FIRE_HEIGHTS, levelIntensity } from "../drive";
import { HazardLevel } from "../types";

// ── Flammes (GPU, points) ────────────────────────────────────────────────
const FLAME_VERTEX = `
  uniform float uTime;
  uniform float uIntensity;
  uniform float uFlameHeight;
  attribute vec3 aBase;
  attribute vec3 aOffset;
  attribute float aSize;
  varying float vLife;
  varying float vSeed;
  void main() {
    float seed = aOffset.x * 7.31 + aOffset.y * 13.7 + aOffset.z * 3.17;
    float speed = 0.5 + aOffset.y * 0.35;
    float life = fract(uTime * speed + seed);
    vLife = life;
    vSeed = seed;

    vec3 p = aBase;
    p.x += aOffset.x * (1.1 + uIntensity * 2.0);
    p.z += aOffset.z * (1.1 + uIntensity * 2.0);
    p.y += life * uFlameHeight * (0.55 + uIntensity * 0.85);
    p.x += sin(uTime * 2.4 + seed * 43.0) * 0.10 * (0.5 + uIntensity);
    p.z += cos(uTime * 2.1 + seed * 37.0) * 0.10 * (0.5 + uIntensity);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float s = aSize * (1.0 - life * 0.82) * (0.7 + uIntensity * 0.7);
    gl_PointSize = max(s * (260.0 / max(-mv.z, 0.1)), 1.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const FLAME_FRAGMENT = `
  precision mediump float;
  varying float vLife;
  varying float vSeed;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    // NOTE: smoothstep(edge0, edge1, x) exige edge0 < edge1 (sinon
    // comportement indéfini selon la spec GLSL — certains pilotes
    // discardent alors tous les fragments).
    float alpha = 1.0 - smoothstep(0.04, 0.5, d);
    if (alpha < 0.02) discard;

    float t = clamp(vLife, 0.0, 1.0);
    vec3 core = vec3(1.0, 0.92, 0.55);
    vec3 mid = vec3(1.0, 0.45, 0.08);
    vec3 dark = vec3(0.45, 0.08, 0.02);
    vec3 c = mix(core, mid, smoothstep(0.0, 0.45, t));
    c = mix(c, dark, smoothstep(0.45, 0.92, t));

    float flick = 0.82 + 0.18 * sin(gl_FragCoord.x * 0.23 + vSeed * 100.0 + fract(vLife * 40.0) * 6.2831);
    float fade = 1.0 - smoothstep(0.72, 1.0, t);
    gl_FragColor = vec4(c * flick, alpha * fade);
  }
`;

// ── Fumée (GPU, points) ──────────────────────────────────────────────────
const SMOKE_VERTEX = `
  uniform float uTime;
  uniform float uSmokeHeight;
  attribute vec3 aBase;
  attribute float aSize;
  attribute float aSpeed;
  attribute float aSeed;
  varying float vAlpha;
  void main() {
    float life = fract(uTime * aSpeed + aSeed);
    vec3 p = aBase;
    p.y += life * uSmokeHeight * (1.1 + aSeed);
    p.x += sin(uTime * 0.5 + aSeed * 40.0) * (1.5 + aSeed * 2.5) * life;
    p.z += cos(uTime * 0.4 + aSeed * 27.0) * (1.5 + aSeed * 2.5) * life;
    p.x *= 1.0 + life * 1.1;
    p.z *= 1.0 + life * 1.1;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float s = aSize * (1.0 + life * 3.2);
    gl_PointSize = max(s * (300.0 / max(-mv.z, 0.1)), 1.0);
    vAlpha = sin(life * 3.14159);
    gl_Position = projectionMatrix * mv;
  }
`;

const SMOKE_FRAGMENT = `
  precision mediump float;
  uniform sampler2D uTex;
  varying float vAlpha;
  void main() {
    vec4 t = texture2D(uTex, gl_PointCoord);
    gl_FragColor = vec4(0.58, 0.56, 0.53, t.a * vAlpha * 0.62);
  }
`;

/** Proportion maximale de la hauteur du bâtiment atteinte par le feu,
 *  par niveau — garde une différence visible entre les intensités
 *  (tres_faible : RDC seul ; critique : embrasement complet + toiture). */
const MAX_BURN_FRACTION: Record<HazardLevel, number> = {
  tres_faible: 0.28,
  faible: 0.5,
  modere: 0.7,
  eleve: 0.88,
  critique: 1.0
};

const CHARCOAL = new THREE.Color(0x0b0807);

interface MaterialSnapshot {
  material: THREE.MeshStandardMaterial;
  color: THREE.Color;
  roughness: number;
  emissive: THREE.Color;
  emissiveIntensity: number;
  opacity: number;
  transparent: boolean;
}

interface FloorBurn {
  node: THREE.Object3D;
  mats: MaterialSnapshot[];
  /** instant (secondes) où cet étage a commencé à brûler */
  ignitionAt: number;
  damage: number;
}

export class FireSimulation {
  enabled = false;
  level: HazardLevel = "modere";
  speed = 1;

  private points?: THREE.Points;
  private material?: THREE.ShaderMaterial;
  private geometry?: THREE.BufferGeometry;
  private anchors: Array<{ x: number; y: number; z: number; floor: number }> = [];
  private maxParticles = 1024;
  private buildingHeight = 6;
  private floors: FloorBurn[] = [];
  private windowMats: MaterialSnapshot[] = [];
  private roofMats: MaterialSnapshot[] = [];
  private smoke?: THREE.Points;
  private smokeMaterial?: THREE.ShaderMaterial;
  private smokeGeometry?: THREE.BufferGeometry;
  private elapsed = 0;
  private prevEnabled = false;
  private totalFloors = 1;
  private levelHeight = 3;

  // ── Construction ───────────────────────────────────────────────────────

  /** Enregistre les ancres de feu (façades + toiture), par étage. */
  setAnchors(
    halfExtents: { x: number; z: number },
    height: number,
    floors = 1
  ) {
    this.buildingHeight = Math.max(height, 2.5);
    this.totalFloors = Math.max(1, floors);
    this.levelHeight = this.buildingHeight / this.totalFloors;
    const { x, z } = halfExtents;
    const anchors: Array<{ x: number; y: number; z: number; floor: number }> = [];

    // Façades : une ancre par ~2 m de mur, répartie sur tous les étages
    const perimeter: Array<[number, number]> = [
      [-x, -z], [x, -z], [x, z], [-x, z]
    ];
    const step = 2.2;
    for (let i = 0; i < perimeter.length; i++) {
      const [ax, az] = perimeter[i];
      const [bx, bz] = perimeter[(i + 1) % perimeter.length];
      const len = Math.hypot(bx - ax, bz - az);
      const n = Math.max(1, Math.floor(len / step));
      for (let k = 0; k <= n; k++) {
        const t = k / n;
        const hy = 0.25 + Math.random() * this.buildingHeight * 0.8;
        anchors.push({
          x: ax + (bx - ax) * t,
          y: hy,
          z: az + (bz - az) * t,
          floor: Math.min(this.totalFloors - 1, Math.floor(hy / this.levelHeight))
        });
      }
    }

    // Toiture : ligne de faîtage (flambe aux niveaux élevés — floor = dernier)
    const ridgeY = this.buildingHeight * 0.92;
    const ridgeLen = Math.max(x, z) * 2;
    const horizontal = x >= z;
    for (let k = 0; k < 10; k++) {
      const t = (k + Math.random() * 0.8) / 10;
      const along = (t - 0.5) * ridgeLen;
      anchors.push(
        horizontal
          ? { x: along, y: ridgeY, z: 0, floor: this.totalFloors - 1 }
          : { x: 0, y: ridgeY, z: along, floor: this.totalFloors - 1 }
      );
    }

    // Trie par étage : la propagation est un simple préfixe du drawRange.
    anchors.sort((a, b) => a.floor - b.floor);
    this.anchors = anchors;
    this.rebuild();
    this.buildSmoke();
  }

  /**
   * Enregistre la structure du bâtiment pour les dégâts : étages (murs),
   * vitrage et toiture. Restaure d'abord un éventuel état précédent.
   */
  bindBuilding(root: THREE.Object3D) {
    this.restoreBuilding();
    this.floors = [];
    this.windowMats = [];
    this.roofMats = [];

    const snapshotMats = (obj: THREE.Object3D): MaterialSnapshot[] => {
      const out: MaterialSnapshot[] = [];
      obj.traverse(mesh => {
        if (!(mesh instanceof THREE.Mesh)) {
          return;
        }
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        mats.forEach(m => {
          if (m instanceof THREE.MeshStandardMaterial) {
            out.push({
              material: m,
              color: m.color.clone(),
              roughness: m.roughness,
              emissive: m.emissive.clone(),
              emissiveIntensity: m.emissiveIntensity,
              opacity: m.opacity,
              transparent: m.transparent
            });
          }
        });
      });
      return out;
    };

    // Étages : nodes « Etage N » (le loader remplace l'espace par '_')
    const floorNodes: Array<{ node: THREE.Object3D; index: number }> = [];
    root.traverse(obj => {
      const m = /^etage[_ ](\d+)$/i.exec(obj.name || "");
      if (m) {
        floorNodes.push({ node: obj, index: parseInt(m[1], 10) });
      }
    });
    floorNodes.sort((a, b) => a.index - b.index);

    if (floorNodes.length > 0) {
      floorNodes.forEach(f => {
        this.floors.push({
          node: f.node,
          mats: snapshotMats(f.node),
          ignitionAt: -1,
          damage: 0
        });
      });
    } else {
      // Repli : bâtiment monobloc → un seul « étage » (tout carbonise)
      this.floors.push({ node: root, mats: snapshotMats(root), ignitionAt: -1, damage: 0 });
    }

    // Vitrage (fenêtres) : nodes « Vitrage » ou mailles transparentes nommées
    root.traverse(obj => {
      if (/vitrage|fenetre|glass/i.test(obj.name || "")) {
        this.windowMats.push(...snapshotMats(obj));
      }
    });
    // Toiture
    root.traverse(obj => {
      if (/^toiture$/i.test(obj.name || "")) {
        this.roofMats.push(...snapshotMats(obj));
      }
    });
  }

  /** Construit (ou reconstruit) le système de particules de flammes. */
  private rebuild() {
    if (!this.geometry) {
      this.geometry = new THREE.BufferGeometry();
      this.material = new THREE.ShaderMaterial({
        vertexShader: FLAME_VERTEX,
        fragmentShader: FLAME_FRAGMENT,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        uniforms: {
          uTime: { value: 0 },
          uIntensity: { value: 0.6 },
          uFlameHeight: { value: 3.2 }
        }
      });
    }

    const count = Math.min(this.anchors.length || 1, this.maxParticles);
    const base = new Float32Array(count * 3);
    const offset = new Float32Array(count * 3);
    const size = new Float32Array(count);

    for (let i = 0; i < count; i++) {
      const a = this.anchors[i % this.anchors.length];
      base[i * 3] = a.x;
      base[i * 3 + 1] = a.y;
      base[i * 3 + 2] = a.z;
      offset[i * 3] = (Math.random() - 0.5) * 2;
      offset[i * 3 + 1] = Math.random();
      offset[i * 3 + 2] = (Math.random() - 0.5) * 2;
      size[i] = 0.7 + Math.random() * 1.3;
    }

    this.geometry.setAttribute("aBase", new THREE.BufferAttribute(base, 3));
    this.geometry.setAttribute("aOffset", new THREE.BufferAttribute(offset, 3));
    this.geometry.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    // `position` est requis par le chemin de rendu de three.js pour
    // dimensionner le draw call des Points (sans lui : 0 sommets dessinés).
    this.geometry.setAttribute("position", new THREE.BufferAttribute(base, 3));
  }

  /** Panache de fumée au-dessus du toit. */
  private buildSmoke() {
    if (!this.smokeGeometry) {
      this.smokeGeometry = new THREE.BufferGeometry();
      const tex = makeSmokeTexture();
      this.smokeMaterial = new THREE.ShaderMaterial({
        vertexShader: SMOKE_VERTEX,
        fragmentShader: SMOKE_FRAGMENT,
        transparent: true,
        depthWrite: false,
        uniforms: {
          uTime: { value: 0 },
          uSmokeHeight: { value: 6 },
          uTex: { value: tex }
        }
      });
    }
    const count = 140;
    const base = new Float32Array(count * 3);
    const size = new Float32Array(count);
    const speed = new Float32Array(count);
    const seed = new Float32Array(count);
    const roofY = this.buildingHeight * 0.94;
    for (let i = 0; i < count; i++) {
      base[i * 3] = (Math.random() - 0.5) * this.buildingHeight * 0.5;
      base[i * 3 + 1] = roofY + Math.random() * 0.5;
      base[i * 3 + 2] = (Math.random() - 0.5) * this.buildingHeight * 0.5;
      size[i] = 0.8 + Math.random() * 1.4;
      speed[i] = 0.08 + Math.random() * 0.12;
      seed[i] = Math.random();
    }
    this.smokeGeometry.setAttribute("aBase", new THREE.BufferAttribute(base, 3));
    this.smokeGeometry.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    this.smokeGeometry.setAttribute("aSpeed", new THREE.BufferAttribute(speed, 1));
    this.smokeGeometry.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
    this.smokeGeometry.setAttribute("position", new THREE.BufferAttribute(base, 3));
    if (this.smokeMaterial) {
      this.smokeMaterial.uniforms.uSmokeHeight.value = this.buildingHeight * 1.4;
    }
  }

  // ── Pilotage ───────────────────────────────────────────────────────────

  /** Applique l'état (niveau → intensité, propagation, dégâts). */
  apply(scene: THREE.Scene) {
    if (!this.geometry || !this.material || !this.anchors.length) {
      return;
    }
    if (!this.points) {
      this.points = new THREE.Points(this.geometry, this.material);
      this.points.name = "Simulation · Feu";
      this.points.frustumCulled = false;
      scene.add(this.points);
    }
    if (!this.smoke) {
      this.smoke = new THREE.Points(this.smokeGeometry!, this.smokeMaterial!);
      this.smoke.name = "Simulation · Fumée";
      this.smoke.frustumCulled = false;
      scene.add(this.smoke);
    }
    this.points.visible = this.enabled;
    this.smoke.visible = this.enabled;

    // Nouvelle mise en route → la propagation repart du RDC
    if (this.enabled && !this.prevEnabled) {
      this.elapsed = 0;
    }
    this.prevEnabled = this.enabled;
    if (!this.enabled) {
      this.resetDamage();
      return;
    }

    this.material.uniforms.uIntensity.value = levelIntensity(this.level);
    this.material.uniforms.uFlameHeight.value = FIRE_HEIGHTS[this.level];
  }

  update(dt: number, elapsed: number) {
    if (!this.material) {
      return;
    }
    this.material.uniforms.uTime.value = elapsed * this.speed;
    if (this.smokeMaterial) {
      this.smokeMaterial.uniforms.uTime.value = elapsed * this.speed;
    }
    if (!this.enabled) {
      return;
    }
    this.elapsed += dt * this.speed;

    // Propagation : un étage tous les `interval` secondes (plus rapide si élevé),
    // plafonné par le niveau (tres_faible ne dépasse pas le RDC).
    const interval = 9 - 6.5 * levelIntensity(this.level); // 8.7s (tres_faible) → 2.5s (critique)
    const maxFloors = Math.max(1, Math.ceil(this.totalFloors * MAX_BURN_FRACTION[this.level]));
    const ignitedFloors = Math.min(maxFloors, Math.max(1, Math.floor(this.elapsed / interval) + 1));

    // Allume les flammes des étages enflammés (préfixe — les ancres sont triées)
    const visibleCount = this.anchors.reduce((acc, a) => (a.floor < ignitedFloors ? acc + 1 : acc), 0);
    if (this.geometry) {
      this.geometry.setDrawRange(0, visibleCount);
    }

    // Dégâts : carbonisation des murs par étage
    this.updateDamage(elapsed, ignitedFloors);
  }

  private updateDamage(elapsed: number, ignitedFloors: number) {
    const burnIn = 2.2; // secondes entre l'ignition et le début de carbonisation
    const burnDur = 7.0; // durée de carbonisation complète

    this.floors.forEach((f, i) => {
      if (f.ignitionAt < 0 && i < ignitedFloors) {
        f.ignitionAt = elapsed;
      }
      if (f.ignitionAt < 0) {
        return;
      }
      const t = (elapsed - f.ignitionAt - burnIn) / burnDur;
      const dmg = THREE.MathUtils.clamp(t, 0, 1);
      if (dmg === f.damage) {
        return;
      }
      f.damage = dmg;
      f.mats.forEach(s => {
        s.material.color.copy(s.color).lerp(CHARCOAL, dmg * 0.92);
        s.material.roughness = THREE.MathUtils.lerp(s.roughness, 0.95, dmg);
      });
    });

    // Vitrage : s'embrase puis « casse » (opacité → 0)
    const burn = ignitedFloors / Math.max(1, this.totalFloors);
    this.windowMats.forEach(s => {
      const glow = THREE.MathUtils.clamp(burn * 1.4, 0, 1);
      s.material.emissive.copy(new THREE.Color(1, 0.35, 0.05));
      s.material.emissiveIntensity = s.emissiveIntensity + glow * 3.0;
      if (burn > 0.45) {
        s.material.transparent = true;
        s.material.opacity = s.opacity * (1 - Math.min(1, (burn - 0.45) / 0.5));
      }
    });

    // Toiture : s'enflamme aux niveaux élevés
    if (this.roofMats.length > 0 && burn > 0.55) {
      const roofDmg = THREE.MathUtils.clamp((burn - 0.55) / 0.45, 0, 1);
      this.roofMats.forEach(s => {
        s.material.color.copy(s.color).lerp(CHARCOAL, roofDmg * 0.85);
      });
    }
  }

  /** Remet les matériaux du bâtiment dans leur état d'origine. */
  private resetDamage() {
    this.floors.forEach(f => {
      f.mats.forEach(s => {
        s.material.color.copy(s.color);
        s.material.roughness = s.roughness;
      });
      f.damage = 0;
      f.ignitionAt = -1;
    });
    this.windowMats.forEach(s => {
      s.material.emissive.copy(s.emissive);
      s.material.emissiveIntensity = s.emissiveIntensity;
      s.material.opacity = s.opacity;
      s.material.transparent = s.transparent;
    });
    this.roofMats.forEach(s => {
      s.material.color.copy(s.color);
    });
  }

  private restoreBuilding() {
    this.resetDamage();
    this.floors = [];
    this.windowMats = [];
    this.roofMats = [];
  }

  dispose(scene: THREE.Scene) {
    if (this.points) {
      scene.remove(this.points);
      this.points = undefined;
    }
    if (this.smoke) {
      scene.remove(this.smoke);
      this.smoke = undefined;
    }
    if (this.geometry) {
      this.geometry.dispose();
      this.geometry = undefined;
    }
    if (this.smokeGeometry) {
      this.smokeGeometry.dispose();
      this.smokeGeometry = undefined;
    }
    if (this.material) {
      this.material.dispose();
      this.material = undefined;
    }
    if (this.smokeMaterial) {
      this.smokeMaterial.uniforms.uTex.value.dispose();
      this.smokeMaterial.dispose();
      this.smokeMaterial = undefined;
    }
    this.anchors = [];
    this.restoreBuilding();
  }
}

function makeSmokeTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 2, 32, 32, 30);
  g.addColorStop(0, "rgba(255,255,255,0.95)");
  g.addColorStop(0.6, "rgba(255,255,255,0.4)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}
