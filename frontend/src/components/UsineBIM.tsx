// =============================================================================
//   TYPHOON — /usine : étape 4 « Jumeau BIM » — jumeau 3D réaliste coloré
//   Moteur avancé three.js (WebGL) façon visualiseur BIM :
//     · enveloppe industrielle réaliste : façades béton texturées (panneaux,
//       joints, menuiseries vitrées), acrotère, porte de chargement, dalle
//     · toiture plate avec acrotère + équipements de toiture (CVC)
//     · COLORATION PAR RISQUE D03 : acrotère, arêtes, emprise au sol et cadre
//       de toiture teintés du niveau de risque — matériaux réels conservés
//     · équipements 3D par type (machines, cuves, silos…) colorés par risque
//     · clic → fiche de zone, ombres portées, orbite/zoom
//     · vue plan 2D (SVG) en repli/alternatif
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { UsineJumeau } from './UsineJumeau';
import {
  bandForScore,
  bandForKey,
  normalizeNiveau,
  TYPE_EQUIP_LABELS,
  TYPE_ZONE_LABELS,
  type Equipement,
  type ZonePlan,
} from '../usine/types';

type Props = {
  zones: ZonePlan[];
  equipements: Equipement[];
  nomUsine?: string;
  scoreGlobal?: number | null;
};

const ZONE_HEIGHTS: Record<string, number> = {
  production: 8,
  stockage: 10,
  bureaux: 5,
  cuves: 6,
  expedition: 7,
  laboratoire: 5,
  maintenance: 6,
};

/* Palette "matériaux" (réalisme, indépendante du risque) */
const MAT = {
  steel: 0x3b4a5a,
  steelDark: 0x2a3542,
  glass: 0x9db8cf,
};

