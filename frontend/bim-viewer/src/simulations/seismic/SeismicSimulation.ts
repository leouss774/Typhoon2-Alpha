/**
 * Séisme — trois comportements pilotés par le niveau D03 du rapport :
 *
 *  - tous niveaux : secousse amortie du sol (enveloppe sinusoïdale calibrée
 *    sur `niveau`) + cisaillement progressif des étages (décalage horizontal
 *    croissant avec la hauteur — approche « matrices », zéro dépendance) ;
 *  - `critique` : effondrement en corps rigides Rapier (les étages produits
 *    par le backend basculent et s'empilent) quand le moteur est disponible,
 *    sinon repli sur un cisaillement violent (fail-soft).
 */

import * as THREE from "three";
import { SEISMIC_SWAY, seismicDuration } from "../drive";
import { HazardLevel } from "../types";
import { RapierCollapse } from "./RapierCollapse";

interface FloorRef {
  node: THREE.Object3D;
  index: number;
}

interface SavedTransform {
  obj: THREE.Object3D;
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  scale: THREE.Vector3;
}

export class SeismicSimulation {
  enabled = false;
  level: HazardLevel = "modere";
  speed = 1;

  private root?: THREE.Object3D;
  private floors: FloorRef[] = [];
  private extras: THREE.Object3D[] = [];
  private saved: SavedTransform[] = [];
  private collapse = new RapierCollapse();
  private running = false;
  private elapsedSinceStart = 0;
  private duration = 10;
  private collapsed = false;
  private pendingCollapse = false;

  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-floating-promises
    this.collapse.init();
  }

  /** Enregistre la structure : étages séparés (backend) + parties annexes. */
  bindModel(root: THREE.Object3D) {
    this.root = root;
    this.floors = [];
    this.extras = [];
    this.saved = [];

    // Seules les parties NON-porteuses suivent l'étage supérieur pendant
    // l'effondrement (Rapier). Les planchers restent en place : ils figurent
    // les dalles qui survivent à l'écroulement des murs.
    const nonPorteur = new Set(["Toiture", "Cadres", "Vitrage", "Porte"]);

    root.traverse((obj: THREE.Object3D) => {
      // Le loader glTF normalise certains noms de noeuds ("Etage 1" peut
      // devenir "Etage_1") : on accepte espace ET underscore.
      const m = /^Etage[ _](\d+)$/.exec(obj.name || "");
      if (m) {
        this.floors.push({ node: obj, index: parseInt(m[1], 10) - 1 });
      } else if (nonPorteur.has(obj.name)) {
        this.extras.push(obj);
      }
    });

    // Tri par étage + sauvegarde des transformations d'origine (reset)
    this.floors.sort((a, b) => a.index - b.index);
    const all = [root, ...this.floors.map(f => f.node), ...this.extras];
    all.forEach(obj => {
      this.saved.push({
        obj,
        position: obj.position.clone(),
        quaternion: obj.quaternion.clone(),
        scale: obj.scale.clone()
      });
    });
  }

  apply() {
    this.duration = seismicDuration(this.level);
    if (!this.enabled) {
      // Désactivation : on libère le moteur physique et on remet en place.
      this.collapse.stop();
      this.pendingCollapse = false;
      this.stopEffects();
      return;
    }
    // Montée en intensité vers `critique` pendant qu'un cisaillement tourne
    // déjà : on relance la séquence pour tenter l'effondrement (Rapier).
    if (this.running && this.level === "critique" && !this.collapsed && this.collapse.ready) {
      this.stopEffects();
    }
    if (this.running || this.collapsed || !this.root) {
      return;
    }
    this.running = true;
    this.elapsedSinceStart = 0;
    this.collapsed = false;
    this.pendingCollapse = this.level === "critique" && !this.collapse.ready;
    this.tryStartCollapse();
  }

  /** Démarre l'effondrement Rapier si le moteur est prêt (retry sinon). */
  private tryStartCollapse() {
    if (this.level !== "critique" || !this.root || !this.enabled) {
      return;
    }
    this.collapse.start(this.root, this.floors.map(f => f.node), this.extras);
    if (this.collapse.running) {
      this.collapsed = true;
      this.running = false; // le moteur physique pilote désormais
      this.pendingCollapse = false;
    }
  }

  update(dt: number) {
    if (this.collapsed && this.collapse.running) {
      this.collapse.step(dt);
      return;
    }
    // Rapier pas encore chargé au moment de l'activation : on retente dès
    // que le module WASM est prêt (le cisaillement joue en attendant).
    if (this.pendingCollapse && this.collapse.ready && !this.collapsed) {
      this.tryStartCollapse();
      if (this.collapsed) {
        return;
      }
    }
    if (!this.running || !this.root || !this.enabled) {
      return;
    }

    this.elapsedSinceStart += dt * this.speed;
    const t = this.elapsedSinceStart;

    // Enveloppe : monte 0→1 en ~1 s, oscille, redescend en fin de durée.
    const dur = this.duration;
    const envIn = Math.min(t / Math.max(0.9, dur * 0.12), 1);
    const envOut = Math.max(1 - (t - dur * 0.72) / Math.max(0.1, dur * 0.28), 0);
    const env = envIn * envOut * (0.62 + 0.38 * Math.sin(t * 5.5 * this.speed));

    const amp = SEISMIC_SWAY[this.level];
    const n = this.floors.length;

    // Cisaillement par étage : décalage horizontal croissant avec la hauteur
    for (const f of this.floors) {
      const frac = n > 1 ? f.index / (n - 1) : 0;
      const phase = f.index * 0.9;
      const offsetX = env * amp * frac * Math.sin(t * 6.2 * this.speed + phase);
      const offsetZ = env * amp * frac * 0.8 * Math.cos(t * 5.4 * this.speed + phase);
      f.node.position.x = offsetX;
      f.node.position.z = offsetZ;
      f.node.rotation.z = env * amp * 0.12 * frac * Math.sin(t * 3.3 * this.speed + phase);
      f.node.updateMatrix();
    }

    // Secousse du sol (bruit pseudo-aléatoire via sin à hautes fréquences)
    if (this.root) {
      const shake = env * amp * 0.35;
      this.root.position.x = shake * Math.sin(t * 31.7);
      this.root.position.z = shake * Math.sin(t * 27.3 + 1.3);
      this.root.rotation.z = shake * 0.5 * Math.sin(t * 22.1 + 0.7);
      this.root.updateMatrix();
      this.root.updateMatrixWorld(true);
    }

    if (t >= dur) {
      this.stopEffects();
    }
  }

  private stopEffects() {
    this.running = false;
    this.collapsed = false;
    this.pendingCollapse = false;
    for (const s of this.saved) {
      s.obj.position.copy(s.position);
      s.obj.quaternion.copy(s.quaternion);
      s.obj.scale.copy(s.scale);
      s.obj.updateMatrix();
    }
    if (this.root) {
      this.root.updateMatrixWorld(true);
    }
  }

  dispose() {
    this.collapse.stop();
    this.stopEffects();
    this.floors = [];
    this.extras = [];
    this.saved = [];
    this.root = undefined;
  }
}
