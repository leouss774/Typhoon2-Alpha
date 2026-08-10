/**
 * Inondation — plan d'eau animé (GPU) qui monte autour du bâtiment ET
 * interagit avec lui :
 *
 *  - les vagues (multi-octaves) + une liseré d'écume (foam) là où l'eau
 *    touche les murs (distance au rectangle d'emprise, calculée en shader) ;
 *  - la SUBMERSION : les matériaux du bâtiment sont clonés et enrichis d'un
 *    shader (`onBeforeCompile`) — toute partie dont l'altitude est sous le
 *    niveau d'eau passe en teinte « sous l'eau » et devient translucide,
 *    on voit donc le bâtiment s'immerger progressivement (RDC → étages).
 *
 * Hauteurs cibles : `FLOOD_HEIGHTS[niveau]` (aucune donnée inventée).
 */

import * as THREE from "three";
import { FLOOD_HEIGHTS } from "../drive";
import { HazardLevel } from "../types";

const VERTEX_SHADER = `
  uniform float uTime;
  uniform float uHeight;
  uniform float uAmp;
  varying float vWave;
  varying vec3 vWPos;
  void main() {
    vec3 p = position;
    float w1 = sin(p.x * 0.7 + uTime * 1.1);
    float w2 = sin(p.z * 0.5 - uTime * 0.8);
    vWave = w1 * 0.5 + w2 * 0.5;
    float y = uHeight
      + sin(p.x * 0.9 + uTime * 1.6) * uAmp
      + sin(p.z * 1.1 + uTime * 1.3 + 1.7) * uAmp * 0.6
      + sin((p.x + p.z) * 0.55 + uTime * 2.0) * uAmp * 0.35;
    // p est déjà en mètres monde (le maillage est à l'échelle 1)
    vWPos = vec3(p.x, y, p.z);
    gl_Position = projectionMatrix * viewMatrix * vec4(vWPos, 1.0);
  }
`;

const FRAGMENT_SHADER = `
  precision mediump float;
  uniform float uTime;
  uniform vec3 uDeep;
  uniform vec3 uShallow;
  uniform vec3 uFoam;
  uniform float uOpacity;
  uniform vec2 uHalfExt;
  varying float vWave;
  varying vec3 vWPos;
  void main() {
    float t = clamp(vWave * 0.5 + 0.5, 0.0, 1.0);
    vec3 c = mix(uDeep, uShallow, t);

    // Écume : plus le fragment est proche des murs du bâtiment, plus clair.
    float dx = max(abs(vWPos.x) - uHalfExt.x, 0.0);
    float dz = max(abs(vWPos.z) - uHalfExt.y, 0.0);
    float dist = length(vec2(dx, dz));
    float foam = 1.0 - smoothstep(0.0, 1.6, dist);
    float sparkle = 0.5 + 0.5 * sin(vWPos.x * 3.0 + vWPos.z * 2.7 + fract(uTime * 0.9) * 6.2831);
    c = mix(c, uFoam, foam * (0.5 + 0.5 * sparkle));

    float a = uOpacity * (0.6 + 0.4 * t);
    gl_FragColor = vec4(c, a);
  }
`;

/** Injection fragment pour la submersion (murs sous le niveau d'eau).
 *  Commence par le chunk `output_fragment` (r152) qui pose gl_FragColor. */
const SUBMERSION_GLSL = `
#include <output_fragment>
{
  // smoothstep(edge0, edge1, x) exige edge0 < edge1 (sinon indéfini).
  float sub = smoothstep(uTyphoonWaterLevel - 1.0, uTyphoonWaterLevel, vTyphoonWPos.y);
  if (sub > 0.002) {
    vec3 wet = mix(gl_FragColor.rgb, uTyphoonWaterColor, sub * 0.72);
    float alpha = gl_FragColor.a * (1.0 - 0.55 * sub);
    gl_FragColor = vec4(wet, alpha);
  }
}
`;

interface SubmersionWrap {
  mesh: THREE.Mesh;
  original: THREE.Material;
  clone: THREE.Material;
  uniforms: { uTyphoonWaterLevel: { value: number } };
}

let wrapUid = 0;

export class FloodSimulation {
  enabled = false;
  level: HazardLevel = "modere";
  speed = 1;

  private mesh?: THREE.Mesh;
  private material?: THREE.ShaderMaterial;
  private currentHeight = 0;
  private targetHeight = 0;
  private waveAmp = 0.05;
  private size = 60;
  private halfExt = { x: 5, z: 5 };
  private wraps: SubmersionWrap[] = [];

