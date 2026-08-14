// =============================================================================
//   TYPHOON — UnifiedMap : carte unique Mapbox GL JS v3 (pas de fallback
//   MapLibre) utilisée par /zone (Cartographie & Analyse).
//   Fond de carte : Mapbox Standard seul, en 2D comme en 3D (éclairage
//   « dusk » + landmarks 3D). Le fond sombre CARTO hérité de MapLibre a été
//   retiré : Mapbox est l'unique moteur de fond de carte.
//   · Bâtiments 3D (BDNB, extrusion par hauteur réelle) + surlignage accent
//     de l'empreinte du bâtiment diagnostiqué (extrusion 3D et teinte 2D)
//   · Couches de risque BRGM (WMS) + WFS Géorisques (step Cartographie)
//   · Parcelles cadastrales IGN (toggle, step Analyse uniquement)
//   · Popup de l'adresse avec les aléas présents (step Cartographie)
//   · Resize différé pour suivre la transition du panneau latéral
//   · (Pas de sélection au clic : on étudie uniquement le bâtiment de
//     l'adresse diagnostiquée — le surlignage suit le rapport.)
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

import {
  API,
  type BdnbBatiment,
  type RisqueReport,
  WMS_LAYER_MAP,
  WFS_LAYER_MAP,
  D03,
  ALEA_ICONS,
  bandForKey,
  escHtml,
} from '../zone/config';
import {
  bboxAround,
  bboxAroundMeters,
  cadastreTileUrl,
  featureContainsPoint,
  firstRing,
  fetchWfsLayer,
  geomToWgs84,
  polygonCenter,
  wmsTileUrl,
} from '../zone/mapHelpers';

// Token + style en variable d'environnement (jamais en dur dans le code).
const MAPBOX_TOKEN: string = (import.meta as any).env?.VITE_MAPBOX_TOKEN || '';
const MAPBOX_STYLE: string =
  (import.meta as any).env?.VITE_MAPBOX_STYLE || 'mapbox://styles/mapbox/standard';
if (MAPBOX_TOKEN) {
  mapboxgl.accessToken = MAPBOX_TOKEN;
}

/* Style Mapbox Standard (GL JS v3) : éclairage « dusk » (coucher de soleil,
 * lumières de la ville) + objets 3D (bâtiments, arbres, landmarks). La config
 * est ignorée par les styles classiques (ex. dark-v11) — sans effet si
 * VITE_MAPBOX_STYLE pointe ailleurs. */
const IS_STANDARD_STYLE = MAPBOX_STYLE.includes('/standard');
const STANDARD_CONFIG = {
  basemap: {
    lightPreset: 'dusk',
    show3dObjects: true,
    show3dLandmarks: true,
  },
};

/* ── IDs de couches ── */
const BUILDINGS_LAYER = 'mb-buildings-3d';
const BUILDINGS_SOURCE = 'mb-bdnb-buildings';
const BUILDINGS_OUTLINE_LAYER = 'mb-buildings-outline';
/* Surlignage 2D du bâtiment diagnostiqué : empreinte teintée accent +
 * contour accent (visible en vue 2D, où l'extrusion 3D est masquée). */
const BUILDINGS_2D_LAYER = 'mb-buildings-2d-highlight';
/* Étiquette flottante du bâtiment cible (P9) — id BDNB tronqué, zoom ≥ 15. */
const TARGET_LABEL_LAYER = 'mb-target-label';
/* Bâtiments 3D natifs Mapbox (source composite/building — tout le bâti OSM,
 * « vibe ville numérique »). Ajoutés sous la couche BDNB. */
const NATIVE_BUILDINGS_LAYER = 'mb-native-buildings';

/* Parcelles cadastrales IGN (WMS data.geopf.fr) — toggle Analyse. */
const CADASTRE_LAYER = 'mb-cadastre';
const CADASTRE_SOURCE = 'mb-cadastre-src';

/* Mode « Bâtiments » (Cities Skylines-style) : rayon autour de l'adresse
 * diagnostiquée dans lequel les bâtiments sont recolorés par métrique —
 * volontairement petit (l'utilisateur ne veut pas « couvrir toute la
 * France », juste le voisinage immédiat). */
const BUILDING_RISK_RADIUS_M = 100;

/* Onglets BDNB (valeur propre au bâtiment, pas une zone Géorisques). */
const BDNB_TAB_META: Record<string, { label: string; icon: string }> = {
  argile: { label: 'Argile', icon: 'grass' },
  radon: { label: 'Radon', icon: 'science' },
  sismique: { label: 'Sismique', icon: 'crisis_alert' },
};

/** Accent courant (--accent sur .zone-app). */
function currentAccent(): string {
  let v = '';
  try {
    const app = document.querySelector('.zone-app');
    v =
      getComputedStyle(app ?? document.documentElement).getPropertyValue('--accent').trim() ||
      getComputedStyle(document.documentElement).getPropertyValue('--orange').trim();
  } catch { /* ignore */ }
  return /^#[0-9a-fA-F]{6}$/.test(v) ? v : '#4386B1';
}

/* ── Props ── */

interface UnifiedMapProps {
  report: RisqueReport | null;
  visibleLayerKeys?: ReadonlySet<string>;
  /** Bâtiment de l'adresse diagnostiquée — surligné. */
  batiment?: BdnbBatiment | null;
  /** Afficher le popup aléas + couches WMS/WFS (étape Cartographie uniquement). */
  showRisks?: boolean;
  /** Afficher le toggle « Parcelles cadastrales » (étape Analyse uniquement). */
  allowParcels?: boolean;
  /** Nombre max de bâtiments chargés par bbox (0 = tous, jusqu'à épuisement).
   *  Cartographie : tous. Analyse : 200 (la carte y est secondaire). */
  buildingsLimit?: number;
  /** 3D au démarrage. */
  initial3D?: boolean;
  fitZoom?: number;
}

/* ── Composant ── */

