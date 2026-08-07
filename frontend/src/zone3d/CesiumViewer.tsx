// =============================================================================
//   TYPHOON — /zone : « Vue terrain 3D » — globe CesiumJS (étape 4, onglet
//   à côté du Jumeau 3D). Chargé à la demande (React.lazy) — le bundle
//   Cesium (~10 Mo) n'est téléchargé qu'au premier clic sur l'onglet.
//
//   · Relief + imagerie : sources publiques (cf. cesiumConfig.ts), repli
//     Cesium ion si VITE_CESIUM_ION_TOKEN est fourni.
//   · Couches de risque : portage direct des WMS/WFS de config.ts (layers.ts),
//     visibilité pilotée par le même `visibleLayerKeys` que l'étape 2.
//   · Bonus cavités : sol semi-transparent quand la couche CAVITE est active
//     (rendu « sous terre » impossible sur la carte OpenLayers).
//   · Cycle de vie : viewer.destroy() au démontage (§11 du plan) — testé avec
//     les bascules d'onglet répétées sur le même écran.
// =============================================================================

/* Note : la feuille de style Widgets/widgets.css est injectée par
   vite-plugin-cesium (transformIndexHtml, dev + build) — pas d'import
   manuel, sinon double chargement (chunk CSS redondant de ~24 Ko). */
import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import * as Cesium from 'cesium';
import type { AleaDetail } from '../zone/config';
import { createBaseImagery, createTerrainProvider, FLY_TO_HEIGHT } from './cesiumConfig';
import { buildHazardLayers, setHazardLayerVisible, type HazardLayer } from './layers';

/** Simulation en cours d'affichage (Sprint 2 — pipeline CZML). */
export interface CesiumSimulation {
  code: string;
  czmlUrl: string;
}

export interface CesiumViewerProps {
  lat: number;
  lon: number;
  codeInsee: string;
  aleas: AleaDetail[];
  visibleLayerKeys: ReadonlySet<string>;
  /** Simulation CZML a charger/animer sur le globe (null = aucune). */
  simulation?: CesiumSimulation | null;
  /** Echec de chargement du CZML (URL invalide, réseau) — remonte a l'UI. */
  onSimulationError?: (code: string, message: string) => void;
  /** Mode « placer une source » : un clic sur le globe appelle
   *  onSourcePicked(lat, lon) au lieu d'interagir avec la caméra. */
  sourceMode?: boolean;
  /** Source manuelle courante (marqueur affiché sur le globe). */
  source?: { lat: number; lon: number } | null;
  onSourcePicked?: (lat: number, lon: number) => void;
  /** URL du .glb du bâtiment diagnostiqué (GET /diagnostic/adresse/gltf) —
   *  posé sur le terrain à l'emplacement réel de l'adresse. null = aucun. */
  buildingUrl?: string | null;
}