  /** Construit le plan d'eau au-dessus de l'emprise du bâtiment. */
  create(scene: THREE.Scene, halfExtents: { x: number; z: number }, height: number) {
    if (this.mesh) {
      scene.remove(this.mesh);
      this.mesh.geometry.dispose();
      if (this.material) {
        this.material.dispose();
      }
      this.mesh = undefined;
      this.material = undefined;
    }
    this.halfExt = { ...halfExtents };
    const diag = Math.max(Math.hypot(halfExtents.x * 2, halfExtents.z * 2), 6);
    this.size = Math.max(diag * 3.2, 40);
    this.waveAmp = Math.max(Math.min(height * 0.015, 0.12), 0.03);

    // Maillage à l'échelle 1 : les positions sont directement en mètres
    // monde (le bug d'avant multipliait la hauteur par `size` → l'eau
    // flottait à ~36 m au-dessus du bâtiment).
    const geometry = new THREE.PlaneGeometry(this.size, this.size, 96, 96);
    geometry.rotateX(-Math.PI / 2);

    this.material = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        uTime: { value: 0 },
        uHeight: { value: 0 },
        uAmp: { value: this.waveAmp },
        uDeep: { value: new THREE.Color(0x14406b) },
        uShallow: { value: new THREE.Color(0x2e7bb5) },
        uFoam: { value: new THREE.Color(0xdceefa) },
        uOpacity: { value: 0.62 },
        uHalfExt: { value: new THREE.Vector2(this.halfExt.x, this.halfExt.z) }
      }
    });

    this.mesh = new THREE.Mesh(geometry, this.material);
    this.mesh.name = "Simulation · Inondation";
    this.mesh.renderOrder = 2;
    this.mesh.visible = false;
    scene.add(this.mesh);
  }

  /**
   * Enrichit les matériaux du bâtiment avec le shader de submersion.
   * Appelé à chaque bindModel — restaure d'abord l'ancien jeu de clones.
   */
  bindBuilding(root: THREE.Object3D) {
    this.restoreBuilding();
    const wraps: SubmersionWrap[] = [];
    root.traverse(obj => {
      if (!(obj instanceof THREE.Mesh)) {
        return;
      }
      const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
      materials.forEach((mat, i) => {
        if (!(mat instanceof THREE.MeshStandardMaterial)) {
          return;
        }
        const original = mat;
        const clone = original.clone();
        const uniforms = {
          uTyphoonWaterLevel: { value: -10 },
          uTyphoonWaterColor: { value: new THREE.Color(0x0a2f4d) }
        };
        clone.onBeforeCompile = (shader: THREE.Shader) => {
          shader.uniforms = Object.assign(shader.uniforms, uniforms);
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\nuniform float uTyphoonWaterLevel;\nvarying vec3 vTyphoonWPos;"
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\nvTyphoonWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;"
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              "#include <common>\nuniform float uTyphoonWaterLevel;\nuniform vec3 uTyphoonWaterColor;\nvarying vec3 vTyphoonWPos;"
            )
            .replace("#include <output_fragment>", SUBMERSION_GLSL);
        };
        // Programme dédié par clone (les uniforms du closure diffèrent).
        (clone as THREE.MeshStandardMaterial & { _typhoonKey: number })._typhoonKey = ++wrapUid;
        clone.customProgramCacheKey = () => {
          return `typhoon_submersion_${(clone as THREE.MeshStandardMaterial & { _typhoonKey: number })._typhoonKey}`;
        };
        if (Array.isArray(obj.material)) {
          (obj.material as THREE.Material[])[i] = clone;
        } else {
          obj.material = clone;
        }
        wraps.push({ mesh: obj, original, clone, uniforms });
      });
    });
    this.wraps = wraps;
  }

  /** Remet les matériaux d'origine sur le bâtiment. */
  private restoreBuilding() {
    this.wraps.forEach(w => {
      if (w.mesh && w.mesh.material) {
        if (Array.isArray(w.mesh.material)) {
          const idx = w.mesh.material.indexOf(w.clone);
          if (idx !== -1) {
            (w.mesh.material as THREE.Material[])[idx] = w.original;
          }
        } else if (w.mesh.material === w.clone) {
          w.mesh.material = w.original;
        }
      }
      w.clone.dispose();
    });
    this.wraps = [];
  }

  /** Met à jour la cible (hauteur d'eau) selon le niveau. */
  apply() {
    if (!this.mesh) {
      return;
    }
    this.mesh.visible = this.enabled;
    this.targetHeight = this.enabled ? FLOOD_HEIGHTS[this.level] : 0;
  }

  update(dt: number, elapsed: number) {
    if (!this.mesh || !this.material) {
      return;
    }
    const k = 1 - Math.exp(-dt * 0.6 * this.speed);
    this.currentHeight += (this.targetHeight - this.currentHeight) * k;
    const uniforms = this.material.uniforms;
    uniforms.uTime.value = elapsed * this.speed;
    uniforms.uHeight.value = this.currentHeight;
    // Submersion : même niveau que le plan d'eau.
    this.wraps.forEach(w => {
      w.uniforms.uTyphoonWaterLevel.value = this.currentHeight;
    });

    if (!this.enabled && this.currentHeight < 0.005) {
      this.mesh.visible = false;
      // eau retombée → plus aucun effet de submersion nécessaire
      this.wraps.forEach(w => {
        w.uniforms.uTyphoonWaterLevel.value = -10;
      });
    }
  }

  dispose(scene: THREE.Scene) {
    if (this.mesh) {
      scene.remove(this.mesh);
      this.mesh.geometry.dispose();
      if (this.material) {
        this.material.dispose();
      }
      this.mesh = undefined;
      this.material = undefined;
    }
    this.restoreBuilding();
  }
}
