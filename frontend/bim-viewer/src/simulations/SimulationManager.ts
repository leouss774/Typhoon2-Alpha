/**
 * DisasterSimulationManager — registre des simulations par aléa.
 *
 * - reçoit le payload du rapport (parent React → iframe, postMessage
 *   `typhoon:sim`) et en dérive les niveaux D03 (aucune donnée inventée) ;
 * - expose l'état (enabled / level / speed) pilotable depuis dat.gui —
 *   les réglages manuels priment ensuite sur le rapport ;
 * - forwarde `update(dt)` à chaque simulation active depuis la boucle de
 *   rendu de Viewer3D.
 */

import * as THREE from "three";
import {
  HazardKind,
  HazardLevel,
  SimPayload,
  SimulationState,
  defaultState
} from "./types";
import { driveFromPayload, buildingInfoFromPayload } from "./drive";
import { FloodSimulation } from "./flood/FloodSimulation";
import { FireSimulation } from "./fire/FireSimulation";
import { SeismicSimulation } from "./seismic/SeismicSimulation";

export class SimulationManager {
  readonly state: SimulationState = defaultState();
  /** Notifie (dat.gui) quand l'état d'une simulation change — permet de
   *  refléter les niveaux auto-dérivés du rapport dans les contrôles. */
  onStateChange?: (kind: HazardKind) => void;
  /** Notifie (Viewer3DContainer) quand au moins une simulation s'active ou se
   *  désactive — sert au bouton flottant « Simulations » (état + auto-ouverture
   *  du panneau). Appelé uniquement sur transition d'activité. */
  onActivityChange?: (active: boolean) => void;
  private lastActive = false;

  private scene?: THREE.Scene;
  private root?: THREE.Object3D;
  private flood = new FloodSimulation();
  private fire = new FireSimulation();
  private seismic = new SeismicSimulation();
  private payload: SimPayload | null = null;
  /** true dès que l'utilisateur touche un réglage (dat.gui) : le rapport ne
   *  doit alors plus écraser ce choix. */
  private manual: Record<HazardKind, boolean> = {
    flood: false,
    fire: false,
    seismic: false
  };

  constructor(scene?: THREE.Scene) {
    this.scene = scene;
  }

  /** Attache la scène (sinon au premier bindModel). */
  setScene(scene: THREE.Scene) {
    this.scene = scene;
  }

  /**
   * Le modèle 3D vient d'être chargé : on enregistre la structure (étages
   * séparés) et on dimensionne les simulations sur la géométrie réelle.
   */
  bindModel(root: THREE.Object3D) {
    this.root = root;
    root.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const halfExtents = {
      x: Math.max(size.x / 2, 0.5),
      z: Math.max(size.z / 2, 0.5)
    };
    const height = Math.max(size.y, 2.5);

    const fromPayload = buildingInfoFromPayload(this.payload);
    const floors = fromPayload.floors || Math.max(1, Math.round(height / 2.7));

    this.flood.create(this.scene!, halfExtents, height);
    this.flood.bindBuilding(root);
    this.fire.setAnchors(halfExtents, height, floors);
    this.fire.bindBuilding(root);
    this.seismic.bindModel(root);

    // Applique le payload s'il est arrivé avant le modèle
    this.applyPayload();
    this.applyAll();
  }

  /** Reçoit le rapport (postMessage parent) et dérive les niveaux. */
  setPayload(payload: SimPayload | null) {
    this.payload = payload;
    if (!this.scene || !this.root) {
      return; // le payload sera appliqué à bindModel()
    }
    this.applyPayload();
  }

  /** Dérive état + niveau du rapport, sauf si l'utilisateur a réglé à la main. */
  private applyPayload() {
    const driven = driveFromPayload(this.payload);
    (Object.keys(driven) as HazardKind[]).forEach(kind => {
      if (this.manual[kind]) {
        return;
      }
      const d = driven[kind];
      // AUTO-ACTIVATION sans donnée inventée : un aléa recensé (`present`)
      // ET quantifié (`niveau` D03) active la simulation à ce niveau. Sans
      // niveau, on n'invente pas d'intensité — la simulation reste
      // disponible via dat.gui (mode manuel).
      if (d.present && d.level !== null) {
        this.state[kind].enabled = true;
        this.state[kind].level = d.level;
      }
    });
    this.applyAll();
  }

  // ── Pilote depuis dat.gui ────────────────────────────────────────────────

  setEnabled(kind: HazardKind, value: boolean) {
    this.manual[kind] = true;
    this.state[kind].enabled = value;
    this.applyAll();
  }

  setLevel(kind: HazardKind, level: HazardLevel) {
    this.manual[kind] = true;
    this.state[kind].level = level;
    this.applyAll();
  }

  setSpeed(kind: HazardKind, speed: number) {
    this.manual[kind] = true;
    this.state[kind].speed = speed;
    this.applyAll();
  }

  /** Réarme les simulations (nouvelle secousse, montée des eaux relancée). */
  reset(kind?: HazardKind) {
    const kinds: HazardKind[] = kind ? [kind] : ["flood", "fire", "seismic"];
    kinds.forEach(k => {
      if (this.state[k].enabled) {
        this.setEnabled(k, false);
        this.setEnabled(k, true);
      }
    });
  }

  private applyAll() {
    const s = this.state;
    this.flood.enabled = s.flood.enabled;
    this.flood.level = s.flood.level;
    this.flood.speed = s.flood.speed;
    this.fire.enabled = s.fire.enabled;
    this.fire.level = s.fire.level;
    this.fire.speed = s.fire.speed;
    this.seismic.enabled = s.seismic.enabled;
    this.seismic.level = s.seismic.level;
    this.seismic.speed = s.seismic.speed;

    if (this.scene) {
      this.flood.apply();
      this.fire.apply(this.scene);
      this.seismic.apply();
    }
    (["flood", "fire", "seismic"] as HazardKind[]).forEach(kind => {
      this.onStateChange && this.onStateChange(kind);
    });
    const active = this.isActive();
    if (active !== this.lastActive) {
      this.lastActive = active;
      this.onActivityChange && this.onActivityChange(active);
    }
  }

  /** Boucle de rendu : appelée à chaque frame depuis Viewer3D.animate(). */
  update(dt: number, elapsed: number) {
    if (!this.scene) {
      return;
    }
    if (this.state.flood.enabled) {
      this.flood.update(dt, elapsed);
    }
    if (this.state.fire.enabled) {
      this.fire.update(dt, elapsed);
    }
    if (this.state.seismic.enabled) {
      this.seismic.update(dt);
    }
  }

  /** Une simulation est-elle active ? (permet de forcer le rendu continu.) */
  isActive(): boolean {
    return this.state.flood.enabled || this.state.fire.enabled || this.state.seismic.enabled;
  }

  dispose() {
    if (this.scene) {
      // Ordre inverse du bind : fire restaure ses dégâts sur les matériaux
      // (éventuellement clonés par la submersion) avant que flood ne
      // remette les matériaux d'origine.
      this.fire.dispose(this.scene);
      this.flood.dispose(this.scene);
      this.seismic.dispose();
    }
    this.root = undefined;
    this.scene = undefined;
    if (this.lastActive) {
      this.lastActive = false;
      this.onActivityChange && this.onActivityChange(false);
    }
  }
}
