/**
 * Effondrement sismique — moteur physique Rapier (WASM, Apache-2.0).
 *
 * Chaque étage (node glTF "Etage N" produite par le backend) devient un
 * corps rigide ; à l'activation, une impulsion horizontale croissante avec
 * la hauteur + une rotation initient l'effondrement : les étages basculent
 * et s'empilent au sol (niveau `critique` du rapport).
 *
 * Le build `@dimforge/rapier3d-compat` embarque le WASM inline (base64) :
 * aucune requête réseau, donc compatible file:// et CSP. L'import est
 * DYNAMIQUE : le chunk (~2 Mo) n'est chargé que quand un effondrement est
 * déclenché — le chargement initial du viewer reste léger. En cas d'échec
 * d'initialisation, `SeismicSimulation` retombe sur le cisaillement par
 * matrices (fail-soft).
 */

import * as THREE from "three";

type RapierModule = typeof import("@dimforge/rapier3d-compat");
let RAPIER: RapierModule | null = null;

interface FloorBody {
  node: THREE.Object3D;
  body: any;
  start: { position: THREE.Vector3; quaternion: THREE.Quaternion; scale: THREE.Vector3 };
}

interface SavedTransform {
  obj: THREE.Object3D;
  parent: THREE.Object3D | null;
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  scale: THREE.Vector3;
}

export class RapierCollapse {
  ready = false;
  running = false;

  private world: any = null;
  private bodies: FloorBody[] = [];
  private extras: SavedTransform[] = [];
  private root?: THREE.Object3D;

  /** Initialise Rapier (wasm inline) — ne jette jamais. */
  async init(): Promise<boolean> {
    try {
      if (!RAPIER) {
        const mod = await import("@dimforge/rapier3d-compat");
        RAPIER = mod;
      }
      await RAPIER.init();
      this.ready = true;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("[Sim] Rapier indisponible, effondrement physique désactivé :", e);
      this.ready = false;
    }
    return this.ready;
  }

  /**
   * Démarre l'effondrement : corps rigides par étage + sol fixe. Les
   * parties non-porteuses (toiture, cadres, vitrage, porte) sont rattachées
   * à l'étage supérieur pour s'effondrer avec lui ; les planchers restent
   * en place (image d'étages qui survivent aux murs).
   */
  start(
    root: THREE.Object3D,
    floors: THREE.Object3D[],
    extras: THREE.Object3D[]
  ) {
    if (!this.ready || !RAPIER || this.running || floors.length < 2) {
      return;
    }
    const R = RAPIER;
    this.root = root;
    this.world = new R.World({ x: 0, y: -9.81, z: 0 });
    this.bodies = [];
    this.extras = [];

    // Sol fixe
    const groundBody = this.world.createRigidBody(
      R.RigidBodyDesc.fixed().setTranslation(0, -0.5, 0)
    );
    this.world.createCollider(
      R.ColliderDesc.cuboid(200, 0.5, 200).setFriction(0.8),
      groundBody
    );

    const n = floors.length;
    const impulse = 6 + Math.random() * 3;
    const angleDir = Math.random() > 0.5 ? 1 : -1;

    floors.forEach((node, i) => {
      const save = this.save(node);
      const box = new THREE.Box3().setFromObject(node);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());

      // Corps dynamique positionné au centre de l'étage
      const bodyDesc = R.RigidBodyDesc.dynamic()
        .setTranslation(center.x, center.y, center.z)
        .setLinearDamping(0.4)
        .setAngularDamping(0.6);
      const body = this.world.createRigidBody(bodyDesc);
      this.world.createCollider(
        R.ColliderDesc
          .cuboid(
            Math.max(size.x / 2 - 0.02, 0.1),
            Math.max(size.y / 2 - 0.02, 0.1),
            Math.max(size.z / 2 - 0.02, 0.1)
          )
          .setFriction(0.7)
          .setRestitution(0.05)
          .setDensity(180),
        body
      );

      // Impulsion : plus forte en haut, direction aléatoire + rotation
      const frac = i / Math.max(n - 1, 1);
      body.setLinvel(
        { x: (Math.random() - 0.5) * impulse * (0.4 + frac), y: 0, z: (Math.random() - 0.5) * impulse * (0.4 + frac) },
        true
      );
      if (i === n - 1) {
        body.setAngvel({ x: angleDir * (0.5 + frac), y: 0, z: angleDir * (1.2 + frac) }, true);
      }

      this.bodies.push({ node, body, start: { position: save.position, quaternion: save.quaternion, scale: save.scale } });
    });

    // Rattachement des parties non-porteuses à l'étage supérieur
    const topFloor = floors[n - 1];
    extras.forEach(obj => {
      const saved = this.save(obj);
      this.extras.push(saved);
      obj.parent && obj.parent.remove(obj);
      topFloor.add(obj);
    });

    this.running = true;
  }

  private save(obj: THREE.Object3D): SavedTransform {
    return {
      obj,
      parent: obj.parent,
      position: obj.position.clone(),
      quaternion: obj.quaternion.clone(),
      scale: obj.scale.clone()
    };
  }

  /** Avance le monde physique et synchronise les transformations. */
  step(dt: number) {
    if (!this.running || !this.world) {
      return;
    }
    const timestep = Math.min(Math.max(dt, 1 / 120), 1 / 30);
    this.world.timestep = timestep;
    this.world.step();

    for (const fb of this.bodies) {
      const t = fb.body.translation();
      const q = fb.body.rotation();
      fb.node.position.set(t.x, t.y, t.z);
      fb.node.quaternion.set(q.x, q.y, q.z, q.w);
      fb.node.updateMatrix();
    }
    if (this.root) {
      this.root.updateMatrixWorld(true);
    }
  }

  /** Restaure la position d'origine et libère le monde physique. */
  stop() {
    if (!this.running) {
      return;
    }
    this.running = false;

    // Restaure les parties rattachées
    for (const saved of this.extras) {
      if (saved.obj.parent) {
        saved.obj.parent.remove(saved.obj);
      }
      if (saved.parent) {
        saved.parent.add(saved.obj);
      }
      saved.obj.position.copy(saved.position);
      saved.obj.quaternion.copy(saved.quaternion);
      saved.obj.scale.copy(saved.scale);
      saved.obj.updateMatrix();
    }
    this.extras = [];

    // Restaure les étages
    for (const fb of this.bodies) {
      fb.node.position.copy(fb.start.position);
      fb.node.quaternion.copy(fb.start.quaternion);
      fb.node.scale.copy(fb.start.scale);
      fb.node.updateMatrix();
    }
    this.bodies = [];

    if (this.world) {
      this.world.free();
      this.world = null;
    }
    if (this.root) {
      this.root.updateMatrixWorld(true);
    }
  }
}
