// =============================================================================
//   TYPHOON — Carte unique Mapbox GL JS (pas de fallback MapLibre)
//   Fond de carte : Mapbox (style personnalisé sombre) ; en vue 2D, le fond
//   sombre CARTO d'origine MapLibre est réutilisé (tuiles identiques à
//   l'ancienne carte).
//   · Bâtiments 3D natifs Mapbox (source composite/building — pas d'extrusion BDNB)
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
  RISK_WMS_POLYGON,
  bandForKey,
  escHtml,
} from '../zone/config';
import {
  cadastreTileUrl,
  firstRing,
  fetchWfsLayer,
  geomToWgs84,
  polygonCenter,
  buildingSamplePoints,
  wmsTileUrl,
  wgs84ToWebMercator,
  fetchRiskZoneImage,
  riskPixelColor,
} from '../zone/mapHelpers';

// Token + style en variable d'environnement (jamais en dur dans le code).
const MAPBOX_TOKEN: string = (import.meta as any).env?.VITE_MAPBOX_TOKEN || '';
const MAPBOX_STYLE: string =
  (import.meta as any).env?.VITE_MAPBOX_STYLE || 'mapbox://styles/mapbox/standard';
if (MAPBOX_TOKEN) {
  mapboxgl.accessToken = MAPBOX_TOKEN;
}

/* ── IDs de couches ── */
/* Bâtiments 3D : rendus nativement par le style Mapbox Standard
   (couche « 3d-building » + modèles détaillés) — plus d'extrusion custom. */

/* Fond sombre 2D — tuiles CARTO dark de l'ancienne carte MapLibre. */
const CARTO_DARK_LAYER = 'mb-carto-dark';
const CARTO_DARK_SOURCE = 'mb-carto-dark-src';
const CARTO_DARK_TILES = 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png';

/* Parcelles cadastrales IGN (WMS data.geopf.fr) — toggle Analyse. */
const CADASTRE_LAYER = 'mb-cadastre';
const CADASTRE_SOURCE = 'mb-cadastre-src';

/** Hex #RRGGBB → rgba() (Mapbox refuse le hex 8 chiffres dans fill-color). */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

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
  /** Bâtiment cible (diagnostiqué) — surligné en priorité. */
  batiment?: BdnbBatiment | null;
  /** Afficher le popup aléas + couches WMS/WFS (étape Cartographie uniquement). */
  showRisks?: boolean;
  /** Afficher le toggle « Parcelles cadastrales » (étape Analyse uniquement). */
  allowParcels?: boolean;
  /** 3D au démarrage. */
  initial3D?: boolean;
  fitZoom?: number;
}

/* ── Composant ── */