export function UnifiedMap({
  report,
  visibleLayerKeys = new Set<string>(),
  batiment,
  showRisks = false,
  allowParcels = false,
  buildingsLimit = 200,
  initial3D = true,
  fitZoom = 16.5,
}: UnifiedMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapReadyRef = useRef(false);
  const buildingsSeqRef = useRef(0);
  const buildingsTimerRef = useRef<number | null>(null);
  const resizeTimerRef = useRef<number | null>(null);
  const renderSeqRef = useRef(0);
  const is3dRef = useRef(initial3D);
  const latestReportRef = useRef(report);
  latestReportRef.current = report;
  const batimentRef = useRef(batiment);
  batimentRef.current = batiment;
  const riskModeRef = useRef(false);
  /* Mode « Bâtiments » (Cities Skylines-style) : onglet actif (métrique en
   * cours d'affichage), scores calculés par onglet (batiment_groupe_id →
   * rang D03), bâtiments dans le rayon (avec leurs champs BDNB) et dernière
   * FeatureCollection posée sur BUILDINGS_SOURCE (pour fusionner les scores
   * sans perdre les bâtiments déjà chargés par `loadBuildings`). */
  const activeTabRef = useRef<string | null>(null);
  const scoreMapsRef = useRef<Map<string, Map<string, number>>>(new Map());
  const radiusBuildingsRef = useRef<GeoJSON.Feature[]>([]);
  const buildingsDataRef = useRef<GeoJSON.FeatureCollection | null>(null);
  const visibleKeysRef = useRef(visibleLayerKeys);
  visibleKeysRef.current = visibleLayerKeys;
  const buildingsLimitRef = useRef(buildingsLimit);
  buildingsLimitRef.current = buildingsLimit;
  const layerIdsByKeyRef = useRef<Map<string, string[]>>(new Map());
  const markerRef = useRef<mapboxgl.Marker | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  const pinElRef = useRef<HTMLDivElement | null>(null);
  /* Indicateur du bâtiment cible (épingle accrochée à la géométrie BDNB),
   * visible en 2D comme en 3D. */
  const buildingPinRef = useRef<mapboxgl.Marker | null>(null);
  /* Couches de risque interactives (hover + clic) : layerId → métadonnées
   * d'affichage. Alimenté par renderReport, lu par les handlers mousemove/click
   * posés une seule fois sur la carte. */
  const interactiveLayersRef = useRef<Map<string, { libelle: string; niveau?: string | null; kind: 'vector' | 'circle' }>>(new Map());
  const hoverPopupRef = useRef<mapboxgl.Popup | null>(null);

  const [is3d, setIs3d] = useState(initial3D);
  const [showParcels, setShowParcels] = useState(false);
  /* Mode « Bâtiments » actif (n'importe quel onglet sélectionné) — pilote la
   * visibilité de l'outline/étiquette du bâtiment cible même hors du tab lui-même. */
  const [riskMode, setRiskMode] = useState(false);
  /* Onglet actif du mode « Bâtiments » : argile/radon/sismique (BDNB) ou un
   * aléa Géorisques vectoriel (ppr/canalisations/ssp) — un seul à la fois,
   * comme les vues d'info de Cities Skylines. */
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  /* Éclairage du style Standard : « crépuscule » (dusk, coucher de soleil)
   * par défaut — toggle vers « jour » (day) via setConfigProperty. */
  const [lightPreset, setLightPreset] = useState<'day' | 'dusk'>('dusk');

  function currentBatiment(): BdnbBatiment | null {
    return batimentRef.current ?? latestReportRef.current?.bdnb?.batiment ?? null;
  }

  function highlightId(): string | null | undefined {
    return currentBatiment()?.batiment_groupe_id ?? null;
  }

  /* ── Init carte (une fois) ── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!MAPBOX_TOKEN) {
      setMapError('Token Mapbox manquant — définissez VITE_MAPBOX_TOKEN dans le fichier .env à la racine du projet.');
      return;
    }

    const rep = latestReportRef.current;
    const center: [number, number] = rep ? [rep.lon, rep.lat] : [2.35, 46.8];

    const map = new mapboxgl.Map({
      container,
      style: MAPBOX_STYLE,
      config: STANDARD_CONFIG,
      center,
      zoom: rep ? fitZoom : 5,
      pitch: is3dRef.current ? 55 : 0,
      bearing: is3dRef.current ? -20 : 0,
      antialias: true,
      minZoom: 3,
      maxZoom: 19,
      attributionControl: true,
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');
    mapRef.current = map;

    map.on('error', (e) => {
      // Erreurs de tuiles/sources (WMS BRGM, cadastre…) : non bloquantes.
      // (les champs sourceId/tile/data ne sont typés que sur les anciennes
      // versions — MapboxError de v2 — d'où le cast).
      const legacy = e as unknown as { sourceId?: string; tile?: unknown; data?: unknown; message?: string };
      if (legacy?.sourceId || legacy?.tile || legacy?.data) {
        console.warn('[mapbox] tuile/source:', e.error?.message ?? e);
        return;
      }
      const msg = String(e.error?.message ?? legacy?.message ?? '');
      // « The layer X does not exist in the map's style » : erreur transitoire
      // (race pendant un remount / swap de style) — jamais fatale, sinon le
      // bandeau d'erreur démonte une carte parfaitement fonctionnelle.
      if (/does not exist in the map's style/.test(msg)) {
        console.warn('[mapbox] couche transitoire:', msg);
        return;
      }
      // Seul un échec de chargement du style lui-même est fatal.
      if (/failed to (fetch|load) style|style is not done loading|stylesheet.*(404|error)|networkerror/i.test(msg)) {
        console.warn('[mapbox] erreur:', msg);
        setMapError((prev) => prev ?? 'Chargement du style Mapbox impossible');
        return;
      }
      console.warn('[mapbox] non bloquant:', msg);
    });

    map.on('load', () => {
      mapReadyRef.current = true;
      // Si le style a fini par se charger (retry HMR/dev), on lève le bandeau.
      setMapError(null);
      ensureCadastreLayer(map);
      ensureNativeBuildings(map);
      ensureBuildingsLayer(map);
      updateBuildingsTarget(map);
      placeBuildingPin(map);
      setupRiskLayerInteractions(map);
      void loadBuildings(map);
      if (showRisks) renderReport(map, latestReportRef.current);
    });

    map.on('moveend', () => {
      if (!is3dRef.current) return;
      if (buildingsTimerRef.current) window.clearTimeout(buildingsTimerRef.current);
      buildingsTimerRef.current = window.setTimeout(() => void loadBuildings(map), 500);
    });

    /* Resize différé (panneau latéral) */
    let firstPaint = true;
    const ro = new ResizeObserver(() => {
      const el = containerRef.current;
      if (!el) return;
      if (el.clientWidth === 0 || el.clientHeight === 0) return;
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
      const first = firstPaint;
      firstPaint = false;
      resizeTimerRef.current = window.setTimeout(() => {
        resizeTimerRef.current = null;
        const m = mapRef.current;
        if (!m) return;
        m.resize();
        if (first) void loadBuildings(m);
      }, first ? 60 : 350);
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
      resizeTimerRef.current = null;
      if (buildingsTimerRef.current) window.clearTimeout(buildingsTimerRef.current);
      buildingsTimerRef.current = null;
      mapReadyRef.current = false;
      mapRef.current = null;
      markerRef.current?.remove();
      markerRef.current = null;
      popupRef.current?.remove();
      popupRef.current = null;
      pinElRef.current?.remove();
      pinElRef.current = null;
      buildingPinRef.current?.remove();
      buildingPinRef.current = null;
      hoverPopupRef.current?.remove();
      hoverPopupRef.current = null;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Changement de bâtiment/adresse ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    // Nouvelle adresse : les scores du mode « Bâtiments » (rayon ~100 m)
    // sont calculés pour l'ancien lon/lat, donc invalides.
    scoreMapsRef.current.clear();
    radiusBuildingsRef.current = [];
    updateBuildingsTarget(map);
    placeBuildingPin(map);
    const b = currentBatiment();
    if (b?.geom_groupe) {
      try {
        const wgs = geomToWgs84(b.geom_groupe as Record<string, unknown>);
        const c = polygonCenter(wgs?.coordinates);
        if (c) map.easeTo({ center: c, zoom: fitZoom, pitch: is3dRef.current ? 55 : 0, duration: 900 });
      } catch { /* */ }
    }
    if (is3dRef.current) void loadBuildings(map);
    if (activeTabRef.current) void activateTabColoring(map, activeTabRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batiment, report]);

  /* ── Gros plan (step Cartographie : marqueur + popup + calques aléas) ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    if (showRisks) {
      renderReport(map, report);
    } else {
      // Quitter Cartographie sans ça laissait les couches de zone (fills +
      // extrusions P6) posées sur la carte : `renderReport` ne se relance
      // pas ici, donc rien ne les cachait — elles restaient visibles (et se
      // superposaient) une fois passé en Analyse.
      hideLayersModeLayers(map);
      if (report) placeMarker(map, report);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRisks, report]);

  /* ── visibleLayerKeys → masquer/afficher les couches WMS/WFS ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    applyRiskLayersVisibility(map);
  }, [visibleLayerKeys]);

  /** Applique la visibilité des couches de risque en tenant compte à la fois
   *  du toggle par aléa (`visibleLayerKeys`) et du mode 2D/3D : une couche
   *  `fill` (zone plate) n'est montrée qu'en 2D, son pendant `fill-extrusion`
   *  (P6) qu'en 3D — `line`/`circle`/`raster` restent inchangés par le 2D/3D. */
  function applyRiskLayersVisibility(map: mapboxgl.Map) {
    for (const [key, ids] of layerIdsByKeyRef.current) {
      const keyVisible = visibleKeysRef.current.has(key);
      for (const id of ids) {
        const layer = map.getLayer(id);
        if (!layer) continue;
        let visible = keyVisible;
        if (layer.type === 'fill') visible = keyVisible && !is3dRef.current;
        else if (layer.type === 'fill-extrusion') visible = keyVisible && is3dRef.current;
        map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
      }
    }
  }

  /** Cache toutes les couches de risque « Layers mode » (fills/extrusions
   *  WMS/WFS de `renderReport`), indépendamment de `visibleLayerKeys` —
   *  utilisé en quittant Cartographie et en entrant dans le mode « Bâtiments »
   *  (les deux visualisations ne doivent jamais se superposer en 3D). */
  function hideLayersModeLayers(map: mapboxgl.Map) {
    for (const ids of layerIdsByKeyRef.current.values()) {
      for (const id of ids) {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none');
      }
    }
  }

  /* ═══════════ Couches sources et rendu ═══════════ */

  /** Survol + clic sur les couches de risque (vecteur WFS + cercles fallback) :
   *  posé une fois sur la carte, lit `interactiveLayersRef` (mis à jour à
   *  chaque `renderReport`) pour retrouver libellé/niveau de la feature visée. */
  function setupRiskLayerInteractions(map: mapboxgl.Map) {
    const featureAt = (point: mapboxgl.Point) => {
      const ids = Array.from(interactiveLayersRef.current.keys()).filter((id) => map.getLayer(id));
      if (!ids.length) return null;
      const feats = map.queryRenderedFeatures(point, { layers: ids });
      if (!feats.length) return null;
      const meta = interactiveLayersRef.current.get(String(feats[0].layer?.id));
      return meta ?? null;
    };
    const tooltipHtml = (meta: { libelle: string; niveau?: string | null; kind: 'vector' | 'circle' }) => {
      const band = bandForKey(meta.niveau);
      const label = band?.label ?? meta.niveau ?? '—';
      const note = meta.kind === 'circle' ? ' · présence communale (zone exacte non localisée)' : '';
      return (
        `<div class="mb-hover-title">${escHtml(meta.libelle)}</div>` +
        `<div class="mb-hover-level" style="color:${band?.color ?? '#E8E6DC'}">${escHtml(label)}${escHtml(note)}</div>`
      );
    };
    map.on('mousemove', (e) => {
      const meta = featureAt(e.point);
      map.getCanvas().style.cursor = meta ? 'pointer' : '';
      if (!meta) {
        hoverPopupRef.current?.remove();
        hoverPopupRef.current = null;
        return;
      }
      if (!hoverPopupRef.current) {
        hoverPopupRef.current = new mapboxgl.Popup({
          closeButton: false, closeOnClick: false, offset: 12, className: 'mb-hover-popup',
        });
      }
      hoverPopupRef.current.setLngLat(e.lngLat).setHTML(tooltipHtml(meta)).addTo(map);
    });
    map.on('click', (e) => {
      const meta = featureAt(e.point);
      if (!meta) return;
      new mapboxgl.Popup({ closeButton: true, offset: 12, className: 'mb-hover-popup' })
        .setLngLat(e.lngLat)
        .setHTML(tooltipHtml(meta))
        .addTo(map);
    });
  }

  /** Bâtiments 3D natifs Mapbox : tout le bâti OSM extrudé (hauteurs réelles
   *  OSM, approx.) — remplace le chargement BDNB par viewport pour l'effet
   *  « ville numérique » en vue 3D. Avec le style Standard (GL JS v3) la ville
   *  3D est déjà rendue nativement (avec landmarks) : la couche est superflue. */
  function ensureNativeBuildings(map: mapboxgl.Map) {
    if (IS_STANDARD_STYLE) return;
    if (map.getLayer(NATIVE_BUILDINGS_LAYER)) return;
    map.addLayer({
      id: NATIVE_BUILDINGS_LAYER,
      type: 'fill-extrusion',
      source: 'composite',
      'source-layer': 'building',
      minzoom: 14,
      layout: { visibility: is3dRef.current ? 'visible' : 'none' },
      paint: {
        'fill-extrusion-height': [
          'interpolate', ['linear'], ['zoom'],
          14, 0,
          15.2, ['coalesce', ['get', 'height'], 8],
        ],
        'fill-extrusion-base': [
          'interpolate', ['linear'], ['zoom'],
          14, 0,
          15.2, ['coalesce', ['get', 'min_height'], 0],
        ],
        'fill-extrusion-color': [
          'interpolate', ['linear'], ['coalesce', ['get', 'height'], 8],
          0, '#4a5568', 10, '#6b7c93', 25, '#93a7bf', 45, '#c3d2e2',
        ],
        'fill-extrusion-opacity': 0.9,
        'fill-extrusion-vertical-gradient': true,
      },
    });
  }

  /** Parcelles cadastrales IGN (WMS data.geopf.fr) — toggle Analyse. */
  function ensureCadastreLayer(map: mapboxgl.Map) {
    if (map.getLayer(CADASTRE_LAYER)) return;
    map.addSource(CADASTRE_SOURCE, {
      type: 'raster',
      tiles: [cadastreTileUrl()],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Parcelles © IGN',
    });
    map.addLayer({
      id: CADASTRE_LAYER,
      type: 'raster',
      source: CADASTRE_SOURCE,
      layout: { visibility: 'none' },
      paint: { 'raster-opacity': 1 },
    });
  }

  function ensureBuildingsLayer(map: mapboxgl.Map) {
    if (map.getLayer(BUILDINGS_LAYER)) return;
    map.addSource(BUILDINGS_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    map.addLayer({
      id: BUILDINGS_LAYER,
      type: 'fill-extrusion',
      source: BUILDINGS_SOURCE,
      layout: { visibility: is3dRef.current ? 'visible' : 'none' },
      paint: {
        'fill-extrusion-height': ['case', ['>', ['coalesce', ['get', 'hauteur_mean'], 0], 0], ['get', 'hauteur_mean'], 9],
        'fill-extrusion-base': 0,
        'fill-extrusion-color': buildingColorExpr(highlightId(), currentAccent(), null),
        'fill-extrusion-opacity': 0.95,
        'fill-extrusion-vertical-gradient': true,
      },
    });
    const targetId = highlightId() ?? null;
    map.addLayer({
      id: BUILDINGS_OUTLINE_LAYER,
      type: 'line',
      source: BUILDINGS_SOURCE,
      filter: targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], ''],
      layout: { visibility: is3dRef.current || riskModeRef.current ? 'visible' : 'none' },
      paint: { 'line-color': currentAccent(), 'line-width': 2.5, 'line-opacity': 0.95 },
    });
    /* Surlignage 2D : visible uniquement en vue 2D (l'extrusion fait le
       travail en 3D) — le bâtiment cible reste identifiable en accent, y
       compris en mode « Bâtiments » (qui ne recolore que l'extrusion 3D). */
    map.addLayer({
      id: BUILDINGS_2D_LAYER,
      type: 'fill',
      source: BUILDINGS_SOURCE,
      filter: targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], ''],
      layout: { visibility: is3dRef.current ? 'none' : 'visible' },
      paint: {
        'fill-color': currentAccent(),
        'fill-opacity': 0.4,
        'fill-outline-color': currentAccent(),
      },
    });
    /* Étiquette flottante du bâtiment cible (P9) — id BDNB tronqué, visible
       à partir du zoom 15 (identification même sous des volumes de risque). */
    map.addLayer({
      id: TARGET_LABEL_LAYER,
      type: 'symbol',
      source: BUILDINGS_SOURCE,
      filter: targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], ''],
      minzoom: 15,
      layout: {
        'text-field': ['slice', ['get', 'batiment_groupe_id'], -9],
        'text-size': 11,
        'text-anchor': 'bottom',
        'text-offset': [0, -1.2],
        'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
        'symbol-placement': 'point',
      },
      paint: {
        'text-color': currentAccent(),
        'text-halo-color': 'rgba(10,14,20,0.85)',
        'text-halo-width': 1.2,
      },
    });
  }

  /** Repeint/refiltre les couches bâtiments selon le mode courant :
   *  - mode normal : seul le bâtiment cible est extrudé par la couche BDNB
   *    (le reste de la ville 3D vient des bâtiments natifs Mapbox), en accent ;
   *  - mode « Bâtiments » (`activeTabRef` défini) : plus de filtre — TOUS les
   *    bâtiments chargés s'extrudent, colorés par `risk_score` (gradient) là
   *    où on a un score, sinon la rampe de hauteur neutre habituelle.
   *  Le contour/étiquette du bâtiment cible restent en accent dans les deux
   *  cas — c'est ce qui le garde identifiable même repeint par le gradient. */
  function updateBuildingsTarget(map: mapboxgl.Map) {
    const targetId = highlightId() ?? null;
    const accent = currentAccent();
    const tab = activeTabRef.current;
    const targetFilter: any = targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], ''];
    if (map.getLayer(BUILDINGS_LAYER)) {
      map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-color', buildingColorExpr(targetId, accent, tab ? 'risk_score' : null));
      map.setFilter(BUILDINGS_LAYER, tab ? null : targetFilter);
    }
    if (map.getLayer(BUILDINGS_OUTLINE_LAYER)) {
      map.setFilter(BUILDINGS_OUTLINE_LAYER, targetFilter);
      map.setPaintProperty(BUILDINGS_OUTLINE_LAYER, 'line-color', accent);
      map.setLayoutProperty(BUILDINGS_OUTLINE_LAYER, 'visibility', is3dRef.current || riskModeRef.current ? 'visible' : 'none');
    }
    if (map.getLayer(BUILDINGS_2D_LAYER)) {
      map.setFilter(BUILDINGS_2D_LAYER, targetFilter);
      map.setPaintProperty(BUILDINGS_2D_LAYER, 'fill-color', accent);
      map.setPaintProperty(BUILDINGS_2D_LAYER, 'fill-outline-color', accent);
    }
    if (map.getLayer(TARGET_LABEL_LAYER)) {
      map.setFilter(TARGET_LABEL_LAYER, targetFilter);
      map.setPaintProperty(TARGET_LABEL_LAYER, 'text-color', accent);
    }
  }

  /** Masque les bâtiments 3D natifs (Standard `show3dObjects`, ou la couche
   *  de repli non-Standard) pendant le mode « Bâtiments » — sinon notre
   *  propre extrusion BDNB colorée se superposerait aux volumes gris natifs
   *  sur les mêmes empreintes (double extrusion). Restaurés à la sortie. */
  function suppressNativeBuildings(map: mapboxgl.Map, hide: boolean) {
    if (IS_STANDARD_STYLE) {
      try {
        map.setConfigProperty('basemap', 'show3dObjects', !hide);
      } catch { /* style non chargé/non-Standard : sans effet */ }
    }
    if (map.getLayer(NATIVE_BUILDINGS_LAYER)) {
      map.setLayoutProperty(NATIVE_BUILDINGS_LAYER, 'visibility', hide ? 'none' : (is3dRef.current ? 'visible' : 'none'));
    }
  }

  /* ── Rendu Cartographie : marqueur + popup + calques aléas WMS/WFS ── */

  function renderReport(map: mapboxgl.Map, rep: RisqueReport | null) {
    /* Nettoyage des couches de risque précédentes — toutes les couches
     * d'abord (fill + outline peuvent partager une même source), puis les
     * sources : `removeSource` échoue tant qu'une couche la référence. */
    for (const ids of layerIdsByKeyRef.current.values()) {
      for (const id of ids) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
    }
    for (const ids of layerIdsByKeyRef.current.values()) {
      for (const id of ids) {
        if (map.getSource(`src-${id}`)) map.removeSource(`src-${id}`);
      }
    }
    layerIdsByKeyRef.current.clear();
    interactiveLayersRef.current.clear();
    const seq = ++renderSeqRef.current;

    placeMarker(map, rep);
    popupRef.current?.remove();
    popupRef.current = null;

    if (!rep) return;

    const aleaRows = (rep.aleas || [])
      .filter((a) => a.present === true && a.niveau)
      .map((a) => {
        const band = bandForKey(a.niveau);
        const color = band?.color ?? '#8A8984';
        const label = band?.label ?? a.niveau ?? '';
        const icon = ALEA_ICONS[a.code] ?? 'crisis_alert';
        return (
          `<div class="mb-risk-row">` +
          `<md-icon aria-hidden="true">${icon}</md-icon>` +
          `<span class="mb-risk-name">${escHtml(a.libelle)}</span>` +
          `<span class="mb-risk-pill" style="--risk-color:${color}">${escHtml(label)}</span>` +
          `</div>`
        );
      })
      .join('');

    /* Indicateur d'adresse compact : en-tête adresse + aléas présents en
       pastilles de niveau colorées (pas de gros popup ni de liens externes —
       la carte et le panneau latéral restent les interactions principales). */
    popupRef.current = new mapboxgl.Popup({ offset: 22, closeButton: true, maxWidth: '300px', className: 'mb-risk-popup' })
      .setLngLat([rep.lon, rep.lat])
      .setHTML(
        `<div class="mb-risk-head">` +
        `<md-icon aria-hidden="true">pin_drop</md-icon>` +
        `<span class="mb-risk-addr">${escHtml(rep.adresse_normalisee)}</span>` +
        `</div>` +
        `<div class="mb-risk-rows">` +
        (aleaRows ||
          `<div class="mb-risk-row"><span class="mb-risk-name">Aucun aléa présent</span><span class="mb-risk-pill">—</span></div>`) +
        `</div>`
      )
      .addTo(map);

    map.easeTo({ center: [rep.lon, rep.lat], zoom: fitZoom, duration: 1200 });

    /* Surbrillance du bâtiment diagnostiqué */
    updateBuildingsTarget(map);

    /* Couches WMS + WFS. Le vecteur (WFS) prime sur le raster (WMS) dès que
     * la donnée existe pour l'aléa (principe #4 de la doc) : plusieurs
     * FeatureType peuvent composer un même aléa (ex. ppr agrège 8 couches de
     * périmètres) — on les fusionne en une seule source. Le raster reste le
     * repli si le vecteur ne renvoie aucune feature dans la bbox. */
    const bbox = bboxAround(rep.lon, rep.lat);
    const beforeId = map.getLayer(BUILDINGS_LAYER) ? BUILDINGS_LAYER : undefined;
    const renderLayers = async () => {
      for (const a of rep.aleas || []) {
        if (seq !== renderSeqRef.current) return;
        const band = a.niveau ? bandForKey(a.niveau) : undefined;
        const color = band?.color || '#7A9187';
        const visible = visibleKeysRef.current.has(a.code);
        const layerId = `alea-${a.code}`;
        const sourceId = `src-${layerId}`;
        const track = (id: string) => {
          if (!layerIdsByKeyRef.current.has(a.code)) layerIdsByKeyRef.current.set(a.code, []);
          layerIdsByKeyRef.current.get(a.code)!.push(id);
        };

        let wfsRendered = false;
        if (WFS_LAYER_MAP[a.code]) {
          const merged: GeoJSON.Feature[] = [];
          for (const typeName of WFS_LAYER_MAP[a.code]) {
            try {
              const geojson = await fetchWfsLayer(typeName, bbox);
              if (seq !== renderSeqRef.current) return;
              if (geojson?.features?.length) merged.push(...geojson.features);
            } catch { /* couche suivante */ }
          }
          if (merged.length) {
            const data = withNiveauProp({ type: 'FeatureCollection', features: merged }, a.niveau);
            map.addSource(sourceId, { type: 'geojson', data });
            const fillVisible = visible && !is3dRef.current;
            const extrusionVisible = visible && is3dRef.current;
            map.addLayer({
              id: layerId, type: 'fill', source: sourceId,
              layout: { visibility: fillVisible ? 'visible' : 'none' },
              paint: {
                'fill-color': d03ColorExpr(color),
                'fill-opacity': 0.5,
                'fill-outline-color': '#263238',
              },
            }, beforeId);
            const outlineId = `${layerId}-outline`;
            map.addLayer({
              id: outlineId, type: 'line', source: sourceId,
              layout: { visibility: visible ? 'visible' : 'none' },
              paint: {
                'line-color': d03ColorExpr(color),
                'line-width': d03LineWidthExpr(),
                'line-opacity': 0.6,
              },
            }, beforeId);
            /* Extrusion 3D (P6) : les zones de risque deviennent des volumes
             * qu'on survole — hauteur codée sur le niveau D03, plafonnée pour
             * rester lisible face aux bâtiments. Passe sous BUILDINGS_LAYER
             * (before:) pour ne jamais masquer le surlignage du bâtiment cible. */
            const extrusionId = `${layerId}-extrusion`;
            map.addLayer({
              id: extrusionId, type: 'fill-extrusion', source: sourceId,
              layout: { visibility: extrusionVisible ? 'visible' : 'none' },
              paint: {
                'fill-extrusion-height': d03HeightExpr(),
                'fill-extrusion-base': 0,
                'fill-extrusion-color': d03ColorExpr(color),
                'fill-extrusion-opacity': 0.55,
                'fill-extrusion-vertical-gradient': false,
              },
            }, beforeId);
            track(layerId);
            track(outlineId);
            track(extrusionId);
            interactiveLayersRef.current.set(layerId, { libelle: a.libelle, niveau: a.niveau, kind: 'vector' });
            interactiveLayersRef.current.set(extrusionId, { libelle: a.libelle, niveau: a.niveau, kind: 'vector' });
            wfsRendered = true;
          }
        }
        if (wfsRendered) continue;

        if (WMS_LAYER_MAP[a.code]) {
          map.addSource(sourceId, { type: 'raster', tiles: [wmsTileUrl(WMS_LAYER_MAP[a.code])], tileSize: 256, maxzoom: 19 });
          map.addLayer({ id: layerId, type: 'raster', source: sourceId, layout: { visibility: visible ? 'visible' : 'none' }, paint: { 'raster-opacity': 0.65 } });
          track(layerId);
          continue;
        }

        /* Fallback : cercle ponctuel — marque une présence communale, pas la
         * zone exacte du risque (cf. tooltip au survol). */
        map.addSource(sourceId, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [rep.lon, rep.lat] }, properties: {} }] },
        });
        let circle: any = { 'circle-radius': 10, 'circle-color': color, 'circle-opacity': 0.65 };
        if (a.niveau && D03.find((d) => d.key === a.niveau)) {
          circle['circle-stroke-color'] = color;
          circle['circle-stroke-width'] = a.niveau === 'critique' ? 3 : 1;
        }
        map.addLayer({ id: layerId, type: 'circle', source: sourceId, layout: { visibility: visible ? 'visible' : 'none' }, paint: circle });
        track(layerId);
        interactiveLayersRef.current.set(layerId, { libelle: a.libelle, niveau: a.niveau, kind: 'circle' });
      }
    };
    void renderLayers();
  }

  /* ── Marqueur ── */

  function placeMarker(map: mapboxgl.Map, rep: RisqueReport | null) {
    markerRef.current?.remove();
    markerRef.current = null;
    if (!rep) return;
    const el = document.createElement('div');
    el.className = 'map-pin';
    el.innerHTML = '<span class="map-pin-dot"></span><span class="map-pin-stem"></span>';
    markerRef.current = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, 0] })
      .setLngLat([rep.lon, rep.lat])
      .addTo(map);
  }

  /** Épingle « bâtiment cible » : accrochée au centre de l'empreinte BDNB
   *  (géométrie réelle), visible en 2D comme en 3D. Le surlignage accent
   *  de la couche BDNB fait le reste en 3D. */
  function placeBuildingPin(map: mapboxgl.Map) {
    buildingPinRef.current?.remove();
    buildingPinRef.current = null;
    const b = currentBatiment();
    if (!b?.geom_groupe) return;
    try {
      const wgs = geomToWgs84(b.geom_groupe as Record<string, unknown>);
      const c = polygonCenter(wgs?.coordinates);
      if (!c) return;
      const el = document.createElement('div');
      el.className = 'bldg-pin';
      el.innerHTML = '<span class="bldg-pin-dot"></span>';
      buildingPinRef.current = new mapboxgl.Marker({ element: el, anchor: 'bottom', offset: [0, 0] })
        .setLngLat([c[0], c[1]])
        .addTo(map);
    } catch { /* */ }
  }

  async function loadBuildings(map: mapboxgl.Map) {
    let west = 0, south = 0, east = 0, north = 0;
    try {
      const bounds = map.getBounds();
      if (!bounds) return; // type v3 : LngLatBounds | null
      west = bounds.getWest(); south = bounds.getSouth(); east = bounds.getEast(); north = bounds.getNorth();
      if (!isFinite(west) || !isFinite(east)) return;
    } catch { return; }
    const seq = ++buildingsSeqRef.current;
    const url = `${API}/diagnostic/zone/buildings?west=${west}&south=${south}&east=${east}&north=${north}&limit=${buildingsLimitRef.current}`;
    try {
      const resp = await fetch(url);
      if (seq !== buildingsSeqRef.current || !mapRef.current) return;
      if (!resp.ok) return;
      const fc = (await resp.json()) as GeoJSON.FeatureCollection;
      if (seq !== buildingsSeqRef.current) return;
      ensureBuildingsLayer(map);
      const b = currentBatiment();
      const targetId = b?.batiment_groupe_id;
      if (targetId) {
        const targetInFc = fc.features.some((f) => f.properties?.batiment_groupe_id === targetId);
        if (b && !targetInFc && b.geom_groupe) {
          const wgsGeom = geomToWgs84(b.geom_groupe as Record<string, unknown>);
          if (wgsGeom) fc.features.push({ type: 'Feature', geometry: wgsGeom as unknown as GeoJSON.Geometry, properties: { batiment_groupe_id: b.batiment_groupe_id, hauteur_mean: b.hauteur_mean || 10 } });
        }
      }
      // Si le mode « Bâtiments » est actif, ré-applique les scores déjà
      // calculés (cf. `scoreMapsRef`) aux bâtiments qui viennent d'entrer
      // dans le viewport (pan/zoom) — pas de nouvel appel réseau.
      const merged = activeTabRef.current ? mergeScoresIntoFc(fc, activeTabRef.current) : fc;
      buildingsDataRef.current = merged;
      (map.getSource(BUILDINGS_SOURCE) as mapboxgl.GeoJSONSource)?.setData(merged);
    } catch { /* */ }
  }

  function toggle3D(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    is3dRef.current = enabled; setIs3d(enabled);
    if (map.getLayer(BUILDINGS_LAYER)) map.setLayoutProperty(BUILDINGS_LAYER, 'visibility', enabled ? 'visible' : 'none');
    suppressNativeBuildings(map, !!activeTabRef.current);
    if (map.getLayer(BUILDINGS_2D_LAYER)) {
      map.setLayoutProperty(BUILDINGS_2D_LAYER, 'visibility', enabled ? 'none' : 'visible');
    }
    // Outline (visible en 3D, ou en 2D si riskMode actif) + filtre BDNB → bâtiment cible.
    updateBuildingsTarget(map);
    // Couches de risque : bascule fill (2D) ↔ fill-extrusion (3D, P6).
    applyRiskLayersVisibility(map);
    map.easeTo({ pitch: enabled ? 55 : 0, duration: 800 });
    if (enabled) void loadBuildings(map);
  }

  function toggleParcels(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    setShowParcels(enabled);
    if (map.getLayer(CADASTRE_LAYER)) {
      map.setLayoutProperty(CADASTRE_LAYER, 'visibility', enabled ? 'visible' : 'none');
    }
  }

  /** Fusionne un score numérique (`risk_score`, rang D03 0-5) dans les
   *  features qui ont une entrée dans `scoreMapsRef.get(tab)` — les autres
   *  restent inchangées (pas de propriété `risk_score`, donc repli sur la
   *  rampe de hauteur neutre dans `buildingColorExpr`). */
  function mergeScoresIntoFc(fc: GeoJSON.FeatureCollection, tab: string | null): GeoJSON.FeatureCollection {
    if (!tab) return fc;
    const scoreMap = scoreMapsRef.current.get(tab);
    if (!scoreMap) return fc;
    return {
      ...fc,
      features: fc.features.map((f) => {
        const id = f.properties?.batiment_groupe_id;
        const score = id ? scoreMap.get(id) : undefined;
        if (score === undefined) return f;
        return { ...f, properties: { ...(f.properties || {}), risk_score: score } };
      }),
    };
  }

  /** Union de deux listes de features par `batiment_groupe_id` — garantit
   *  que les bâtiments du rayon ~100 m (mode « Bâtiments ») sont bien dans
   *  la source même si le viewport courant est plus étroit que le rayon. */
  function unionFeatures(base: GeoJSON.Feature[], extra: GeoJSON.Feature[]): GeoJSON.Feature[] {
    const seen = new Set(base.map((f) => f.properties?.batiment_groupe_id).filter(Boolean));
    const additional = extra.filter((f) => {
      const id = f.properties?.batiment_groupe_id;
      return id && !seen.has(id);
    });
    return [...base, ...additional];
  }

  /** Calcule les scores (batiment_groupe_id → rang D03) d'un onglet du mode
   *  « Bâtiments », pour tous les bâtiments dans un rayon `BUILDING_RISK_RADIUS_M`
   *  autour de l'adresse :
   *  - onglets BDNB (argile/radon/sismique) : valeur propre au bâtiment,
   *    récupérée en un seul appel groupé (`with_risks=true`, cf. backend) ;
   *  - onglets Géorisques vectoriels (ppr/canalisations/ssp) : le bâtiment
   *    est dans la zone si son centre tombe dans un polygone de la couche
   *    WFS de l'aléa (même rayon), score = rang du niveau D03 du rapport,
   *    sinon 0 (hors zone = réellement plus sûr pour CET aléa, pas
   *    « donnée manquante » — reste honnête, cf. doc de conception). */
  async function computeScoresForTab(map: mapboxgl.Map, rep: RisqueReport, tab: string): Promise<void> {
    const [west, south, east, north] = bboxAroundMeters(rep.lon, rep.lat, BUILDING_RISK_RADIUS_M);
    let radiusFeatures: GeoJSON.Feature[] = [];
    try {
      const resp = await fetch(
        `${API}/diagnostic/zone/buildings?west=${west}&south=${south}&east=${east}&north=${north}&limit=0&with_risks=true`
      );
      if (resp.ok) {
        const fc = (await resp.json()) as GeoJSON.FeatureCollection;
        radiusFeatures = fc.features || [];
      }
    } catch { /* best-effort : scoreMap restera vide, tous les bâtiments gardent la rampe neutre */ }
    radiusBuildingsRef.current = radiusFeatures;

    const scoreMap = new Map<string, number>();
    if (BDNB_TAB_META[tab]) {
      for (const f of radiusFeatures) {
        const id = f.properties?.batiment_groupe_id;
        if (!id) continue;
        const norm = normalizeRiskLevel(f.properties?.[`alea_${tab}`]);
        scoreMap.set(id, norm ? RISK_LEVEL_RANK[norm] : 0);
      }
    } else if (WFS_LAYER_MAP[tab]) {
      const alea = rep.aleas?.find((a) => a.code === tab);
      const rank = alea?.niveau ? (RISK_LEVEL_RANK[alea.niveau] ?? 0) : 0;
      const zoneFeatures: GeoJSON.Feature[] = [];
      for (const typeName of WFS_LAYER_MAP[tab]) {
        try {
          const fcz = await fetchWfsLayer(typeName, [west, south, east, north]);
          if (fcz?.features?.length) zoneFeatures.push(...fcz.features);
        } catch { /* type suivant */ }
      }
      for (const f of radiusFeatures) {
        const id = f.properties?.batiment_groupe_id;
        if (!id || !f.geometry) continue;
        const center = polygonCenter((f.geometry as { coordinates: unknown }).coordinates);
        const inside = center ? zoneFeatures.some((zf) => featureContainsPoint(zf, center)) : false;
        scoreMap.set(id, inside ? rank : 0);
      }
    }
    scoreMapsRef.current.set(tab, scoreMap);
  }

  /** Calcule (si pas déjà en cache) puis applique les scores d'un onglet à
   *  la couche bâtiments — fusionne avec ce qui est déjà chargé (viewport +
   *  rayon), pose les données, et laisse `updateBuildingsTarget` repeindre. */
  async function activateTabColoring(map: mapboxgl.Map, tab: string): Promise<void> {
    const rep = latestReportRef.current;
    if (!rep) return;
    if (!scoreMapsRef.current.has(tab)) {
      await computeScoresForTab(map, rep, tab);
    }
    if (activeTabRef.current !== tab || !mapRef.current) return; // superseded entre-temps
    const src = map.getSource(BUILDINGS_SOURCE) as mapboxgl.GeoJSONSource | undefined;
    if (!src) return;
    const base = buildingsDataRef.current ?? { type: 'FeatureCollection' as const, features: [] };
    const unioned = unionFeatures(base.features, radiusBuildingsRef.current);
    const merged = mergeScoresIntoFc({ type: 'FeatureCollection', features: unioned }, tab);
    buildingsDataRef.current = merged;
    src.setData(merged);
    updateBuildingsTarget(map);
  }

  /** Bascule l'onglet du mode « Bâtiments » (Cities Skylines-style) : un
   *  onglet à la fois — cliquer sur l'onglet actif désactive le mode. */
  function toggleTab(tab: string) {
    const map = mapRef.current;
    if (!map) return;
    const next = activeTabRef.current === tab ? null : tab;
    activeTabRef.current = next;
    setActiveTab(next);
    riskModeRef.current = !!next;
    setRiskMode(!!next);
    suppressNativeBuildings(map, !!next);
    if (!next) {
      updateBuildingsTarget(map);
      return;
    }
    // Les deux visualisations (zones Layers mode / bâtiments colorés) ne
    // doivent jamais se superposer en 3D.
    hideLayersModeLayers(map);
    if (!is3dRef.current) toggle3D(true);
    void activateTabColoring(map, next);
  }

  /** Toggle éclairage du style Standard : crépuscule (dusk) ↔ jour (day). */
  function toggleLight() {
    const map = mapRef.current;
    if (!map || !IS_STANDARD_STYLE) return;
    const next = lightPreset === 'dusk' ? 'day' : 'dusk';
    try {
      map.setConfigProperty('basemap', 'lightPreset', next);
      setLightPreset(next);
    } catch {
      // Style non-Standard : la config est ignorée, rien à faire.
    }
  }

  const activeAleas = showRisks
    ? (report?.aleas || []).filter((a) => a.present === true && a.niveau && visibleLayerKeys.has(a.code))
    : [];
  const activeBandKeys = Array.from(new Set(activeAleas.map((a) => a.niveau as string)));
  const activeBands = D03.filter((b) => activeBandKeys.includes(b.key));

  /* Onglets du mode « Bâtiments » (Cities Skylines-style) : les 3 champs
     BDNB toujours proposés, plus un onglet par aléa Géorisques vectoriel
     réellement présent sur ce rapport (ppr/canalisations/ssp aujourd'hui —
     cf. WFS_LAYER_MAP). Analyse uniquement (`allowParcels`). */
  const riskTabs = allowParcels
    ? [
        ...Object.entries(BDNB_TAB_META).map(([key, meta]) => ({ key, ...meta })),
        ...(report?.aleas || [])
          .filter((a) => a.present === true && WFS_LAYER_MAP[a.code])
          .map((a) => ({ key: a.code, label: a.libelle, icon: ALEA_ICONS[a.code] ?? 'warning' })),
      ]
    : [];
  const activeTabMeta = riskTabs.find((t) => t.key === activeTab);

  return (
    <div className="mb-demo-wrap">
      {mapError ? (
        <div className="mb-demo-error"><md-icon>error</md-icon><p>{mapError}</p></div>
      ) : (
        <div ref={containerRef} className="mb-demo-map" />
      )}
      {!mapError && activeAleas.length > 0 && (
        <div className="mb-map-legend" role="group" aria-label="Légende des risques affichés">
          <div className="mb-map-legend-head">
            <md-icon>layers</md-icon>
            <span>{activeAleas.length} couche{activeAleas.length > 1 ? 's' : ''} active{activeAleas.length > 1 ? 's' : ''}</span>
          </div>
          <div className="mb-map-legend-bands">
            {activeBands.map((b) => (
              <div className="mb-map-legend-row" key={b.key}>
                <span className="mb-map-legend-dot" style={{ background: b.color }} />
                <span>{b.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!mapError && activeTab && (
        <div className="mb-map-legend mb-map-legend-risk" role="group" aria-label="Légende de la coloration des bâtiments">
          <div className="mb-map-legend-head">
            <md-icon>gradient</md-icon>
            <span>{activeTabMeta?.label ?? activeTab} — bâtiments à ~{BUILDING_RISK_RADIUS_M} m</span>
          </div>
          <div className="mb-map-legend-bands">
            {D03.map((b) => (
              <div className="mb-map-legend-row" key={b.key}>
                <span className="mb-map-legend-dot" style={{ background: b.color }} />
                <span>{b.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!mapError && riskTabs.length > 0 && (
        <div className="mb-risk-tabs" role="group" aria-label="Mode de coloration des bâtiments">
          {riskTabs.map((t) => (
            <button key={t.key} type="button"
              className={`map-3d-toggle analyse${activeTab === t.key ? ' active' : ''}`}
              onClick={() => toggleTab(t.key)} aria-pressed={activeTab === t.key}
              title={`Colorer les bâtiments (~${BUILDING_RISK_RADIUS_M} m) par ${t.label}`}
              aria-label={`Colorer les bâtiments par ${t.label}`}>
              <md-icon>{t.icon}</md-icon>
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      )}
      {!mapError && (
        <div className="mb-demo-tools" role="group" aria-label="Options de la carte">
          {allowParcels && (
            <button type="button"
              className={`map-3d-toggle analyse${showParcels ? ' active' : ''}`}
              onClick={() => toggleParcels(!showParcels)} aria-pressed={showParcels}
              title={showParcels ? 'Masquer les parcelles cadastrales (IGN)' : 'Afficher les parcelles cadastrales (IGN)'}
              aria-label={showParcels ? 'Masquer les parcelles cadastrales' : 'Afficher les parcelles cadastrales'}>
              <md-icon>grid_on</md-icon>
              <span>Parcelles</span>
            </button>
          )}
          <button type="button"
            className={`map-3d-toggle analyse${is3d ? ' active' : ''}`}
            onClick={() => toggle3D(!is3d)} aria-pressed={is3d}
            title={is3d ? 'Revenir à la vue 2D' : 'Passer en vue 3D (bâtiments extrudés BDNB)'}
            aria-label={is3d ? 'Revenir à la vue 2D' : 'Passer en vue 3D'}>
            <md-icon>view_in_ar</md-icon>
            <span>{is3d ? '2D' : '3D'}</span>
          </button>
          {IS_STANDARD_STYLE && (
            <button type="button"
              className={`map-3d-toggle analyse${lightPreset === 'dusk' ? ' active' : ''}`}
              onClick={toggleLight} aria-pressed={lightPreset === 'dusk'}
              title={lightPreset === 'dusk'
                ? 'Passer en mode jour (éclairage standard)'
                : 'Passer en mode crépuscule (coucher de soleil)'}
              aria-label={lightPreset === 'dusk' ? 'Passer en mode jour' : 'Passer en mode crépuscule'}>
              <md-icon>{lightPreset === 'dusk' ? 'light_mode' : 'wb_twilight'}</md-icon>
              <span>{lightPreset === 'dusk' ? 'Jour' : 'Crépuscule'}</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Couleur/épaisseur par bande D03 (couches de risque vecteur) ── */
/** `fill-color`/`line-color` par bande D03 (propriété `niveau` injectée au
 *  fetch, cf. `withNiveauProp`) — repli sur `fallback` si le niveau est
 *  absent/inconnu. */
function d03ColorExpr(fallback: string): any {
  const stops: any[] = [];
  for (const b of D03) stops.push(b.key, b.color);
  return ['match', ['coalesce', ['get', 'niveau'], ''], ...stops, fallback];
}
/** Contour plus épais aux niveaux élevés — hiérarchie visuelle du risque. */
function d03LineWidthExpr(): any {
  return ['match', ['coalesce', ['get', 'niveau'], ''], 'critique', 3, 'eleve', 2, 1.2];
}
/** Hauteur d'extrusion 3D (P6) par bande D03 — la carte « se soulève » là où
 *  le risque est fort ; plafonnée à 14 m pour rester lisible face au bâti. */
function d03HeightExpr(): any {
  return ['match', ['coalesce', ['get', 'niveau'], ''],
    'critique', 14, 'eleve', 10, 'modere', 6, 'faible', 3, 'tres_faible', 1.5, 1];
}
/** Injecte le niveau D03 de l'aléa dans chaque feature (le WFS Géorisques ne
 *  porte pas ce champ) pour permettre le coloriage par `d03ColorExpr`. */
function withNiveauProp(fc: GeoJSON.FeatureCollection, niveau: string | null | undefined): GeoJSON.FeatureCollection {
  return {
    ...fc,
    features: fc.features.map((f) => ({ ...f, properties: { ...(f.properties || {}), niveau } })),
  };
}

/* ── Couleur des volumes extrudés ── */
/** Couleur `fill-extrusion-color` des bâtiments :
 *  - `riskScoreProp` défini (mode « Bâtiments ») : dégradé vert→rouge
 *    (`gradientColorExpr`) pour les bâtiments qui portent cette propriété
 *    (dans le rayon ~100 m, cf. `mergeScoresIntoFc`), rampe de hauteur
 *    neutre sinon — pas de surlignage spécial du bâtiment cible, il est
 *    noté par son contour/étiquette (toujours accent), pas par son fill ;
 *  - sinon (mode normal) : accent pour le bâtiment cible, rampe sinon. */
function buildingColorExpr(targetId: string | null | undefined, accent: string, riskScoreProp: string | null): any {
  const ramp: any = ['interpolate', ['linear'], ['coalesce', ['get', 'hauteur_mean'], 0],
    0, '#4f607a', 6, '#778ca8', 12, '#a3b7cc', 20, '#c7d8e6', 32, '#eef4fa'];
  if (riskScoreProp) {
    return ['case', ['has', riskScoreProp], gradientColorExpr(riskScoreProp), ramp];
  }
  return targetId ? ['case', ['==', ['get', 'batiment_groupe_id'], targetId], accent, ramp] : ramp;
}

/** Dégradé continu vert→rouge (façon Cities Skylines) sur les 5 couleurs
 *  D03 existantes — un `interpolate` (lissé) plutôt qu'un `match` (à plat)
 *  pour le rendu « carte de chaleur » demandé, tout en restant ancré sur la
 *  palette de risque déjà utilisée partout ailleurs dans l'app. Rang 0
 *  (bâtiment évalué, hors zone / valeur nulle) est traité comme le rang 1
 *  (très faible) — les deux signifient « pas de risque particulier ici ». */
function gradientColorExpr(prop: string): any {
  return ['interpolate', ['linear'], ['get', prop],
    0, D03[0].color,
    1, D03[0].color,
    2, D03[1].color,
    3, D03[2].color,
    4, D03[3].color,
    5, D03[4].color,
  ];
}

/* ── Mode « Bâtiments » (Cities Skylines-style) ── */
/** Normalise un niveau de risque bâtiment BDNB (vocabulaire libre — « nul »,
 *  « faible », « moyen », « fort », ou un code de zone 1-5 selon le champ)
 *  vers une clé de bande D03. Repli `null` (pas de couleur) si non reconnu —
 *  préférable à une couleur trompeuse sur un vocabulaire non confirmé. */
function normalizeRiskLevel(raw?: string | null): string | null {
  if (!raw) return null;
  const v = raw.toString().trim().toLowerCase();
  if (/^(nul|nulle|none|aucun|0)$/.test(v)) return null;
  if (/tr[eè]s.?faible|^1$/.test(v)) return 'tres_faible';
  if (/faible|^2$/.test(v)) return 'faible';
  if (/mod[eé]r[eé]|moyen|^3$/.test(v)) return 'modere';
  if (/[eé]lev[eé]|^4$/.test(v)) return 'eleve';
  if (/fort|critique|^5$/.test(v)) return 'critique';
  return null;
}

/** Rang D03 (1 très faible → 5 critique) — score numérique injecté dans
 *  `risk_score` pour piloter `gradientColorExpr`, et utilisé pour comparer
 *  les niveaux D03 des aléas Géorisques vectoriels (cf. `computeScoresForTab`). */
const RISK_LEVEL_RANK: Record<string, number> = {
  tres_faible: 1, faible: 2, modere: 3, eleve: 4, critique: 5,
};