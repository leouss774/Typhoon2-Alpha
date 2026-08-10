// =============================================================================
//   TYPHOON — Carte unique Mapbox GL JS (pas de fallback MapLibre)
//   Fond de carte : Mapbox (style personnalisé sombre) ; en vue 2D, le fond
//   sombre CARTO d'origine MapLibre est réutilisé (tuiles identiques à
//   l'ancienne carte).
//   · Bâtiments 3D (BDNB, extrusion par hauteur réelle)
//   · Couches de risque BRGM (WMS) + WFS Géorisques (step Cartographie)
//   · Parcelles cadastrales IGN (toggle, step Analyse uniquement)
//   · Popup de l'adresse avec les aléas présents (step Cartographie)
//   · Sélection au clic → surlignage + fiche (story A2)
//   · Resize différé pour suivre la transition du panneau latéral
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
  bandForKey,
  escHtml,
} from '../zone/config';
import {
  cadastreTileUrl,
  firstRing,
  fetchWfsLayer,
  geomToWgs84,
  polygonCenter,
  wmsTileUrl,
} from '../zone/mapHelpers';

// Token + style en variable d'environnement (jamais en dur dans le code).
const MAPBOX_TOKEN: string = (import.meta as any).env?.VITE_MAPBOX_TOKEN || '';
const MAPBOX_STYLE: string =
  (import.meta as any).env?.VITE_MAPBOX_STYLE || 'mapbox://styles/mapbox/dark-v11';
if (MAPBOX_TOKEN) {
  mapboxgl.accessToken = MAPBOX_TOKEN;
}

/* ── IDs de couches ── */
const BUILDINGS_LAYER = 'mb-buildings-3d';
const BUILDINGS_SOURCE = 'mb-bdnb-buildings';
const BUILDINGS_OUTLINE_LAYER = 'mb-buildings-outline';
/* Bâtiments 3D natifs Mapbox (source composite/building — tout le bâti OSM,
 * « vibe ville numérique »). Ajoutés sous la couche BDNB. */
const NATIVE_BUILDINGS_LAYER = 'mb-native-buildings';

/* Fond sombre 2D — tuiles CARTO dark de l'ancienne carte MapLibre. */
const CARTO_DARK_LAYER = 'mb-carto-dark';
const CARTO_DARK_SOURCE = 'mb-carto-dark-src';
const CARTO_DARK_TILES = 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png';

/* Parcelles cadastrales IGN (WMS data.geopf.fr) — toggle Analyse. */
const CADASTRE_LAYER = 'mb-cadastre';
const CADASTRE_SOURCE = 'mb-cadastre-src';

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