/* ── Aide hex → THREE.Color sans garder d'instance (réutilisée par zone) ── */
function parseHex(hex: string): { r: number; g: number; b: number } {
  const clean = hex.replace('#', '');
  const n = parseInt(clean, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

/* ── Mélange la couleur de risque vers le blanc (teinte claire d'enveloppe) ── */
function tintColor(hex: string, towardWhite: number): THREE.Color {
  const { r, g, b } = parseHex(hex);
  return new THREE.Color().setRGB(
    (r + (255 - r) * towardWhite) / 255,
    (g + (255 - g) * towardWhite) / 255,
    (b + (255 - b) * towardWhite) / 255
  );
}

export function UsineBIM({ zones, equipements, nomUsine, scoreGlobal }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState<'3d' | '2d'>('3d');
  const [webglFailed, setWebglFailed] = useState(false);
  const [selected, setSelected] = useState<ZonePlan | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || view !== '3d' || zones.length === 0) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    } catch {
      setWebglFailed(true);
      return;
    }
    setWebglFailed(false);

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;

    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1220);
    scene.fog = new THREE.Fog(0x0b1220, 80, 180);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 400);
    camera.position.set(26, 20, 34);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2.05;
    controls.minDistance = 6;
    controls.maxDistance = 120;

    /* ── Lumière (studio industriel) ── */
    const hemi = new THREE.HemisphereLight(0xdfeaff, 0x0b1220, 0.95);
    scene.add(hemi);
    const sun = new THREE.DirectionalLight(0xfff2dd, 2.6);
    sun.position.set(22, 34, 16);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -32;
    sun.shadow.camera.right = 32;
    sun.shadow.camera.top = 32;
    sun.shadow.camera.bottom = -32;
    sun.shadow.bias = -0.0005;
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0xbfd7ee, 0.7);
    fill.position.set(-18, 12, -22);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0x4386b1, 0.9);
    rim.position.set(-14, 8, 26);
    scene.add(rim);

    /* ── Sol ── */
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(170, 170),
      new THREE.MeshStandardMaterial({ color: 0x131a26, roughness: 0.95, metalness: 0 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    const grid = new THREE.GridHelper(170, 34, 0x2b3b52, 0x1b2737);
    scene.add(grid);

    /* ── Disposition des zones sur une grille ── */
    const n = Math.max(zones.length, 1);
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);
    const cellW = 9;
    const cellD = 7;
    const gap = 2;
    const totalW = cols * cellW + (cols - 1) * gap;
    const totalD = rows * cellD + (rows - 1) * gap;

    const zoneGroup = new THREE.Group();
    const pickable: THREE.Object3D[] = [];
    const zonePositions = new Map<string, { x: number; z: number; w: number; d: number }>();

    const materials: THREE.Material[] = [];
    const textures: THREE.Texture[] = [];

    zones.forEach((zone, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = col * (cellW + gap) - totalW / 2 + cellW / 2;
      const z = row * (cellD + gap) - totalD / 2 + cellD / 2;
      const w = cellW - 0.6;
      const d = cellD - 0.6;
      zonePositions.set(zone.id, { x, z, w, d });

      const h = ZONE_HEIGHTS[zone.type] || 7;
      const band = bandForScore(zone.risque);
      const accent = parseHex(band.color);

      const building = new THREE.Group();
      building.name = `zone-${zone.id}`;
      building.userData.zoneId = zone.id;

      /* ── Dalle (emprise) ── */
      const slab = new THREE.Mesh(
        new THREE.BoxGeometry(w, 0.45, d),
        new THREE.MeshStandardMaterial({
          color: tintColor(band.color, 0.72),
          roughness: 0.85,
          metalness: 0.05,
        })
      );
      slab.position.y = 0.225;
      slab.receiveShadow = true;
      building.add(slab);
      materials.push(slab.material as THREE.Material);

      /* ── Emprise au sol teintée par le risque (lecture "vue de dessus") ── */
      const footprint = new THREE.Mesh(
        new THREE.PlaneGeometry(w + 0.7, d + 0.7),
        new THREE.MeshBasicMaterial({
          color: band.color,
          transparent: true,
          opacity: 0.28,
          depthWrite: false,
        })
      );
      footprint.rotation.x = -Math.PI / 2;
      footprint.position.y = 0.03;
      footprint.userData.zoneId = zone.id;
      building.add(footprint);
      pickable.push(footprint);
      materials.push(footprint.material as THREE.Material);

      /* ── Façade texturée (panneaux béton + menuiseries vitrées) teintée ──
         par le niveau de risque : le bâtiment entier porte sa couleur D03
         (vrai BIM coloré), la texture conserve panneaux/joints/menuiseries. ── */
      const wallH = h - 0.45;
      const wallY = 0.45 + wallH / 2;
      const facadeTex = buildFacadeTexture(w, d, wallH, accent);
      textures.push(facadeTex);
      const wallMat = new THREE.MeshStandardMaterial({
        map: facadeTex,
        color: tintColor(band.color, 0.62),
        roughness: 0.9,
        metalness: 0.02,
      });
      materials.push(wallMat);

      const walls: Array<[number, number, number, number]> = [
        [0, -d / 2, w, 0.3],
        [0, d / 2, w, 0.3],
        [-w / 2, 0, 0.3, d],
        [w / 2, 0, 0.3, d],
      ];
      for (const [wx, wz, wl, wt] of walls) {
        const wall = new THREE.Mesh(new THREE.BoxGeometry(wl, wallH, wt), wallMat);
        wall.position.set(wx, wallY, wz);
        wall.castShadow = true;
        wall.receiveShadow = true;
        wall.userData.zoneId = zone.id;
        building.add(wall);
        pickable.push(wall);
      }

      /* ── Porte de chargement (façade avant) : dormant + volet teinté ── */
      const doorGroup = buildDoor(accent);
      doorGroup.position.set(0, 0.45, d / 2 + 0.16);
      building.add(doorGroup);
      doorGroup.traverse((o) => {
        o.userData.zoneId = zone.id;
        pickable.push(o);
      });

      /* ── Acrotère (bord de toiture) teinté par le risque ── */
      const parapetH = 0.55;
      const parapet = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.3, parapetH, d + 0.3),
        new THREE.MeshStandardMaterial({
          color: band.color,
          roughness: 0.55,
          metalness: 0.18,
        })
      );
      parapet.position.y = 0.45 + wallH + parapetH / 2;
      parapet.castShadow = true;
      parapet.receiveShadow = true;
      parapet.userData.zoneId = zone.id;
      building.add(parapet);
      pickable.push(parapet);
      materials.push(parapet.material as THREE.Material);

      /* ── Bande lumineuse du parapet (cadre couleur, lisible de loin) ── */
      const glow = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.42, 0.09, d + 0.42),
        new THREE.MeshBasicMaterial({ color: band.color })
      );
      glow.position.y = 0.45 + wallH + parapetH + 0.05;
      building.add(glow);
      materials.push(glow.material as THREE.Material);

      /* ── Toiture plate : dalle + équipements CVC ── */
      const roofSlab = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.05, 0.35, d + 0.05),
        new THREE.MeshStandardMaterial({
          color: tintColor(band.color, 0.45),
          roughness: 0.7,
          metalness: 0.3,
        })
      );
      roofSlab.position.y = 0.45 + wallH + 0.175;
      roofSlab.receiveShadow = true;
      building.add(roofSlab);
      materials.push(roofSlab.material as THREE.Material);

      buildRoofUnits(building, w, d, 0.45 + wallH + 0.35);

      /* ── Arêtes BIM : cadre teinté par le risque (câblage visible) ── */
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)),
        new THREE.LineBasicMaterial({ color: band.color, transparent: true, opacity: 0.9 })
      );
      edges.position.y = h / 2;
      building.add(edges);
      materials.push(edges.material as THREE.Material);

      /* ── Panneau de zone (toiture) avec le score ── */
      const labelCanvas = document.createElement('canvas');
      labelCanvas.width = 512;
      labelCanvas.height = 128;
      const ctx = labelCanvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = 'rgba(9,14,22,0.88)';
        ctx.fillRect(0, 0, 512, 128);
        ctx.strokeStyle = band.color;
        ctx.lineWidth = 4;
        ctx.strokeRect(4, 4, 504, 120);
        ctx.fillStyle = '#e5e7eb';
        ctx.font = 'bold 34px Google Sans, system-ui, sans-serif';
        const label = (zone.nom || zone.id).slice(0, 26);
        ctx.fillText(label, 24, 52);
        ctx.fillStyle = band.color;
        ctx.font = 'bold 30px Google Sans, system-ui, sans-serif';
        ctx.fillText(`${zone.risque ?? '—'} · ${band.label}`, 24, 102);
      }
      const labelTex = new THREE.CanvasTexture(labelCanvas);
      labelTex.colorSpace = THREE.SRGBColorSpace;
      textures.push(labelTex);
      const labelMat = new THREE.MeshBasicMaterial({
        map: labelTex,
        transparent: true,
        depthWrite: false,
      });
      materials.push(labelMat);
      const labelPlane = new THREE.Mesh(new THREE.PlaneGeometry(5.4, 1.35), labelMat);
      labelPlane.position.set(0, 0.45 + wallH + parapetH + 1.0, 0);
      labelPlane.rotation.x = -Math.PI / 2;
      building.add(labelPlane);

      building.position.set(x, 0, z);
      zoneGroup.add(building);
    });

    /* ── Équipements 3D par type, répartis dans leur zone ── */
    const equipGroup = new THREE.Group();

    equipements.forEach((eq) => {
      const pos = zonePositions.get(eq.zone_id || '');
      if (!pos) return;
      const band = bandForScore(eq.risque);
      const mesh = buildEquipMesh(eq, band.color);
      const zoneEqs = equipements.filter((ee) => (ee.zone_id || '') === (eq.zone_id || ''));
      const idx = zoneEqs.findIndex((ee) => ee.id === eq.id);
      const perRow = Math.max(1, Math.min(3, Math.floor(pos.w / 2.6)));
      const col = idx % perRow;
      const row = Math.floor(idx / perRow);
      const nx = pos.w / 2 - 2.4 - col * 2.4;
      const nz = pos.d / 2 - 2.2 - row * 2.2;
      const ex = pos.x - pos.w / 2 + nx + 1.2;
      const ez = pos.z - pos.d / 2 + nz + 1.2;
      mesh.position.set(ex, 0.45, ez);
      mesh.traverse((o) => {
        o.userData.equipId = eq.id;
        o.userData.zoneId = eq.zone_id || pos.x !== undefined ? (eq.zone_id || '') : '';
      });
      equipGroup.add(mesh);
    });

    scene.add(zoneGroup);
    scene.add(equipGroup);

    /* ── Clic / survol : sélection de zone ── */
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let isDragging = false;

    const pickZone = (e: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(pickable, true);
      const hit = hits.find((hh) => (hh.object.userData.zoneId as string | undefined) != null);
      return (hit?.object.userData.zoneId as string | undefined) || null;
    };

    const onPointerDown = () => {
      isDragging = false;
    };
    const onPointerMove = (e: PointerEvent) => {
      if (e.buttons > 0) isDragging = true;
      renderer.domElement.style.cursor = pickZone(e) ? 'pointer' : 'grab';
    };
    const onClick = (e: PointerEvent) => {
      if (isDragging) return;
      const zoneId = pickZone(e);
      const zone = zoneId ? zones.find((zz) => zz.id === zoneId) || null : null;
      setSelected((prev) => (prev?.id === zoneId ? prev : zone));
    };

    renderer.domElement.addEventListener('pointerdown', onPointerDown);
    renderer.domElement.addEventListener('pointermove', onPointerMove);
    renderer.domElement.addEventListener('click', onClick);

    /* ── Cadrage de la caméra ── */
    const box = new THREE.Box3().setFromObject(zoneGroup);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    controls.target.copy(center).add(new THREE.Vector3(0, size.y / 2, 0));
    const dist = Math.max(size.x, size.z, 10) * 1.6 + size.y * 1.5;
    camera.position.copy(controls.target).add(new THREE.Vector3(dist * 0.72, dist * 0.6, dist * 0.9));
    controls.update();

    /* ── Animation ── */
    let raf = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    };
    animate();

    /* ── Redimensionnement ── */
    const onResize = () => {
      const w = container.clientWidth || 800;
      const h = container.clientHeight || 500;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      renderer.domElement.removeEventListener('pointerdown', onPointerDown);
      renderer.domElement.removeEventListener('pointermove', onPointerMove);
      renderer.domElement.removeEventListener('click', onClick);
      controls.dispose();
      materials.forEach((m) => m.dispose());
      textures.forEach((t) => t.dispose());
      scene.traverse((o) => {
        const mesh = o as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
      });
      renderer.dispose();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, zones, equipements]);

  const totalSurface = zones.reduce((a, z) => a + (typeof z.surface_m2 === 'number' ? z.surface_m2 : 0), 0);
  const globalBand = bandForScore(scoreGlobal ?? 0);

  return (
    <div className="bim-wrap usine-bim-wrap">
      <header className="bim-header usine-bim-header">
        <div className="bim-title">
          <h2>Jumeau BIM de l'usine</h2>
          <p className="bim-meta">
            {nomUsine || 'Usine'} · {zones.length} bâtiments · {equipements.length} équipements ·
            {totalSurface ? ` ${totalSurface.toLocaleString('fr-FR')} m²` : ''}
            {scoreGlobal != null ? ` · score ${scoreGlobal}/100 (${globalBand.label})` : ''}
          </p>
        </div>
        <div className="bim-view-tabs usine-bim-tabs" role="tablist" aria-label="Mode de visualisation">
          <button
            type="button"
            role="tab"
            aria-selected={view === '3d'}
            className={`bim-view-tab${view === '3d' ? ' active' : ''}`}
            onClick={() => setView('3d')}
          >
            <md-icon>view_in_ar</md-icon>
            <span>Jumeau 3D</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === '2d'}
            className={`bim-view-tab${view === '2d' ? ' active' : ''}`}
            onClick={() => setView('2d')}
          >
            <md-icon>map</md-icon>
            <span>Plan 2D</span>
          </button>
        </div>
      </header>

      {view === '3d' ? (
        webglFailed ? (
          <div className="analyse-empty">
            <md-icon>view_in_ar</md-icon>
            <h2>WebGL indisponible</h2>
            <p>Votre navigateur ne prend pas en charge le rendu 3D — basculez sur la vue Plan 2D.</p>
            <md-filled-button onClick={() => setView('2d')}>
              <md-icon slot="icon">map</md-icon> Voir le plan 2D
            </md-filled-button>
          </div>
        ) : (
          <div className="usine-bim-stage">
            <div ref={containerRef} className="usine-bim-canvas" />

            {/* Légende */}
            <div className="usine-bim-legend">
              <span className="usine-legend-item" key="legend-title">
                <span className="usine-legend-dot" style={{ background: 'linear-gradient(135deg,#e5e7eb,#6b7280)' }} />
                Bâtiment coloré par son niveau de risque (enveloppe · toiture · arêtes)
              </span>
              {['tres_faible', 'faible', 'modere', 'eleve', 'critique'].map((k) => (
                <span className="usine-legend-item" key={k}>
                  <span className="usine-legend-dot" style={{ background: bandForKey(k).color }} />
                  {bandForKey(k).label}
                </span>
              ))}
            </div>

            {/* Fiche zone sélectionnée */}
            {selected && (
              <aside className="usine-bim-info">
                <header>
                  <strong>{selected.nom}</strong>
                  <button type="button" aria-label="Fermer" onClick={() => setSelected(null)}>
                    <md-icon>close</md-icon>
                  </button>
                </header>
                <span className="usine-bim-info-band" style={{ color: bandForScore(selected.risque).color }}>
                  Risque {selected.risque ?? '—'}/100 · {bandForScore(selected.risque).label}
                </span>
                <div className="usine-bim-info-kv">
                  <span>Type</span>
                  <strong>{TYPE_ZONE_LABELS[selected.type] || selected.type}</strong>
                  <span>Surface</span>
                  <strong>
                    {typeof selected.surface_m2 === 'number'
                      ? `${selected.surface_m2.toLocaleString('fr-FR')} m²`
                      : '—'}
                  </strong>
                  <span>Vulnérabilité</span>
                  <strong>{selected.vulnerabilite ?? '—'}/100</strong>
                </div>
                {selected.description ? <p>{selected.description}</p> : null}
                <footer>
                  {equipements.filter((e) => e.zone_id === selected.id).length} équipement(s) dans cette zone
                </footer>
              </aside>
            )}

            {/* Hint */}
            <div className="usine-bim-hint">
              <md-icon>pan_tool_alt</md-icon>
              <span>Glisser = orbiter · Molette = zoom · Clic sur un bâtiment = fiche de zone</span>
            </div>
          </div>
        )
      ) : (
        <div className="usine-jumeau-2d usine-jumeau-2d-bim">
          <UsineJumeau
            zones={zones.map((z) => ({
              id: z.id,
              nom: z.nom,
              type: TYPE_ZONE_LABELS[z.type] || z.type,
              surface_m2: z.surface_m2 ?? undefined,
              score_risque: z.risque,
              niveau: normalizeNiveau(z.niveau) as any,
            }))}
            equipements={equipements.map((e) => ({
              id: e.id,
              nom: e.nom,
              type: TYPE_EQUIP_LABELS[e.type] || e.type,
              zone: e.zone || '',
              score_risque: e.risque,
            }))}
          />
        </div>
      )}

      <p className="bim-footnote">
        Générateur de jumeau BIM three.js — enveloppe industrielle réaliste (façades béton,
        menuiseries vitrées, toiture plate, équipements CVC) entièrement colorée par le risque
        D03 (enveloppe · toiture · acrotère · arêtes · emprise au sol) · fiche de zone au clic ·{' '}
        <strong>représentation pédagogique — ne remplace pas une maquette BIM d'ingénierie.</strong>
      </p>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   GÉNÉRATEUR DE FAÇADE — panneaux béton + joints + menuiseries vitrées + bande
   d'acrotère teintée (risque). Une seule texture Canvas mappée sur les murs.
   ═══════════════════════════════════════════════════════════════════════════ */

