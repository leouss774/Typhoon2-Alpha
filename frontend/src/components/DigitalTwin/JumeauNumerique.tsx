import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface JumeauNumeriqueProps {
  zonesData: any;
  onZoneClick: (zoneName: string) => void;
  onZoneHover?: (zoneName: string | null) => void;
}

const ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"];
const WIRE_COLOR = 0x5fb2ff;

function scoreToColor(score: number): number {
  if (score < 30) return 0x3fb950;
  if (score < 60) return 0xd29922;
  if (score < 80) return 0xdb6d28;
  return 0xda3633;
}

function makeFillMat(color: number, opacity = 0.16) {
  return new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false });
}

function makeWireMat() {
  return new THREE.LineBasicMaterial({ color: WIRE_COLOR, transparent: true, opacity: 0.85 });
}

export const JumeauNumerique: React.FC<JumeauNumeriqueProps> = ({ zonesData, onZoneClick, onZoneHover }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const clickRef = useRef(onZoneClick);
  const hoverRef = useRef(onZoneHover);
  clickRef.current = onZoneClick;
  hoverRef.current = onZoneHover;

  // Ref pour mise à jour dynamique des couleurs
  const updColorsRef = useRef<((z: any) => void) | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const w = container.clientWidth, h = container.clientHeight || 500;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x04070c);
    scene.fog = new THREE.Fog(0x04070c, 18, 45);
    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h); renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    scene.add(new THREE.HemisphereLight(0x3a7bd5, 0x04070c, 0.7));
    const rim = new THREE.DirectionalLight(0x4da6ff, 0.5); rim.position.set(-8, 10, -6); scene.add(rim);
    const key = new THREE.DirectionalLight(0xbfe0ff, 0.4); key.position.set(8, 12, 8); scene.add(key);

    const grid = new THREE.GridHelper(50, 50, 0x1560ff, 0x0d2647);
    grid.material.transparent = true; grid.material.opacity = 0.35; scene.add(grid);

    const ringGeo = new THREE.RingGeometry(5.6, 5.75, 64);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x4da6ff, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
    const scanRing = new THREE.Mesh(ringGeo, ringMat);
    scanRing.rotation.x = -Math.PI / 2; scanRing.position.y = 0.01;
    scene.add(scanRing);

    const house = new THREE.Group(); scene.add(house);
    const zGroups: Record<string, THREE.Group> = {};
    const zMeshes: Record<string, THREE.Mesh[]> = {};
    const iMeshes: THREE.Mesh[] = [];
    const zSprites: Record<string, THREE.Sprite> = {};

    ZONE_NAMES.forEach(n => {
      const g = new THREE.Group(); g.name = n; house.add(g);
      zGroups[n] = g; zMeshes[n] = [];
    });

    const reg = (zn: string, m: THREE.Mesh) => { m.userData.zoneName = zn; zMeshes[zn].push(m); iMeshes.push(m); };
    const addP = (g: THREE.Group, geo: THREE.BufferGeometry, pos: THREE.Vector3, fc: number, op?: number) => {
      const f = new THREE.Mesh(geo, makeFillMat(fc, op)); f.position.copy(pos); g.add(f);
      const wr = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat()); wr.position.copy(pos); g.add(wr);
      return f;
    };

    const W = 6.0, D = 5.0, fH = 1.35;
    const fY = 0.55, rY = 0.7 + fH, eY = 0.7 + 3 * fH, evY = 0.7 + 4 * fH, riY = evY + 1.7;

    reg("sous_sol", addP(zGroups.sous_sol, new THREE.BoxGeometry(W + 0.3, 1.6, D + 0.3), new THREE.Vector3(0, -0.4, 0), 0x3fb950, 0.18));
    reg("fondations", addP(zGroups.fondations, new THREE.BoxGeometry(W + 0.4, 0.3, D + 0.4), new THREE.Vector3(0, fY, 0), 0x3fb950, 0.18));

    const wt = 0.2;
    [["murs_nord", 0, -1], ["murs_sud", 0, 1], ["murs_est", W/2, 0], ["murs_ouest", -W/2, 0]].forEach(([nm, xOff, zOff]) => {
      const sX = (xOff as number) === 0 ? W : wt;
      const sZ = (xOff as number) === 0 ? wt : D;
      const z = zOff as number;
      const box = new THREE.BoxGeometry(sX, 2 * fH, sZ);
      reg(nm as string, addP(zGroups[nm as string], box, new THREE.Vector3(xOff as number, rY, z), 0x3fb950, 0.16));
      reg(nm as string, addP(zGroups[nm as string], box, new THREE.Vector3(xOff as number, eY, z), 0x3fb950, 0.16));
    });

    const bGeo = new THREE.BoxGeometry(W + 0.15, 0.08, D + 0.15);
    const bF = new THREE.Mesh(bGeo, makeFillMat(0x5fb2ff, 0.25));
    bF.position.set(0, 0.7 + 2 * fH, 0); house.add(bF);
    const bL = new THREE.LineSegments(new THREE.EdgesGeometry(bGeo), makeWireMat());
    bL.position.copy(bF.position); house.add(bL);

    const rH = D / 2 + 0.35, sL = Math.sqrt(rH ** 2 + 1.7 ** 2), rA = Math.atan2(1.7, rH);
    [-1, 1].forEach(s => {
      const geo = new THREE.BoxGeometry(W + 0.7, 0.12, sL);
      const m = new THREE.Mesh(geo, makeFillMat(0x3fb950, 0.16));
      m.rotation.x = s * rA; m.position.set(0, (evY + riY) / 2, s * D / 4);
      zGroups.toiture.add(m);
      const wr = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat());
      wr.rotation.copy(m.rotation); wr.position.copy(m.position); zGroups.toiture.add(wr);
      reg("toiture", m);
    });

    [-1, 1].forEach(zS => {
      const geo = new THREE.BufferGeometry();
      const hW = W / 2;
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-hW, evY, zS, hW, evY, zS, 0, riY, zS]), 3));
      geo.computeVertexNormals();
      const m = new THREE.Mesh(geo, makeFillMat(0x3fb950, 0.16));
      zGroups.toiture.add(m);
      const wr = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat());
      zGroups.toiture.add(wr);
      reg("toiture", m);
    });

    const decor = new THREE.Group(); house.add(decor);
    const aD = (geo: THREE.BufferGeometry, pos: THREE.Vector3) => {
      const f = new THREE.Mesh(geo, makeFillMat(0x5fb2ff, 0.22)); f.position.copy(pos); decor.add(f);
      const wr = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat()); wr.position.copy(pos); decor.add(wr);
    };
    [-1.6, 1.6].forEach(x => aD(new THREE.BoxGeometry(0.9, 1.1, 0.06), new THREE.Vector3(x, rY - 0.1, D/2 + 0.02)));
    [-1.6, 1.6].forEach(x => aD(new THREE.BoxGeometry(0.9, 1.0, 0.06), new THREE.Vector3(x, eY, D/2 + 0.02)));
    aD(new THREE.BoxGeometry(0.9, 1.9, 0.06), new THREE.Vector3(0, 0.7 + 0.95, D/2 + 0.02));
    [-2.0, 2.0].forEach(x => aD(new THREE.BoxGeometry(0.6, 0.35, 0.06), new THREE.Vector3(x, 0.15, D/2 + 0.16)));
    const gW = 3.0, gD = 4.2, gH = 2.4, gX = -W/2 - gW/2 - 0.05;
    aD(new THREE.BoxGeometry(gW, gH, gD), new THREE.Vector3(gX, 0.7 + gH/2, 0));
    aD(new THREE.BoxGeometry(gW + 0.3, 0.1, gD + 0.3), new THREE.Vector3(gX, 0.7 + gH + 0.05, 0));
    aD(new THREE.BoxGeometry(2.4, 1.9, 0.05), new THREE.Vector3(gX, 0.7 + 0.95, D/2));

    // Labels
    const lA: Record<string, THREE.Vector3> = {
      fondations: new THREE.Vector3(W/2+0.3, fY, D/2+0.3), murs_nord: new THREE.Vector3(0, eY, -D/2),
      murs_sud: new THREE.Vector3(0, eY, D/2), murs_est: new THREE.Vector3(W/2, rY, 0),
      murs_ouest: new THREE.Vector3(-W/2, rY, 0), toiture: new THREE.Vector3(0, riY, 0),
      sous_sol: new THREE.Vector3(-W/2-0.3, -0.2, D/2+0.3)
    };
    const lO: Record<string, THREE.Vector3> = {
      fondations: new THREE.Vector3(1.8, 0.6, 1.8), murs_nord: new THREE.Vector3(0, 1.6, -1.4),
      murs_sud: new THREE.Vector3(0, 1.6, 1.4), murs_est: new THREE.Vector3(2.4, 1.2, 0),
      murs_ouest: new THREE.Vector3(-2.4, 1.2, 0), toiture: new THREE.Vector3(0, 1.6, 0),
      sous_sol: new THREE.Vector3(-1.8, 0.3, 1.8)
    };

    function makeLbl(t: string, s: number) {
      const c = document.createElement('canvas'); c.width = 300; c.height = 90;
      const ctx = c.getContext('2d')!; ctx.clearRect(0, 0, c.width, c.height);
      const clr = '#' + scoreToColor(s).toString(16).padStart(6, '0');
      ctx.fillStyle = 'rgba(6,14,26,0.85)'; ctx.strokeStyle = clr; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.roundRect(4, 4, c.width-8, c.height-8, 12); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#cfe8ff'; ctx.font = '600 22px Segoe UI, sans-serif';
      ctx.fillText(t.replace('_', ' '), 20, 36);
      ctx.fillStyle = clr; ctx.font = '700 26px Segoe UI, sans-serif';
      ctx.fillText(s + ' / 100', 20, 70);
      return new THREE.CanvasTexture(c);
    }

    ZONE_NAMES.forEach(n => {
      const tex = makeLbl(n, 0);
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
      const anc = lA[n].clone().add(lO[n]); sp.position.copy(anc); sp.scale.set(1.8, 0.55, 1);
      house.add(sp);
      zSprites[n] = sp;
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([lA[n], anc]),
        new THREE.LineBasicMaterial({ color: WIRE_COLOR, transparent: true, opacity: 0.5 }));
      house.add(line);
    });

    function updColors(z: any) {
      if (!z) return;
      ZONE_NAMES.forEach(n => {
        if (!z[n] || typeof z[n].risque !== 'number') return;
        const score = z[n].risque;
        const c = scoreToColor(score);
        (zMeshes[n] || []).forEach(m => (m.material as THREE.MeshBasicMaterial).color.set(c));
        // Mise a jour du label flottant
        const sp = zSprites[n];
        if (sp) {
          sp.material.map = makeLbl(n, score);
          sp.material.needsUpdate = true;
        }
      });
    }
    updColorsRef.current = updColors;
    if (zonesData) updColors(zonesData);

    // Camera controls (named handlers for cleanup)
    const cT = new THREE.Vector3(0, 2.2, 0);
    let rad = 15, th = Math.PI/4, ph = Math.PI/3, tTh = th, tPh = ph, tRad = rad;
    let drag = false, lX = 0, lY = 0, idle = 0;

    const onMouseDown = (e: MouseEvent) => { drag = true; idle = 0; lX = e.clientX; lY = e.clientY; };
    const onMouseUp = () => { drag = false; idle = 0; };
    const onCamMove = (e: MouseEvent) => {
      if (!drag) return;
      tTh -= (e.clientX - lX) * 0.006; tPh = Math.max(0.4, Math.min(Math.PI/2.1, tPh - (e.clientY - lY) * 0.006));
      lX = e.clientX; lY = e.clientY;
    };
    const onWheel = (e: WheelEvent) => { e.preventDefault(); tRad = Math.max(6, Math.min(28, tRad + e.deltaY * 0.01)); };

    renderer.domElement.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('mousemove', onCamMove);
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });

    // Raycast (named handlers)
    const ray = new THREE.Raycaster();
    const mPos = new THREE.Vector2();
    let hovG: THREE.Group | null = null;
    const getH = (e: MouseEvent) => {
      mPos.x = (e.clientX / window.innerWidth) * 2 - 1;
      mPos.y = -(e.clientY / window.innerHeight) * 2 + 1;
      ray.setFromCamera(mPos, camera);
      return ray.intersectObjects(iMeshes);
    };

    const onRayMove = (e: MouseEvent) => {
      if (drag) return;
      const hits = getH(e);
      const ng = hits.length ? hits[0].object.parent as THREE.Group : null;
      if (hovG && hovG !== ng) { hovG.scale.set(1, 1, 1); hovG = null; renderer.domElement.style.cursor = 'grab'; }
      if (ng && ng !== hovG) { hovG = ng; hovG.scale.set(1.02, 1.02, 1.02); renderer.domElement.style.cursor = 'pointer'; }
      if (hoverRef.current) hoverRef.current(hits.length ? hits[0].object.userData.zoneName : null);
    };
    renderer.domElement.addEventListener('mousemove', onRayMove);

    const onClick = (e: MouseEvent) => {
      const hits = getH(e);
      if (hits.length && clickRef.current) clickRef.current(hits[0].object.userData.zoneName);
    };
    renderer.domElement.addEventListener('click', onClick);

    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', onResize);

    let lf = performance.now(), aid: number;
    const anim = (now: number) => {
      aid = requestAnimationFrame(anim);
      const dt = Math.min((now - lf) / 1000, 0.1); lf = now;
      if (!drag) { idle += dt; if (idle > 2) tTh += dt * 0.06; }
      th += (tTh - th) * 0.1; ph += (tPh - ph) * 0.1; rad += (tRad - rad) * 0.1;
      camera.position.set(cT.x + rad * Math.sin(ph) * Math.sin(th), cT.y + rad * Math.cos(ph), cT.z + rad * Math.sin(ph) * Math.cos(th));
      camera.lookAt(cT);
      scanRing.material.opacity = 0.35 + Math.sin(now * 0.0015) * 0.15;
      renderer.render(scene, camera);
    };
    requestAnimationFrame(anim);

    cleanupRef.current = () => {
      cancelAnimationFrame(aid);
      renderer.domElement.removeEventListener('mousedown', onMouseDown);
      renderer.domElement.removeEventListener('mousemove', onRayMove);
      renderer.domElement.removeEventListener('click', onClick);
      renderer.domElement.removeEventListener('wheel', onWheel);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('mousemove', onCamMove);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
    };
    return () => { if (cleanupRef.current) cleanupRef.current(); };
  }, []);

  // Mise a jour dynamique quand zonesData change (bascule 2025/2050)
  useEffect(() => {
    if (zonesData && updColorsRef.current) updColorsRef.current(zonesData);
  }, [zonesData]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', cursor: 'grab' }} />;
};
