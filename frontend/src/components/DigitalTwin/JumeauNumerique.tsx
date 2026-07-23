import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface JumeauNumeriqueProps {
  zonesData: any;
  geometrie?: { largeur_m: number; profondeur_m: number; orientation_deg: number; };
  onZoneClick: (zoneName: string) => void;
}

export const JumeauNumerique: React.FC<JumeauNumeriqueProps> = ({
  zonesData,
  geometrie = { largeur_m: 7, profondeur_m: 5, orientation_deg: 0 },
  onZoneClick,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const meshesRef = useRef<{ [key: string]: THREE.Mesh[] }>({});
  const interactiveListRef = useRef<THREE.Mesh[]>([]);

  const scoreToColor = (score: number): number => {
    if (score < 30) return 0x3fb950;
    if (score < 60) return 0xd29922;
    if (score < 80) return 0xdb6d28;
    return 0xda3633;
  };

  useEffect(() => {
    if (!containerRef.current) return;
    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight || 500;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);

    scene.add(new THREE.HemisphereLight(0x3a7bd5, 0x04070c, 0.7));
    const pointLight = new THREE.DirectionalLight(0x4da6ff, 0.6);
    pointLight.position.set(5, 12, 8);
    scene.add(pointLight);

    const grid = new THREE.GridHelper(30, 30, 0x1560ff, 0x0d2647);
    grid.material.transparent = true;
    grid.material.opacity = 0.3;
    scene.add(grid);

    const house = new THREE.Group();
    house.rotation.y = THREE.MathUtils.degToRad(-geometrie.orientation_deg);
    scene.add(house);

    const W = geometrie.largeur_m;
    const D = geometrie.profondeur_m;
    const floorH = 1.35;
    const rezY = 0.7 + floorH;

    const makeWireMat = () => new THREE.LineBasicMaterial({ color: 0x5fb2ff, transparent: true, opacity: 0.8 });
    const makeFillMat = (zoneName: string) => new THREE.MeshBasicMaterial({
      color: scoreToColor(zonesData[zoneName]?.risque || 0),
      transparent: true, opacity: 0.25, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false
    });

    const createZone = (name: string, geo: THREE.BufferGeometry, pos: THREE.Vector3) => {
      const fill = new THREE.Mesh(geo, makeFillMat(name));
      fill.position.copy(pos);
      fill.userData = { zoneName: name };
      house.add(fill);
      const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat());
      wire.position.copy(pos);
      house.add(wire);
      if (!meshesRef.current[name]) meshesRef.current[name] = [];
      meshesRef.current[name].push(fill);
      interactiveListRef.current.push(fill);
    };

    createZone("sous_sol", new THREE.BoxGeometry(W + 0.2, 1.6, D + 0.2), new THREE.Vector3(0, -0.4, 0));
    createZone("fondations", new THREE.BoxGeometry(W + 0.3, 0.3, D + 0.3), new THREE.Vector3(0, 0.55, 0));
    createZone("murs_nord", new THREE.BoxGeometry(W, 2 * floorH, 0.2), new THREE.Vector3(0, rezY, -D / 2));
    createZone("murs_sud", new THREE.BoxGeometry(W, 2 * floorH, 0.2), new THREE.Vector3(0, rezY, D / 2));
    createZone("murs_est", new THREE.BoxGeometry(0.2, 2 * floorH, D), new THREE.Vector3(W / 2, rezY, 0));
    createZone("murs_ouest", new THREE.BoxGeometry(0.2, 2 * floorH, D), new THREE.Vector3(-W / 2, rezY, 0));

    const roofLen = Math.sqrt(Math.pow(D/2 + 0.3, 2) + Math.pow(1.5, 2));
    const buildPan = (sign: number) => {
      const geo = new THREE.BoxGeometry(W + 0.6, 0.1, roofLen);
      const mesh = new THREE.Mesh(geo, makeFillMat("toiture"));
      mesh.rotation.x = sign * Math.atan2(1.5, D/2 + 0.3);
      mesh.position.set(0, 0.7 + 3.2 * floorH, sign * (D / 4));
      mesh.userData = { zoneName: "toiture" };
      house.add(mesh);
      const wire = new THREE.LineSegments(new THREE.EdgesGeometry(geo), makeWireMat());
      wire.rotation.copy(mesh.rotation);
      wire.position.copy(mesh.position);
      house.add(wire);
      if (!meshesRef.current["toiture"]) meshesRef.current["toiture"] = [];
      meshesRef.current["toiture"].push(mesh);
      interactiveListRef.current.push(mesh);
    };
    buildPan(1); buildPan(-1);

    let cameraAngle = Math.PI / 4;
    camera.position.set(16 * Math.sin(cameraAngle), 8, 16 * Math.cos(cameraAngle));
    camera.lookAt(new THREE.Vector3(0, 1.8, 0));

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (e: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - bounds.left) / width) * 2 - 1;
      mouse.y = -((e.clientY - bounds.top) / height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(interactiveListRef.current);
      if (hits.length > 0) onZoneClick(hits[0].object.userData.zoneName);
    };
    renderer.domElement.addEventListener('click', onClick);

    let animId: number;
    const loop = () => {
      animId = requestAnimationFrame(loop);
      cameraAngle += 0.002;
      camera.position.x = 16 * Math.sin(cameraAngle);
      camera.position.z = 16 * Math.cos(cameraAngle);
      camera.lookAt(new THREE.Vector3(0, 1.8, 0));
      renderer.render(scene, camera);
    };
    loop();

    return () => {
      cancelAnimationFrame(animId);
      renderer.domElement.removeEventListener('click', onClick);
      renderer.dispose();
      if (containerRef.current) containerRef.current.innerHTML = '';
      meshesRef.current = {};
      interactiveListRef.current = [];
    };
  }, [geometrie, onZoneClick]);

  useEffect(() => {
    Object.keys(zonesData || {}).forEach((zone) => {
      const targets = meshesRef.current[zone];
      if (targets) {
        const hexColor = scoreToColor(zonesData[zone].risque);
        targets.forEach(m => (m.material as THREE.MeshBasicMaterial).color.setHex(hexColor));
      }
    });
  }, [zonesData]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', cursor: 'pointer' }} />;
};