function buildFacadeTexture(
  w: number,
  d: number,
  wallH: number,
  accent: { r: number; g: number; b: number }
): THREE.CanvasTexture {
  const W = 1024;
  const H = 1024;
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  const ctx = c.getContext('2d')!;

  /* Fond béton dégradé (gris industriel) */
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, '#cdd5dd');
  grad.addColorStop(0.55, '#b6c0cb');
  grad.addColorStop(1, '#97a3b0');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);

  /* Bruit de surface discret (granularité béton) */
  for (let i = 0; i < 2200; i++) {
    const alpha = Math.random() * 0.05;
    ctx.fillStyle = Math.random() > 0.5 ? `rgba(255,255,255,${alpha})` : `rgba(40,50,60,${alpha})`;
    ctx.fillRect(Math.random() * W, Math.random() * H, 2, 2);
  }

  /* Panneaux verticaux (pilastres) + joints */
  const panels = Math.max(3, Math.round(w / 2.2));
  ctx.strokeStyle = 'rgba(60,72,84,0.55)';
  ctx.lineWidth = 5;
  for (let i = 1; i < panels; i++) {
    ctx.beginPath();
    ctx.moveTo((W / panels) * i, 0);
    ctx.lineTo((W / panels) * i, H);
    ctx.stroke();
  }
  /* Joints horizontaux */
  ctx.lineWidth = 3;
  for (let y = 0.22; y < 0.92; y += 0.16) {
    ctx.beginPath();
    ctx.moveTo(0, y * H);
    ctx.lineTo(W, y * H);
    ctx.stroke();
  }

  /* Menuiseries vitrées (série industrielle) */
  const cols = Math.max(2, Math.round(panels * 1.2));
  const rows = Math.max(2, Math.round(wallH / 1.7));
  const mw = (W / cols) * 0.62;
  const mh = (H / rows) * 0.62;
  for (let r = 0; r < rows; r++) {
    for (let c2 = 0; c2 < cols; c2++) {
      const cx = (W / cols) * (c2 + 0.5);
      const cy = (H / rows) * (r + 0.5);
      if (r === 0 || r === rows - 1) continue; // bandes basses / hautes pleines
      ctx.fillStyle = 'rgba(30,42,54,0.92)';
      ctx.fillRect(cx - mw / 2, cy - mh / 2, mw, mh);
      /* cadre de fenêtre */
      ctx.strokeStyle = 'rgba(190,200,210,0.9)';
      ctx.lineWidth = 3;
      ctx.strokeRect(cx - mw / 2, cy - mh / 2, mw, mh);
      /* reflet de verre */
      ctx.fillStyle = 'rgba(157,184,207,0.22)';
      ctx.fillRect(cx - mw / 2 + 6, cy - mh / 2 + 6, mw * 0.5, mh * 0.4);
    }
  }

  /* Bande d'acrotère teintée (risque) en haut de façade */
  const accentCss = `rgb(${accent.r}, ${accent.g}, ${accent.b})`;
  ctx.fillStyle = accentCss;
  ctx.globalAlpha = 0.92;
  ctx.fillRect(0, 0, W, H * 0.07);
  ctx.globalAlpha = 1;

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  return tex;
}