interface MapboxFloodMapProps {
  report: RisqueReport | null;
  visibleLayerKeys?: ReadonlySet<string>;
  /** Bâtiment cible (diagnostiqué ou sélectionné) — surligné en priorité. */
  batiment?: BdnbBatiment | null;
  /** Bâtiment sélectionné au clic — surligné en priorité. */
  selectedId?: string | null;
  /** Clic bâtiment → id BDNB ; null si clic dans le vide. */
  onSelect?: (id: string | null) => void;
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

export function MapboxFloodMap({
  report,
  visibleLayerKeys = new Set<string>(),
  batiment,
  selectedId,
  onSelect,
  showRisks = false,
  allowParcels = false,
  buildingsLimit = 200,
  initial3D = true,
  fitZoom = 16.5,
}: MapboxFloodMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapReadyRef = useRef(false);
  const buildingsSeqRef = useRef(0);
  const buildingsTimerRef = useRef<number | null>(null);
  const resizeTimerRef = useRef<number | null>(null);
  const renderSeqRef = useRef(0);
  const is3dRef = useRef(initial3D);
  const selectedIdRef = useRef<string | null | undefined>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const latestReportRef = useRef(report);
  latestReportRef.current = report;
  const batimentRef = useRef(batiment);
  batimentRef.current = batiment;
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

  const [is3d, setIs3d] = useState(initial3D);
  const [showParcels, setShowParcels] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  function currentBatiment(): BdnbBatiment | null {
    return batimentRef.current ?? latestReportRef.current?.bdnb?.batiment ?? null;
  }

  function highlightId(): string | null | undefined {
    return selectedIdRef.current ?? currentBatiment()?.batiment_groupe_id ?? null;
  }

  /* ── Init carte (une fois) ── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!MAPBOX_TOKEN) {
      setMapError('Token Mapbox manquant — définissez VITE_MAPBOX_TOKEN dans frontend/.env.');
      return;
    }

    const rep = latestReportRef.current;
    const center: [number, number] = rep ? [rep.lon, rep.lat] : [2.35, 46.8];

    const map = new mapboxgl.Map({
      container,
      style: MAPBOX_STYLE,
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
      if (e?.sourceId || e?.tile || e?.data) {
        console.warn('[mapbox] tuile/source:', e?.error?.message ?? e);
        return;
      }
      const msg = String(e?.error?.message ?? e?.message ?? '');
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
      ensureBaseLayers(map);
      ensureNativeBuildings(map);
      ensureBuildingsLayer(map);
      updateBuildingsTarget(map);
      placeBuildingPin(map);
      void loadBuildings(map);
      if (showRisks) renderReport(map, latestReportRef.current);
    });

    map.on('moveend', () => {
      if (!is3dRef.current) return;
      if (buildingsTimerRef.current) window.clearTimeout(buildingsTimerRef.current);
      buildingsTimerRef.current = window.setTimeout(() => void loadBuildings(map), 500);
    });

    /* Clic bâtiment / vide */
    const queryBuildings = (point: mapboxgl.PointLike) => {
      const ids: string[] = [];
      if (map.getLayer(BUILDINGS_LAYER)) ids.push(BUILDINGS_LAYER);
      if (map.getLayer(NATIVE_BUILDINGS_LAYER)) ids.push(NATIVE_BUILDINGS_LAYER);
      if (map.getLayer('building')) ids.push('building');
      return ids.length ? map.queryRenderedFeatures(point, { layers: ids }) : [];
    };
    map.on('click', (e) => {
      const features = queryBuildings(e.point);
      let id = (features[0]?.properties?.batiment_groupe_id as string | undefined) ?? null;
      // Clic sur un bâtiment Mapbox générique (pas d'id BDNB) : on résout le
      // bâtiment BDNB le plus proche du point via une mini-bbox.
      if (!id) void resolveBuildingAt(e.lngLat).then((resolved) => {
        selectedIdRef.current = resolved;
        updateBuildingsTarget(map);
        onSelectRef.current?.(resolved);
      });
      else {
        selectedIdRef.current = id;
        updateBuildingsTarget(map);
        onSelectRef.current?.(id);
      }
    });
    map.on('mousemove', (e) => {
      const features = queryBuildings(e.point);
      map.getCanvas().style.cursor = features.length ? 'pointer' : '';
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
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Changement de bâtiment ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batiment, report]);

  /* ── Gros plan (step Cartographie : marqueur + popup + calques aléas) ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    if (showRisks) renderReport(map, report);
    else if (report) placeMarker(map, report);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRisks, report]);

  /* ── visibleLayerKeys → masquer/afficher les couches WMS/WFS ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    for (const [key, ids] of layerIdsByKeyRef.current) {
      const visible = visibleLayerKeys.has(key);
      for (const id of ids) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
        }
      }
    }
  }, [visibleLayerKeys]);

  /* ── Sélection clic → surlignage ── */
  useEffect(() => {
    selectedIdRef.current = selectedId ?? null;
    const map = mapRef.current;
    if (map && mapReadyRef.current) updateBuildingsTarget(map);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  /* ═══════════ Couches sources et rendu ═══════════ */

  /** Bâtiments 3D natifs Mapbox : tout le bâti OSM extrudé (hauteurs réelles
   *  OSM, approx.) — remplace le chargement BDNB par viewport pour l'effet
   *  « ville numérique » en vue 3D. */
  function ensureNativeBuildings(map: mapboxgl.Map) {
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

  /** Fond sombre CARTO (vue 2D) + parcelles cadastrales IGN (toggle). */
  function ensureBaseLayers(map: mapboxgl.Map) {
    if (map.getLayer(CARTO_DARK_LAYER)) return;
    map.addSource(CARTO_DARK_SOURCE, {
      type: 'raster',
      tiles: [CARTO_DARK_TILES],
      tileSize: 256,
      maxzoom: 20,
      attribution: '© CARTO © OpenStreetMap contributors',
    });
    map.addLayer({
      id: CARTO_DARK_LAYER,
      type: 'raster',
      source: CARTO_DARK_SOURCE,
      layout: { visibility: is3dRef.current ? 'none' : 'visible' },
      paint: { 'raster-opacity': 1 },
    });
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
        'fill-extrusion-color': buildingColorExpr(highlightId(), currentAccent()),
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
      layout: { visibility: is3dRef.current ? 'visible' : 'none' },
      paint: { 'line-color': currentAccent(), 'line-width': 2.5, 'line-opacity': 0.95 },
    });
  }

  function updateBuildingsTarget(map: mapboxgl.Map) {
    const targetId = highlightId() ?? null;
    const accent = currentAccent();
    if (map.getLayer(BUILDINGS_LAYER)) {
      map.setPaintProperty(BUILDINGS_LAYER, 'fill-extrusion-color', buildingColorExpr(targetId, accent));
      // En 3D, la ville est rendue par les bâtiments natifs Mapbox : la couche
      // BDNB ne garde que le bâtiment cible (surligné en accent) pour éviter
      // la double extrusion sur les mêmes empreintes.
      map.setFilter(BUILDINGS_LAYER, targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], '']);
    }
    if (map.getLayer(BUILDINGS_OUTLINE_LAYER)) {
      map.setFilter(BUILDINGS_OUTLINE_LAYER, targetId ? ['==', ['get', 'batiment_groupe_id'], targetId] : ['==', ['get', 'batiment_groupe_id'], '']);
      map.setPaintProperty(BUILDINGS_OUTLINE_LAYER, 'line-color', accent);
    }
  }