export function MapboxFloodMap({
  report,
  visibleLayerKeys = new Set<string>(),
  batiment,
  showRisks = false,
  allowParcels = false,
  initial3D = true,
  fitZoom = 16.5,
}: MapboxFloodMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapReadyRef = useRef(false);
  const resizeTimerRef = useRef<number | null>(null);
  const renderSeqRef = useRef(0);
  const is3dRef = useRef(initial3D);
  /* Coloration des bâtiments par zone de risque : quand elle est activée, les
     couches WMS/WFS sont masquées et seuls les bâtiments colorés s'affichent. */
  const [coloringMode, setColoringMode] = useState(false);
  const coloringModeRef = useRef(false);
  /* Mode « Sunset » : éclairage natif Standard (lightPreset dusk). */
  const [sunsetMode, setSunsetMode] = useState(false);
  const sunsetModeRef = useRef(false);
  const latestReportRef = useRef(report);
  latestReportRef.current = report;
  const batimentRef = useRef(batiment);
  batimentRef.current = batiment;
  const visibleKeysRef = useRef(visibleLayerKeys);
  visibleKeysRef.current = visibleLayerKeys;
  const showRisksRef = useRef(showRisks);
  showRisksRef.current = showRisks;
  /* Séquence + timer des colorations 3D par risque (jointure spatiale). */
  const riskSeqRef = useRef(0);
  const riskTimerRef = useRef<number | null>(null);
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
      const evt = e as unknown as { sourceId?: string; tile?: unknown; data?: unknown; error?: Error; message?: string };
      if (evt?.sourceId || evt?.tile || evt?.data) {
        console.warn('[mapbox] tuile/source:', evt?.error?.message ?? e);
        return;
      }
      const msg = String(evt?.error?.message ?? evt?.message ?? '');
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
      placeBuildingPin(map);
      if (showRisks) renderReport(map, latestReportRef.current);
      /* Mode sunset persistant (ex. remount) : on réapplique la palette. */
      if (sunsetModeRef.current) applySunsetMode(map, true);
    });

    map.on('moveend', () => {
      /* Bâtiments 3D : entièrement gérés par Mapbox (composite/building).
         Seule la coloration par aléa recharge les bâtiments du viewport. */
      if (showRisksRef.current && is3dRef.current) scheduleRiskColoring(map);
    });

    /* Sélection de bâtiments au clic : désactivée — on reste sur le bâtiment
       de l'adresse saisie (pas de navigation/fiche d'autres bâtiments). */

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
      }, first ? 60 : 350);
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
      resizeTimerRef.current = null;
      if (riskTimerRef.current) window.clearTimeout(riskTimerRef.current);
      riskTimerRef.current = null;
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
    placeBuildingPin(map);
    const b = currentBatiment();
    if (b?.geom_groupe) {
      try {
        const wgs = geomToWgs84(b.geom_groupe as Record<string, unknown>);
        const c = polygonCenter(wgs?.coordinates);
        if (c) map.easeTo({ center: c, zoom: fitZoom, pitch: is3dRef.current ? 55 : 0, duration: 900 });
      } catch { /* */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batiment, report]);

  /* ── Gros plan (step Cartographie : marqueur + popup + calques aléas) ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    if (showRisks) renderReport(map, report);
    else if (report) placeMarker(map, report);
    void refreshRiskColoring(map);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRisks, report]);

  /* ── visibleLayerKeys / coloringMode → masquer/afficher les couches WMS/WFS
        + coloration 3D (en mode coloration, les couches restent masquées). ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    applyLayerVisibility(map);
    void refreshRiskColoring(map);
  }, [visibleLayerKeys, coloringMode]);

  /* ═══════════ Couches sources et rendu ═══════════ */

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
                paint: { 'fill-color': hexToRgba(color, 0.33), 'fill-opacity': 1, 'fill-outline-color': color },
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

  /** Applique la visibilité des couches WMS/WFS selon les yeux cochés — et les
   *  masque toutes quand la coloration des bâtiments est activée. */
  function applyLayerVisibility(map: mapboxgl.Map) {
    for (const [key, ids] of layerIdsByKeyRef.current) {
      const visible = !coloringModeRef.current && visibleLayerKeys.has(key);
      for (const id of ids) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
        }
      }
    }
  }

  /** Toggle « Coloration » : ON → couches masquées + bâtiments colorés selon
   *  la couleur de la couche WMS à leur position ; OFF → couches normales. */
  function toggleColoring(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    coloringModeRef.current = enabled;
    setColoringMode(enabled);
    applyLayerVisibility(map);
    if (enabled) void refreshRiskColoring(map);
    else clearRiskLayers(map);
  }

  function toggle3D(enabled: boolean) {
    const map = mapRef.current;
    if (!map) return;
    is3dRef.current = enabled; setIs3d(enabled);
    /* Les bâtiments 3D sont rendus nativement par le style Standard. */
    /* Vue 2D → fond sombre CARTO (sauf en mode sunset : on garde le fond
       Mapbox en éclairage crépusculaire, le raster CARTO le masquerait). */
    if (map.getLayer(CARTO_DARK_LAYER)) {
      map.setLayoutProperty(CARTO_DARK_LAYER, 'visibility', enabled || sunsetModeRef.current ? 'none' : 'visible');
    }
    map.easeTo({ pitch: enabled ? 55 : 0, duration: 800 });
    void refreshRiskColoring(map);
  }

  /** Mode « Sunset » : éclairage natif du style Mapbox Standard
   *  (lightPreset dusk — vraie lumière de crépuscule, ombres longues).
   *  Désactivé → retour au preset day. En 2D, on masque le raster CARTO
   *  sombre qui couvrirait l'éclairage. */
  function applySunsetMode(map: mapboxgl.Map, enabled: boolean) {
    sunsetModeRef.current = enabled;
    setSunsetMode(enabled);
    try {
      map.setConfigProperty('basemap', 'lightPreset', enabled ? 'dusk' : 'day');
    } catch {
      /* Style non-Standard (env VITE_MAPBOX_STYLE) : pas d'import basemap. */
    }
    if (map.getLayer(CARTO_DARK_LAYER)) {
      map.setLayoutProperty(CARTO_DARK_LAYER, 'visibility', enabled ? 'none' : (is3dRef.current ? 'none' : 'visible'));
    }
  }

  /* ═══════════ Coloration des bâtiments par aléa (2D et 3D) ═══════════
     Mode « Coloration » (toggle sur la carte, 2D comme 3D) : les couches
     WMS/WFS sont masquées et chaque bâtiment est teinté de la COULEUR de la
     couche WMS à sa position (échantillonnage GetMap transparent, bbox du
     viewport, jointure sur les bâtiments BDNB) — vert/orange/rouge selon la
     légende de la couche, comme le rendu WFS. En 3D : coquilles extrudées ;
     en 2D : empreintes aplaties. Les couches sont re-créées à chaque
     rafraîchissement, triées par sévérité (le risque le plus fort passe
     dessus) ; les aléas décochés sont supprimés (pas de coloration périmée). */

  /** Zoom minimum pour échantillonner : plus bas, la bbox couvre tout un
   *  territoire et l'échantillonnage WMS grossier colore n'importe quoi
   *  (ex. les argiles à l'échelle de la France). On ne colore qu'en vue
   *  rapprochée bâtiment. */
  const MIN_RISK_ZOOM = 15;

  /** Rang de sévérité d'un aléa (bande D03 du rapport, sinon repli). */
  function riskSeverityRank(code: string): number {
    const rep = latestReportRef.current;
    const alea = rep?.aleas?.find((a) => a.code === code);
    const band = alea?.niveau ? bandForKey(alea.niveau) : undefined;
    if (band) return Math.max(0, D03.findIndex((b) => b.key === band.key));
    return 2; // Modéré par défaut
  }

  function clearRiskLayers(map: mapboxgl.Map) {
    for (const code of Object.keys(WMS_LAYER_MAP)) {
      const layerId = `bldg-risk-${code}`;
      const srcId = `bldg-risk-src-${code}`;
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      if (map.getSource(srcId)) map.removeSource(srcId);
    }
  }

  /** Ajoute (ou remplace) la coloration d'un aléa : seule la liste des
   *  bâtiments réellement dans la zone est envoyée (Mapbox ne gère pas les
   *  data-expressions sur fill-extrusion-opacity, l'opacité est constante). */
  function upsertRiskLayer(map: mapboxgl.Map, code: string, features: GeoJSON.Feature[]) {
    const srcId = `bldg-risk-src-${code}`;
    const layerId = `bldg-risk-${code}`;
    const inRisk = features.filter((f) => f.properties?.in_risk === 1);
    const fc: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: inRisk };
    if (map.getLayer(layerId)) map.removeLayer(layerId);
    if (map.getSource(srcId)) map.removeSource(srcId);
    map.addSource(srcId, { type: 'geojson', data: fc });
    /* Même coloration en 2D et 3D : en 2D une simple couche fill (empreinte
       aplatie, couleur de la couche WMS à sa position) ; en 3D la coquille
       extrudée (hauteur BDNB + marge) qui dépasse du bâtiment natif Mapbox. */
    const is3d = is3dRef.current;
    map.addLayer(
      is3d
        ? {
            id: layerId,
            type: 'fill-extrusion',
            source: srcId,
            layout: { visibility: 'visible' },
            paint: {
              'fill-extrusion-height': ['+', ['coalesce', ['get', 'hauteur_mean'], 8], 3],
              'fill-extrusion-base': 0,
              'fill-extrusion-color': ['coalesce', ['get', 'fill_color'], '#888888'],
              'fill-extrusion-opacity': 0.8,
              'fill-extrusion-vertical-gradient': false,
            },
          }
        : {
            id: layerId,
            type: 'fill',
            source: srcId,
            layout: { visibility: 'visible' },
            paint: {
              'fill-color': ['coalesce', ['get', 'fill_color'], '#888888'],
              'fill-opacity': 0.8,
            },
          }
    );
  }

  /** Recalcule la coloration des bâtiments pour les aléas cochés (2D et 3D). */
  async function refreshRiskColoring(map: mapboxgl.Map) {
    // Uniquement étape Cartographie + mode coloration + zoom rapproché.
    if (!showRisksRef.current || !coloringModeRef.current) {
      clearRiskLayers(map);
      if (!coloringModeRef.current) applyLayerVisibility(map);
      return;
    }
    let zoom = 0;
    try { zoom = map.getZoom(); } catch { return; }
    if (!isFinite(zoom) || zoom < MIN_RISK_ZOOM) {
      clearRiskLayers(map);
      return;
    }
    const rep = latestReportRef.current;
    if (!rep) return;
    const active = [...(visibleKeysRef.current || [])].filter((k) => WMS_LAYER_MAP[k]);
    if (!active.length) {
      clearRiskLayers(map);
      return;
    }
    const seq = ++riskSeqRef.current;
    const ordered = [...active].sort((a, b) => riskSeverityRank(a) - riskSeverityRank(b));

    /* 1. Bâtiments BDNB du viewport (empreinte + hauteur). On ne touche pas
          aux couches avant d'avoir des données : si le fetch échoue (BDNB
          souvent rate-limité), la coloration précédente reste en place. */
    let west = 0, south = 0, east = 0, north = 0;
    try {
      const b = map.getBounds();
      if (!b) return;
      west = b.getWest(); south = b.getSouth(); east = b.getEast(); north = b.getNorth();
      if (!isFinite(west) || !isFinite(east)) return;
    } catch { return; }
    let buildings: GeoJSON.Feature[] = [];
    try {
      const resp = await fetch(
        `${API}/diagnostic/zone/buildings?west=${west}&south=${south}&east=${east}&north=${north}&limit=2000`
      );
      if (seq !== riskSeqRef.current) return;
      if (resp.ok) {
        const fc = (await resp.json()) as GeoJSON.FeatureCollection;
        buildings = fc?.features || [];
      }
    } catch { /* BDNB indisponible → on garde la coloration précédente */ }
    if (!buildings.length || seq !== riskSeqRef.current) return;

    /* 2. Purge (aléas décochés + ordre précédent) puis reconstruction dans
          l'ordre de sévérité — le risque le plus fort passe au-dessus. */
    clearRiskLayers(map);

    /* 3. Pour chaque aléa actif : couche WMS GetMap (bbox du viewport) →
          échantillonnage des pixels à l'empreinte de chaque bâtiment. */
    const b = map.getBounds();
    if (!b) return;
    const [xmin, ymin] = wgs84ToWebMercator(b.getWest(), b.getSouth());
    const [xmax, ymax] = wgs84ToWebMercator(b.getEast(), b.getNorth());
    for (const code of ordered) {
      if (seq !== riskSeqRef.current) return;
      const layerName = WMS_LAYER_MAP[code];
      if (!layerName) continue;
      const img = await fetchRiskZoneImage(layerName, [xmin, ymin, xmax, ymax], 512);
      if (!img || seq !== riskSeqRef.current) continue;
      // Zonages : tolérance fine (bords anti-aliasés). Points/lignes : voisinage.
      const tolPx = RISK_WMS_POLYGON.has(code) ? 2 : 10;
      const colored = buildings.map((f) => {
        // Couleur de la couche WMS à la position du bâtiment (moyenne des
        // pixels du voisinage) — le bâtiment prend la couleur de sa zone.
        let color: string | null = null;
        for (const [lon, lat] of buildingSamplePoints(f.geometry as GeoJSON.Geometry)) {
          color = riskPixelColor(img, lon, lat, tolPx);
          if (color) break;
        }
        return {
          ...f,
          properties: {
            ...(f.properties || {}),
            in_risk: color ? 1 : 0,
            fill_color: color ?? undefined,
          },
        } as GeoJSON.Feature;
      });
      upsertRiskLayer(map, code, colored);
    }
  }

  function scheduleRiskColoring(map: mapboxgl.Map) {
    if (riskTimerRef.current) window.clearTimeout(riskTimerRef.current);
    riskTimerRef.current = window.setTimeout(() => {
      riskTimerRef.current = null;
      void refreshRiskColoring(map);
    }, 450);
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
            title={is3d ? 'Revenir à la vue 2D' : 'Passer en vue 3D (bâtiments Mapbox)'}
            aria-label={is3d ? 'Revenir à la vue 2D' : 'Passer en vue 3D'}>
            <md-icon>view_in_ar</md-icon>
            <span>{is3d ? '2D' : '3D'}</span>
          </button>
          <button type="button"
            className={`map-3d-toggle analyse${coloringMode ? ' active' : ''}`}
            onClick={() => toggleColoring(!coloringMode)} aria-pressed={coloringMode}
            title={coloringMode
              ? 'Afficher les couches de risque normalement (bâtiments non colorés)'
              : 'Colorer les bâtiments selon les zones de risque (masque les couches)'}
            aria-label={coloringMode
              ? 'Désactiver la coloration des bâtiments'
              : 'Colorer les bâtiments selon les zones de risque'}>
            <md-icon>palette</md-icon>
            <span>Coloration</span>
          </button>
          <button type="button"
            className={`map-3d-toggle analyse${sunsetMode ? ' active' : ''}`}
            onClick={() => {
              const m = mapRef.current;
              if (m) applySunsetMode(m, !sunsetMode);
            }} aria-pressed={sunsetMode}
            title={sunsetMode
              ? 'Désactiver le mode crépuscule (retour à la palette sombre)'
              : 'Mode crépuscule — palette chaude (coucher de soleil)'}
            aria-label={sunsetMode
              ? 'Désactiver le mode crépuscule'
              : 'Activer le mode crépuscule (coucher de soleil)'}>
            <md-icon>wb_twilight</md-icon>
            <span>Sunset</span>
          </button>
        </div>
      )}
    </div>
  );
}