/* ── Porte de chargement : cadre acier + volet teinté par le risque ── */
function buildDoor(accent: { r: number; g: number; b: number }): THREE.Group {
  const g = new THREE.Group();
  const steel = new THREE.MeshStandardMaterial({ color: MAT.steelDark, roughness: 0.5, metalness: 0.6 });
  const accentMat = new THREE.MeshStandardMaterial({
    color: `rgb(${accent.r}, ${accent.g}, ${accent.b})`,
    roughness: 0.4,
    metalness: 0.5,
  });
  const glass = new THREE.MeshStandardMaterial({
    color: 0x8fa8c2,
    roughness: 0.15,
    metalness: 0.2,
    transparent: true,
    opacity: 0.7,
  });

  /* Dormant */
  const frame = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.6, 0.12), steel);
  frame.position.y = 1.3;
  g.add(frame);
  /* Volet roulant teinté (risque) */
  const shutter = new THREE.Mesh(new THREE.BoxGeometry(1.9, 1.7, 0.1), accentMat);
  shutter.position.y = 1.85;
  g.add(shutter);
  /* Vitrage supérieur */
  const win = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.55, 0.08), glass);
  win.position.y = 0.55;
  g.add(win);
  return g;
}

/* ── Équipements de toiture (CVC) : unités, gaines, cheminées ── */
function buildRoofUnits(parent: THREE.Group, w: number, d: number, baseY: number) {
  const steelDark = new THREE.MeshStandardMaterial({ color: 0x46566b, roughness: 0.6, metalness: 0.5 });
  const steelLight = new THREE.MeshStandardMaterial({ color: 0x6b7d92, roughness: 0.55, metalness: 0.6 });
  const vent = new THREE.MeshStandardMaterial({ color: 0x39485a, roughness: 0.7 });

  const unit = (x: number, z: number, s: number) => {
    const u = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(s, s * 0.8, s), steelDark);
    body.position.y = s * 0.4;
    body.castShadow = true;
    u.add(body);
    const top = new THREE.Mesh(new THREE.BoxGeometry(s * 0.9, 0.18, s * 0.9), steelLight);
    top.position.y = s * 0.8 + 0.09;
    top.castShadow = true;
    u.add(top);
    const ventL = new THREE.Mesh(new THREE.CylinderGeometry(s * 0.1, s * 0.12, 0.35, 10), vent);
    ventL.position.set(-s * 0.3, s * 0.8 + 0.35, -s * 0.25);
    u.add(ventL);
    u.position.set(x, baseY, z);
    parent.add(u);
  };

  const chems = Math.max(1, Math.floor(w / 4));
  const positions: Array<[number, number, number]> = [];
  for (let i = 0; i < chems; i++) {
    positions.push([-w / 2 + 1.6 + i * (w / chems), -d / 4, 1.1]);
    positions.push([-w / 2 + 1.6 + i * (w / chems), d / 4, 1.0]);
  }
  positions.forEach(([x, z, s]) => unit(x, z, s));
}