  /* ── Rendu Cartographie : marqueur + popup + calques aléas WMS/WFS ── */

  function renderReport(map: mapboxgl.Map, rep: RisqueReport | null) {
    /* Nettoyage des couches de risque précédentes */
    for (const ids of layerIdsByKeyRef.current.values()) {
      for (const id of ids) {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(`src-${id}`)) map.removeSource(`src-${id}`);
      }
    }
    layerIdsByKeyRef.current.clear();
    const seq = ++renderSeqRef.current;

    placeMarker(map, rep);
    popupRef.current?.remove();
    popupRef.current = null;

    if (!rep) return;

    const topAleas = (rep.aleas || [])
      .filter((a) => a.present === true && a.niveau)
      .map((a) => {
        const band = bandForKey(a.niveau);
        const color = band?.color ?? '#E8E6DC';
        const label = band?.label ?? a.niveau ?? '';
        return `<div class="pop-row"><span>${escHtml(a.libelle)}</span><span style="color:${color}">${label}</span></div>`;
      })
      .join('');

    const ignLink = `https://www.geoportail.gouv.fr/carte?lon=${rep.lon}&lat=${rep.lat}&z=18`;
    const osmLink = `https://www.openstreetmap.org/?mlat=${rep.lat}&mlon=${rep.lon}&zoom=18`;

    popupRef.current = new mapboxgl.Popup({ offset: 22, closeButton: true, maxWidth: '280px' })
      .setLngLat([rep.lon, rep.lat])
      .setHTML(
        `<div class="pop-title">${escHtml(rep.adresse_normalisee)}</div>` +
        (topAleas || '<div class="pop-row"><span>Aucun aléa présent</span><span>—</span></div>') +
        `<div class="pop-links"><a href="${ignLink}" target="_blank">IGN Géoportail</a><a href="${osmLink}" target="_blank">OpenStreetMap</a></div>`
      )
      .addTo(map);

    map.easeTo({ center: [rep.lon, rep.lat], zoom: fitZoom, duration: 1200 });

    /* Surbrillance du bâtiment diagnostiqué */
    const targetId = rep.bdnb?.batiment?.batiment_groupe_id ?? null;
    const oldTarget = highlightId();
    selectedIdRef.current = selectedId ?? null;
    updateBuildingsTarget(map);

    /* Couches WMS + WFS */
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

        if (WMS_LAYER_MAP[a.code]) {
          map.addSource(sourceId, { type: 'raster', tiles: [wmsTileUrl(WMS_LAYER_MAP[a.code])], tileSize: 256, maxzoom: 19 });
          map.addLayer({ id: layerId, type: 'raster', source: sourceId, layout: { visibility: visible ? 'visible' : 'none' }, paint: { 'raster-opacity': 0.65 } });
          track(layerId);
          continue;
        }

        if (WFS_LAYER_MAP[a.code]) {
          let wfsRendered = false;
          for (const typeName of WFS_LAYER_MAP[a.code]) {
            try {
              const geojson = await fetchWfsLayer(typeName, rep.code_insee);
              if (seq !== renderSeqRef.current) return;
              if (!geojson?.features?.length) continue;
              map.addSource(sourceId, { type: 'geojson', data: geojson as GeoJSON.FeatureCollection });
              map.addLayer({
                id: layerId, type: 'fill', source: sourceId,
                layout: { visibility: visible ? 'visible' : 'none' },
                paint: { 'fill-color': color + '55', 'fill-opacity': 1, 'fill-outline-color': color },
              });
              track(layerId);
              wfsRendered = true;
            } catch { /* */ }
          }
          if (wfsRendered) continue;
        }