export function CesiumViewer({
  lat,
  lon,
  codeInsee,
  aleas,
  visibleLayerKeys,
  simulation = null,
  onSimulationError,
  sourceMode = false,
  source = null,
  onSourcePicked,
  buildingUrl = null,
}: CesiumViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  const layersRef = useRef<HazardLayer[]>([]);
  const simDataSourceRef = useRef<Cesium.CzmlDataSource | null>(null);
  const sourceMarkerRef = useRef<Cesium.Entity | null>(null);
  const buildingEntityRef = useRef<Cesium.Entity | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* onSourcePicked lu en direct dans le handler de clic (pas de stale
     closure — même discipline que visibleRef). */
  const onPickRef = useRef(onSourcePicked);
  onPickRef.current = onSourcePicked;

  /* visibleLayerKeys lu en direct dans les callbacks async (pas de stale closure). */
  const visibleRef = useRef(visibleLayerKeys);
  visibleRef.current = visibleLayerKeys;

  /* ── Création du globe (une seule fois par montage) ── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;

    void (async () => {
      try {
        const baseImagery = await createBaseImagery();

        const viewer = new Cesium.Viewer(container, {
          baseLayer: Cesium.ImageryLayer.fromProviderAsync(Promise.resolve(baseImagery)),

          baseLayerPicker: false,
          geocoder: false,
          homeButton: false,
          sceneModePicker: false,
          navigationHelpButton: false,
          fullscreenButton: false,
          infoBox: false,
          selectionIndicator: false,
          animation: true,
          timeline: true,
        });
        viewerRef.current = viewer;

        /* Accès de debug (dev uniquement) — utilisé par les scripts QA headless
           (scripts/qa_*.mjs) pour sonder l'état du globe sans traverser les
           fibres React. Sans effet en production. */
        if ((import.meta as any).env?.DEV) {
          (window as unknown as Record<string, unknown>).__cesiumViewer = viewer;
        }

        /* Relief : Esri World Elevation3D (ou ion si token) — échec toléré
           → on conserve l'ellipsoïde par défaut. */
        try {
          viewer.terrainProvider = await createTerrainProvider();
        } catch (err) {
          console.warn('[cesium] terrain indisponible — ellipsoïde par défaut :', err);
        }

        /* Vue « recul » sur l'adresse : flyToBoundingSphere cadre le point
           (et non flyTo+orientation, qui pointe vers l'horizon et laisse
           l'adresse hors cadre — la caméra doit VISER le point, pas être
           posée au-dessus). */
        viewer.camera.flyToBoundingSphere(
          new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(lon, lat), 300),
          {
            offset: new Cesium.HeadingPitchRange(
              0,
              Cesium.Math.toRadians(-32),
              FLY_TO_HEIGHT
            ),
            duration: 1.4,
          }
        );

        layersRef.current = await buildHazardLayers(viewer, aleas, codeInsee);
        applyVisibility(viewer, layersRef.current, visibleRef.current);

        if (disposed) {
          if (!viewer.isDestroyed()) viewer.destroy();
          return;
        }
        setReady(true);
      } catch (err) {
        console.error('[cesium] échec d’initialisation du globe :', err);
        if (!disposed) setError('Impossible d’initialiser le globe 3D (WebGL indisponible ?).');
      }
    })();

    /* Nettoyage obligatoire au démontage — évite la fuite mémoire lors des
       bascules d'onglet répétées sur le même écran. StrictMode (dev) peut
       croiser deux initialisations async : la branche `disposed` ci-dessus
       vérifie isDestroyed() avant tout destroy/applyVisibility pour ne
       jamais toucher un viewer déjà détruit. */
    return () => {
      disposed = true;
      const viewer = viewerRef.current;
      viewerRef.current = null;
      layersRef.current = [];
      removeSimulationDataSource(viewer, simDataSourceRef);
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lat, lon, codeInsee]);

  /* ── Toggle œil partagé : visibleLayerKeys → couches Cesium ── */
  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer) applyVisibility(viewer, layersRef.current, visibleLayerKeys);
  }, [visibleLayerKeys]);

  /* ── Mode « placer une source » (interactif) : quand activé, un clic
     gauche sur le globe projette le point en WGS84 et le remonte à l'UI.
     Curseur croix au survol. Le handler est détruit à la sortie du mode. */
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !sourceMode) return;

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    viewer.canvas.style.cursor = 'crosshair';

    handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
      const cartesian = viewer.camera.pickEllipsoid(
        click.position,
        viewer.scene.globe.ellipsoid
      );
      if (!cartesian) return; // clic hors du globe (ciel)
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      onPickRef.current?.(
        Cesium.Math.toDegrees(carto.latitude),
        Cesium.Math.toDegrees(carto.longitude)
      );
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      handler.destroy();
      if (!viewer.isDestroyed()) viewer.canvas.style.cursor = '';
    };
  }, [sourceMode, ready]);

  /* ── Bâtiment diagnostiqué : le .glb du jumeau 3D posé sur le terrain, au
     point réel de l'adresse. Le builder gltf_builder génère le modèle dans
     un repère local (x = Est, z = Sud, hauteur = Y) qui coïncide avec la
     convention glTF par défaut de Cesium (X→Est, Y→haut, Z→Sud) : aucune
     rotation à appliquer — le bâtiment est aligné sur le vrai nord.

     Hauteur : on INJECTE la hauteur du terrain dans la modelMatrix
     (sampleTerrain sur le provider actif, repli 0) au lieu d'utiliser
     heightReference CLAMP_TO_GROUND sur le modèle brut — le support
     HeightReference de Cesium sur un Model + modelMatrix est imprévisible
     quand le terrain n'est pas encore prêt (le bâtiment se retrouve à des
     centaines de mètres d'altitude, donc invisible depuis le sol). Avec la
     hauteur intégrée à la matrice, la base du bâtiment repose exactement
     sur le relief (l'inondation CZML en CLAMP_TO_GROUND pourra « lécher »
     la base du bâtiment).

     Deux couches pour ne JAMAIS laisser la maison invisible :
       · une ancre point + étiquette à l'adresse, toujours présente ;
       · le modèle 3D via Model.fromGltfAsync (promesse explicite) : au
         succès il est ajouté à la scène + zoom « vitrine » sur la maison ;
         à l'échec (réseau/parsing) l'ancre reste — jamais de trou visuel.

     Re-créé quand l'URL change (nouvelle adresse) ; rien à faire si null. */
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !buildingUrl) return;
    let cancelled = false;
    let modelPrimitive: Cesium.Model | null = null;

    const anchorEntity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      point: {
        pixelSize: 9,
        color: Cesium.Color.fromCssColorString('#38bdf8'),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
      label: {
        text: 'Bâtiment diagnostiqué',
        font: '500 12px Roboto, sans-serif',
        pixelOffset: new Cesium.Cartesian2(0, -24),
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 3,
        showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString('#0e1216').withAlpha(0.78),
        backgroundPadding: new Cesium.Cartesian2(8, 5),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 700),
      },
    });
    buildingEntityRef.current = anchorEntity;

    void (async () => {
      /* Hauteur du sol sous le bâtiment (sampleTerrain, repli 0) — voir le
         commentaire d'effet ci-dessus : hauteur dans la matrice, pas de
         heightReference sur le modèle brut. Court délai max (4 s) : si le
         provider n'est pas prêt (réseau lent, terrain en cours), on pose la
         maison au sol 0 plutôt que d'attendre indéfiniment. */
      let groundHeight = 0;
      try {
        const sampled = await Promise.race([
          Cesium.sampleTerrain(viewer.terrainProvider, 12, [
            Cesium.Cartographic.fromDegrees(lon, lat),
          ]),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('sampleTerrain timeout')), 4000)
          ),
        ]);
        if (sampled[0]?.height !== undefined) groundHeight = sampled[0].height;
      } catch (err) {
        console.warn('[cesium] hauteur du terrain indisponible — modèle posé au sol 0 :', err);
      }
      if (cancelled || viewer.isDestroyed()) return;

      const modelMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(
        Cesium.Cartesian3.fromDegrees(lon, lat, groundHeight)
      );

      try {
        const model = await Cesium.Model.fromGltfAsync({
          url: buildingUrl,
          modelMatrix,
          silhouetteColor: Cesium.Color.fromCssColorString('#38bdf8'),
          silhouetteSize: 1.5,
          shadows: Cesium.ShadowMode.ENABLED,
        });
        if (cancelled || viewer.isDestroyed()) {
          model.destroy();
          return;
        }
        viewer.scene.primitives.add(model);
        modelPrimitive = model;
        viewer.shadows = true; // ombre portée de la maison sur le relief

        /* Zoom « vitrine » : on cadre la maison une fois chargée (la vue
           initiale à 2800 m est un recul ; ici on montre le bâtiment).
           flyToBoundingSphere VISE la maison (un flyTo+orientation classique
           la laisserait hors cadre, sous l'horizon). */
        viewer.camera.flyToBoundingSphere(
          new Cesium.BoundingSphere(
            Cesium.Cartesian3.fromDegrees(lon, lat, groundHeight),
            40
          ),
          {
            offset: new Cesium.HeadingPitchRange(
              0,
              Cesium.Math.toRadians(-38),
              560
            ),
            duration: 1.2,
          }
        );
      } catch (err) {
        console.warn('[cesium] modèle du bâtiment indisponible — ancre conservée :', err);
      }
    })();

    return () => {
      cancelled = true;
      buildingEntityRef.current = null;
      if (viewer.isDestroyed()) return;
      viewer.entities.remove(anchorEntity);
      if (modelPrimitive) viewer.scene.primitives.remove(modelPrimitive);
      viewer.shadows = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildingUrl, lat, lon, ready]);

  /* ── Marqueur de la source manuelle (point + étiquette) ── */
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    if (sourceMarkerRef.current) {
      viewer.entities.remove(sourceMarkerRef.current);
      sourceMarkerRef.current = null;
    }
    if (!source) return;

    sourceMarkerRef.current = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(source.lon, source.lat, 25),
      point: {
        pixelSize: 14,
        color: Cesium.Color.fromCssColorString('#38bdf8'),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
      },
      label: {
        text: 'Source d\u2019eau',
        font: '500 12px Roboto, sans-serif',
        pixelOffset: new Cesium.Cartesian2(0, -20),
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 3,
        showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString('#0369a1').withAlpha(0.85),
        backgroundPadding: new Cesium.Cartesian2(8, 5),
      },
    });
  }, [source?.lat, source?.lon]);

  /* ── Simulation CZML (Sprint 2) : charge le document, règle la clock de
     Cesium sur sa plage temporelle et lance la lecture (widget animation /
     timeline natif — play/pause/vitesse fournis par Cesium, pas de UI custom).
     Un changement de simulation remplace la précédente ; null la démonte.

     Dépendances PRIMITIVES (simulation?.code / .czmlUrl) et non l'objet
     `simulation` : ZoneBIM en crée une nouvelle référence à chaque render
     (simForGlobe) — une dépendance objet relancerait l'effet (re-fetch du
     CZML + reset de la clock) à chaque re-render parent (toggle de couche,
     poll…). Même discipline que l'effet d'init (visibleRef). */
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    removeSimulationDataSource(viewer, simDataSourceRef);
    const sim = simulation;
    if (!sim) return;

    let cancelled = false;
    void (async () => {
      try {
        const dataSource = await Cesium.CzmlDataSource.load(sim.czmlUrl);
        if (cancelled || viewer.isDestroyed()) {
          safeDestroyDataSource(dataSource);
          return;
        }

        viewer.dataSources.add(dataSource);
        simDataSourceRef.current = dataSource;

        /* La clock du viewer suit la plage de la simulation (le CZML porte
           son propre interval) ; lecture en boucle, démarrage auto. */
        if (dataSource.clock) {
          viewer.clock.startTime = dataSource.clock.startTime;
          viewer.clock.stopTime = dataSource.clock.stopTime;
          viewer.clock.currentTime = dataSource.clock.startTime;
          viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;
          viewer.clock.shouldAnimate = true;
          viewer.clock.multiplier = dataSource.clock.multiplier || 2;
        }

        /* Cadrer sur l'emprise de la simulation (≈2,2 km autour de l'adresse
           — le raster couvre le SPAN_DEG du moteur). flyToBoundingSphere
           cadre l'adresse (un flyTo+orientation la laisserait hors cadre). */
        viewer.camera.flyToBoundingSphere(
          new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(lon, lat), 600),
          {
            offset: new Cesium.HeadingPitchRange(
              0,
              Cesium.Math.toRadians(-40),
              2400
            ),
            duration: 1.1,
          }
        );
      } catch (err) {
        console.error('[cesium] échec de chargement de la simulation CZML :', err);
        if (!cancelled) onSimulationError?.(sim.code, String(err));
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulation?.code, simulation?.czmlUrl, lat, lon]);

  return (
    <div className="cesium-wrap">
      <div ref={containerRef} className="cesium-canvas" />
      {!ready && !error && (
        <div className="cesium-loading" role="status" aria-live="polite">
          <md-icon>public</md-icon>
          <span>Initialisation du globe 3D…</span>
          <md-linear-progress indeterminate />
        </div>
      )}
      {error && (
        <div className="cesium-error" role="alert">
          <md-icon>error</md-icon>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

/* ── Visibilité des couches + bonus « sous terre » des cavités ── */
export default CesiumViewer;

/* La classe CzmlDataSource de cette version Cesium n'expose pas destroy()/
   isDestroyed() dans ses types (l'interface DataSource n'est pas étendue) —
   le runtime les fournit pourtant : cast typé pour nettoyer sans fuite. */
function safeDestroyDataSource(dataSource: Cesium.CzmlDataSource): void {
  const d = dataSource as unknown as { destroy(): void; isDestroyed(): boolean };
  if (!d.isDestroyed()) d.destroy();
}

/* ── Démonte la source de données de simulation en cours (le cas échéant) ── */
function removeSimulationDataSource(
  viewer: Cesium.Viewer | null,
  ref: MutableRefObject<Cesium.CzmlDataSource | null>
): void {
  const dataSource = ref.current;
  if (!viewer || viewer.isDestroyed() || !dataSource) return;
  try {
    viewer.dataSources.remove(dataSource, true);
  } catch {
    /* déjà détruite */
  }
  ref.current = null;
  viewer.clock.shouldAnimate = false;
}

function applyVisibility(
  viewer: Cesium.Viewer,
  layers: HazardLayer[],
  visibleKeys: ReadonlySet<string>
): void {
  if (viewer.isDestroyed()) return; // course StrictMode : initialisation annulée
  for (const layer of layers) {
    setHazardLayerVisible(layer, visibleKeys.has(layer.code));
  }

  /* Bonus Cesium : quand la couche CAVITE est active, on rend le sol
     semi-transparent pour « voir » les points sous la surface. */
  const globe = viewer.scene.globe;
  const caviteVisible = visibleKeys.has('cavite');
  globe.translucency.enabled = caviteVisible;
  globe.translucency.frontFaceAlpha = caviteVisible ? 0.55 : 1.0;
  globe.translucency.backFaceAlpha = 1.0;
  globe.translucency.frontFaceAlphaByDistance = caviteVisible
    ? new Cesium.NearFarScalar(500, 0.3, 15000, 0.9)
    : new Cesium.NearFarScalar(500, 1.0, 15000, 1.0);
}