/* ─────────── Construction des équipements 3D ─────────── */

function buildEquipMesh(eq: Equipement, color: string): THREE.Group {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.7 });
  const steel = new THREE.MeshStandardMaterial({ color: 0x3a4a5c, roughness: 0.5, metalness: 0.65 });
  const mats: THREE.Material[] = [mat, steel];

  const add = (geo: THREE.BufferGeometry, m: THREE.Material, x = 0, y = 0, z = 0, props: Partial<THREE.Mesh> = {}) => {
    const mesh = new THREE.Mesh(geo, m);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    Object.assign(mesh, props);
    g.add(mesh);
    return mesh;
  };

  /* Plaque de base (tous les équipements reposent sur un socle) */
  add(new THREE.BoxGeometry(1.9, 0.1, 1.4), steel, 0, 0.05, 0);

  switch (eq.type) {
    case 'ligne_production':
      add(new THREE.BoxGeometry(3.2, 0.7, 1.1), mat);
      add(new THREE.BoxGeometry(3.2, 0.18, 1.2), mat, 0, 0.44, 0);
      add(new THREE.CylinderGeometry(0.28, 0.34, 0.5, 12), mat, 0.9, 0.6, 0);
      break;
    case 'machine_outil':
      add(new THREE.BoxGeometry(1.4, 1.5, 1.3), mat);
      add(new THREE.CylinderGeometry(0.42, 0.5, 0.35, 16), mat, 0.7, 0.18, 0);
      add(new THREE.BoxGeometry(1.5, 0.12, 1.4), mat, 0, 0.06, 0);
      break;
    case 'four':
      add(
        new THREE.BoxGeometry(1.7, 1.3, 1.5),
        new THREE.MeshStandardMaterial({ color: 0x39485a, roughness: 0.5, metalness: 0.6 })
      );
      add(
        new THREE.BoxGeometry(1.0, 0.6, 0.8),
        new THREE.MeshStandardMaterial({ color: color, roughness: 0.35, metalness: 0.4 }),
        0,
        0.3,
        0.8
      );
      add(
        new THREE.BoxGeometry(0.7, 0.3, 0.6),
        new THREE.MeshStandardMaterial({ color: '#ffab40', emissive: 0xff6d00, emissiveIntensity: 1.5 }),
        0,
        0.15,
        0.76
      );
      break;
    case 'cuve':
    case 'reservoir':
      add(new THREE.CylinderGeometry(0.9, 0.9, 2.0, 20), mat);
      add(new THREE.TorusGeometry(0.9, 0.06, 8, 20), mat, 0, 1.0, 0);
      break;
    case 'silo':
      add(new THREE.CylinderGeometry(0.75, 0.85, 2.6, 18), mat);
      add(new THREE.ConeGeometry(0.85, 0.9, 18), mat, 0, 1.75, 0);
      add(new THREE.CylinderGeometry(0.12, 0.12, 0.9, 8), mat, 0, 0.1, 0);
      break;
    case 'compresseur':
    case 'groupe_froid':
      add(new THREE.BoxGeometry(1.1, 1.0, 0.9), mat);
      add(new THREE.CylinderGeometry(0.32, 0.32, 0.6, 14), mat, 0, 0.8, 0);
      add(new THREE.BoxGeometry(1.2, 0.14, 1.0), mat, 0, 0.07, 0);
      break;
    case 'pompe':
      add(new THREE.CylinderGeometry(0.32, 0.4, 0.7, 14), mat, 0, 0.35, 0);
      add(new THREE.BoxGeometry(0.5, 0.16, 0.5), mat, 0, 0.08, 0);
      break;
    case 'chaudiere':
      add(new THREE.BoxGeometry(1.3, 1.4, 1.2), mat);
      add(new THREE.CylinderGeometry(0.26, 0.26, 1.3, 12), mat, 0, 1.35, 0);
      add(new THREE.BoxGeometry(0.5, 0.4, 0.2), mat, 0.4, 0.2, 0.6);
      break;
    case 'pont_roulant':
      add(new THREE.BoxGeometry(0.22, 2.0, 0.22), mat, -1.5, 1.0, 0);
      add(new THREE.BoxGeometry(0.22, 2.0, 0.22), mat, 1.5, 1.0, 0);
      add(new THREE.BoxGeometry(3.4, 0.28, 0.55), mat, 0, 2.0, 0);
      add(new THREE.BoxGeometry(0.3, 0.12, 0.9), mat, 0, 1.86, 0.3);
      break;
    case 'robot':
      add(new THREE.BoxGeometry(0.9, 1.15, 0.9), mat, 0, 0.57, 0);
      add(new THREE.BoxGeometry(0.4, 0.8, 0.4), mat, 0.6, 1.4, 0);
      add(new THREE.CylinderGeometry(0.18, 0.18, 0.9, 10), mat, 0.3, 1.15, 0);
      break;
    case 'automate':
    case 'serveur':
    case 'laboratoire':
      add(new THREE.BoxGeometry(1.0, 1.7, 0.8), mat);
      for (let i = 0; i < 3; i++) {
        add(new THREE.BoxGeometry(0.84, 0.05, 0.6), new THREE.MeshStandardMaterial({ color: 0x1a2636 }), 0, 0.45 + i * 0.45, 0.01);
      }
      break;
    default:
      add(new THREE.BoxGeometry(1.0, 1.0, 1.0), mat);
  }

  if (eq.matieres_dangereuses) {
    add(
      new THREE.ConeGeometry(0.28, 0.5, 10),
      new THREE.MeshStandardMaterial({ color: 0xff9a00, emissive: 0xff6d00, emissiveIntensity: 1.1 }),
      0,
      2.1,
      0
    );
  }
  if (eq.critique_production) {
    add(
      new THREE.TorusGeometry(0.22, 0.06, 8, 14),
      new THREE.MeshStandardMaterial({ color: 0x4386b1, emissive: 0x1f5f86, emissiveIntensity: 1.2 }),
      -0.7,
      2.1,
      0
    );
  }

  g.userData.equipId = eq.id;
  return g;
}