        /* Fallback : cercle ponctuel */
        map.addSource(sourceId, {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [rep.lon, rep.lat] }, properties: {} }] },
        });
        let circle: any = { 'circle-radius': 10, 'circle-color': color, 'circle-opacity': 0.65 };
        if (a.niveau && D03.find((d) => d.key === a.niveau)) {
          circle['circle-stroke-color'] = color;
          circle['circle-stroke-width'] = 3;
        }
        map.addLayer({ id: layerId, type: 'circle', source: sourceId, layout: { visibility: visible ? 'visible' : 'none' }, paint: circle });
        track(layerId);
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
      const b = map.getBounds();
      west = b.getWest(); south = b.getSouth(); east = b.getEast(); north = b.getNorth();
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
      if (b?.batiment_groupe_id) {
        const targetInFc = fc.features.some((f) => f.properties?.batiment_groupe_id === b.batiment_groupe_id);
        if (!targetInFc && b.geom_groupe) {
          const wgsGeom = geomToWgs84(b.geom_groupe as Record<string, unknown>);
          if (wgsGeom) fc.features.push({ type: 'Feature', geometry: wgsGeom as unknown as GeoJSON.Geometry, properties: { batiment_groupe_id: b.batiment_groupe_id, hauteur_mean: b.hauteur_mean || 10 } });
        }
      }
      (map.getSource(BUILDINGS_SOURCE) as mapboxgl.GeoJSONSource)?.setData(fc);
    } catch { /* */ }
  }

  function toggle3D(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    is3dRef.current = enabled; setIs3d(enabled);
    for (const id of [BUILDINGS_LAYER, BUILDINGS_OUTLINE_LAYER, NATIVE_BUILDINGS_LAYER]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', enabled ? 'visible' : 'none');
    }
    if (enabled) updateBuildingsTarget(map); // filtre BDNB → bâtiment cible
    /* Vue 2D → fond sombre CARTO (celui de l'ancienne carte MapLibre). */
    if (map.getLayer(CARTO_DARK_LAYER)) {
      map.setLayoutProperty(CARTO_DARK_LAYER, 'visibility', enabled ? 'none' : 'visible');
    }
    map.easeTo({ pitch: enabled ? 55 : 0, duration: 800 });
    if (enabled) void loadBuildings(map);
  }

  /** Résout le bâtiment BDNB le plus proche d'un point de clic (mini-bbox). */
  async function resolveBuildingAt(lngLat: mapboxgl.LngLat): Promise<string | null> {
    const d = 0.0012; // ~130 m — couvre le bâtiment même si le clic est en bordure
    const url =
      `${API}/diagnostic/zone/buildings?west=${lngLat.lng - d}&south=${lngLat.lat - d}` +
      `&east=${lngLat.lng + d}&north=${lngLat.lat + d}&limit=10`;
    try {
      const resp = await fetch(url);
      if (!resp.ok) return null;
      const fc = (await resp.json()) as GeoJSON.FeatureCollection;
      let best: string | null = null;
      let bestD = Infinity;
      for (const f of fc.features || []) {
        const c = polygonCenter((f.geometry as { coordinates?: unknown } | null)?.coordinates);
        if (!c) continue;
        const dd = (c[0] - lngLat.lng) ** 2 + (c[1] - lngLat.lat) ** 2;
        if (dd < bestD) { bestD = dd; best = (f.properties?.batiment_groupe_id as string | undefined) ?? null; }
      }
      return best;
    } catch { return null; }
  }

  function toggleParcels(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    setShowParcels(enabled);
    if (map.getLayer(CADASTRE_LAYER)) {
      map.setLayoutProperty(CADASTRE_LAYER, 'visibility', enabled ? 'visible' : 'none');
    }
  }

  return (
    <div className="mb-demo-wrap">
      {mapError ? (
        <div className="mb-demo-error"><md-icon>error</md-icon><p>{mapError}</p></div>
      ) : (
        <div ref={containerRef} className="mb-demo-map" />
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
        </div>
      )}
    </div>
  );
}

/* ── Couleur des volumes extrudés ── */
function buildingColorExpr(targetId: string | null | undefined, accent: string): any {
  const ramp: any = ['interpolate', ['linear'], ['coalesce', ['get', 'hauteur_mean'], 0],
    0, '#4f607a', 6, '#778ca8', 12, '#a3b7cc', 20, '#c7d8e6', 32, '#eef4fa'];
  return targetId ? ['case', ['==', ['get', 'batiment_groupe_id'], targetId], accent, ramp] : ramp;
}