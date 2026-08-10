// =============================================================================
//   TYPHOON — /zone : BdnbMap — carte « BDNB only » pour l'onglet Analyse
//   Carte OpenLayers « BDNB only » : uniquement le bâti BDNB + parcelles
//   cadastrales (sans les couches Géorisques de la carte unifiée Mapbox).
//
//   Couches :
//     1. Emprise du bâtiment  — geom_groupe (GeoJSON, EPSG:2154 → 4326),
//        vecteur teinté par --accent (fill + arêtes nettes).
//     2. Parcelles cadastrales — WMS IGN Géoplateforme
//        (CADASTRALPARCELS.PARCELLAIRE_EXPRESS, CORS ouvert, souverain IGN).
//     3. Marqueur d'adresse    — pin accent à report.lat/lon.
//
//   Fond : CARTO « light_all » — sur le thème sombre de l'app, un fond noir
//   (dark_all) rendait la carte illisible (tuiles quasi noires + parcelles
//   cadastrales indiscernables). Le fond clair fait ressortir les parcelles.
//
//   Reprojection : la BDNB répond en EPSG:2154 (Lambert-93, mètres). Le
//   registre de projections d'OpenLayers ne contient ni le 2154 ni le 3857
//   (Web Mercator) par défaut → `readFeatures(dataProjection:'EPSG:2154')`
//   laisse les coordonnées en Lambert-93 brutes, qui sont alors interprétées
//   comme des mètres 3857 : l'emprise atterrit à ~235 km de l'adresse et le
//   fit() part dans le vide. On reprojette donc le polygone en EPSG:4326
//   (lat/lon) côté client — port exact de la fonction éprouvée
//   `footprint.lambert93_to_wgs84` du backend (vérifié contre pyproj).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import OLMap from 'ol/Map';
import View from 'ol/View';
import Overlay from 'ol/Overlay';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import XYZ from 'ol/source/XYZ';
import TileWMS from 'ol/source/TileWMS';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import { defaults as defaultControls } from 'ol/control';
import { fromLonLat } from 'ol/proj';
import { extend as extendExtent } from 'ol/extent';
import Style from 'ol/style/Style';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';

import type { BdnbBatiment, RisqueReport } from '../zone/config';

/* ── Fond clair (lisible sur thème sombre) ── */
const CARTO_URLS = [
  'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
  'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
];

const CADASTRE_WMS = 'https://data.geopf.fr/wms-r/wms';
const CADASTRE_LAYER = 'CADASTRALPARCELS.PARCELLAIRE_EXPRESS';

const geoJsonFormat = new GeoJSON();

// ===========================================================================
//  Lambert-93 (EPSG:2154) → WGS84 (EPSG:4326)
//  Port exact de backend/app/digital_twin/footprint.py (lambert93_to_wgs84) :
//  projection conique conforme de Lambert à deux parallèles, ellipsoïde
//  GRS80, constantes IGN (44°/49°, origine 46,5°/3°E, fausses origines
//  700000/6600000). Vérifié contre pyproj : < 1 mm sur les tests de l'API.
// ===========================================================================

const L93_A = 6378137.0; // demi-grand axe GRS80
const L93_E = 0.0818191910428158; // première excentricité GRS80
const L93_LAMBDA0 = (3.0 * Math.PI) / 180.0; // méridien central 3°E
const L93_PHI0 = (46.5 * Math.PI) / 180.0; // latitude d'origine
const L93_PHI1 = (44.0 * Math.PI) / 180.0; // 1er parallèle standard
const L93_PHI2 = (49.0 * Math.PI) / 180.0; // 2e parallèle standard
const L93_X0 = 700000.0; // fausse abscisse
const L93_Y0 = 6600000.0; // fausse ordonnée

const l93M = (phi: number) => Math.cos(phi) / Math.sqrt(1 - L93_E * L93_E * Math.sin(phi) ** 2);
const l93T = (phi: number) =>
  Math.tan(Math.PI / 4 - phi / 2) /
  Math.pow((1 - L93_E * Math.sin(phi)) / (1 + L93_E * Math.sin(phi)), L93_E / 2);

const L93_N =
  (Math.log(l93M(L93_PHI1)) - Math.log(l93M(L93_PHI2))) /
  (Math.log(l93T(L93_PHI1)) - Math.log(l93T(L93_PHI2)));
const L93_F = l93M(L93_PHI1) / (L93_N * Math.pow(l93T(L93_PHI1), L93_N));
const L93_RHO0 = L93_A * L93_F * Math.pow(l93T(L93_PHI0), L93_N);

/** (x, y) Lambert-93 → [lon, lat] WGS84. */
function lambert93ToWgs84(x: number, y: number): [number, number] {
  const dx = x - L93_X0;
  const dy = L93_RHO0 - (y - L93_Y0);
  let rho = Math.hypot(dx, dy);
  if (L93_N < 0) rho = -rho;
  const theta = Math.atan2(dx, dy);
  const lon = L93_LAMBDA0 + theta / L93_N;
  const t = Math.pow(rho / (L93_A * L93_F), 1.0 / L93_N);
  let phi = Math.PI / 2 - 2 * Math.atan(t);
  for (let i = 0; i < 6; i++) {
    phi =
      Math.PI / 2 -
      2 * Math.atan(t * Math.pow((1 - L93_E * Math.sin(phi)) / (1 + L93_E * Math.sin(phi)), L93_E / 2));
  }
  return [(lon * 180) / Math.PI, (phi * 180) / Math.PI];
}

/**
 * Reprojette récursivement les coordonnées d'un GeoJSON (Polygon ou
 * MultiPolygon) de Lambert-93 vers WGS84, et réécrit son CRS.
 * Le `crs` de la réponse BDNB peut manquer ou être EPSG:4326 (cas rare) —
 * on repère alors la nature des coordonnées par leur ordre de grandeur.
 */
function geomToWgs84(geom: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!geom || typeof geom !== 'object') return null;
  const crs = geom.crs as { properties?: { name?: unknown } } | undefined;
  const crsName = String(crs?.properties?.name || '');
  const is4326 = /4326|CRS84/i.test(crsName);
  const coords = geom.coordinates as unknown;

  if (!is4326) {
    // Peut être 2154 (mètres ~1e6) ou 4326 sans crs (degrés ≤ 180/90) :
    // on reprojette sauf si les valeurs ressemblent déjà à des degrés.
    const first = firstCoord(coords);
    if (!(first && Math.abs(first[0]) <= 180 && Math.abs(first[1]) <= 90)) {
      return {
        ...geom,
        crs: { type: 'name', properties: { name: 'EPSG:4326' } },
        coordinates: mapCoords(coords, lambert93ToWgs84),
      };
    }
  }
  return { ...geom, crs: { type: 'name', properties: { name: 'EPSG:4326' } } };
}

function firstCoord(node: unknown): [number, number] | null {
  if (!Array.isArray(node)) return null;
  if (node.length >= 2 && typeof node[0] === 'number' && typeof node[1] === 'number') {
    return [node[0], node[1]];
  }
  for (const sub of node) {
    const c = firstCoord(sub);
    if (c) return c;
  }
  return null;
}

function mapCoords(
  node: unknown,
  fn: (x: number, y: number) => [number, number]
): unknown {
  if (!Array.isArray(node)) return node;
  if (node.length >= 2 && typeof node[0] === 'number' && typeof node[1] === 'number') {
    const [x, y] = node as [number, number];
    return fn(x, y);
  }
  return node.map((n) => mapCoords(n, fn));
}

// ===========================================================================

interface BdnbMapProps {
  batiment: BdnbBatiment;
  report: RisqueReport;
}

export function BdnbMap({ batiment, report }: BdnbMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<OLMap | null>(null);
  const viewRef = useRef<View | null>(null);
  const pinElRef = useRef<HTMLDivElement | null>(null);
  const markerOverlayRef = useRef<Overlay | null>(null);
  const footprintLayerRef = useRef<VectorLayer | null>(null);
  const cadastreLayerRef = useRef<TileLayer | null>(null);
  const lastFitRef = useRef<(() => void) | null>(null);
  const [showCadastre, setShowCadastre] = useState(true);
  const [showEmprise, setShowEmprise] = useState(true);

  /* ── Init map (une seule fois) ── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const cartoLayer = new TileLayer({
      source: new XYZ({ urls: CARTO_URLS, tileSize: 256, maxZoom: 19 }),
    });

    const cadastreLayer = new TileLayer({
      source: new TileWMS({
        url: CADASTRE_WMS,
        params: {
          SERVICE: 'WMS',
          VERSION: '1.3.0',
          LAYERS: CADASTRE_LAYER,
          FORMAT: 'image/png',
          TRANSPARENT: 'true',
          CRS: 'EPSG:3857',
        },
        serverType: 'geoserver',
        crossOrigin: 'anonymous',
        transition: 0,
      }),
      opacity: 0.8,
    });
    cadastreLayerRef.current = cadastreLayer;

    const footprintLayer = new VectorLayer({
      source: new VectorSource(),
      // L'accent est lu à chaque rendu : le canvas ne résout pas var() seul,
      // on le résout donc via getComputedStyle (suit le sélecteur de couleur).
      style: () => {
        const accent =
          getComputedStyle(container).getPropertyValue('--accent').trim() || '#4386b1';
        return new Style({
          fill: new Fill({ color: accent + '55' }),
          stroke: new Stroke({ color: accent, width: 2.5 }),
        });
      },
    });
    footprintLayerRef.current = footprintLayer;

    const view = new View({
      center: fromLonLat([report.lon, report.lat]),
      zoom: 16,
      minZoom: 3,
      maxZoom: 19,
    });
    viewRef.current = view;

    const pinEl = document.createElement('div');
    pinEl.className = 'map-pin';
    pinEl.style.display = 'none';
    container.appendChild(pinEl);
    pinElRef.current = pinEl;

    const markerOverlay = new Overlay({
      element: pinEl,
      positioning: 'center-center',
      stopEvent: false,
    });
    markerOverlayRef.current = markerOverlay;

    const map = new OLMap({
      // Ordre : fond → parcelles cadastrales → emprise BDNB (le bâti passe
      // par-dessus les lignes de parcelles pour garder des arêtes nettes).
      target: container,
      layers: [cartoLayer, cadastreLayer, footprintLayer],
      view,
      overlays: [markerOverlay],
      controls: defaultControls({ attribution: false, rotate: false, zoom: true }),
    });
    mapRef.current = map;

    // L'étape « Analyse » est masquée via [hidden] (display:none) tant que
    // l'utilisateur n'y est pas : la carte est alors créée dans un conteneur
    // de taille 0 et OpenLayers ne demande aucune tuile. Dès que la section
    // passe de 0×0 à une taille réelle (transition hidden→visible), on
    // déclenche updateSize() + un nouveau fit pour charger les tuiles au bon
    // endroit. Sur les autres resize (fenêtre redimensionnée, panneau), on ne
    // fait que synchroniser la taille : re-fitter écraserait le zoom/pan de
    // l'utilisateur. `wasZero` évite aussi un double-fit au montage visible.
    let wasZero = container.clientWidth === 0 || container.clientHeight === 0;
    const ro = new ResizeObserver(() => {
      const el = containerRef.current;
      if (!el) return;
      const isZero = el.clientWidth === 0 || el.clientHeight === 0;
      if (!isZero) map.updateSize();
      if (wasZero && !isZero) lastFitRef.current?.(); // transition vers visible
      wasZero = isZero;
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      map.setTarget(undefined);
      pinEl.remove();
      mapRef.current = null;
      viewRef.current = null;
      markerOverlayRef.current = null;
      pinElRef.current = null;
      footprintLayerRef.current = null;
      cadastreLayerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Emprise BDNB + marqueur + fit quand le bâtiment change ── */
  useEffect(() => {
    const map = mapRef.current;
    const view = viewRef.current;
    const footprintLayer = footprintLayerRef.current;
    if (!map || !view || !footprintLayer) return;

    const coord = fromLonLat([report.lon, report.lat]);
    const pinEl = pinElRef.current;
    if (pinEl) pinEl.style.display = 'block';
    markerOverlayRef.current?.setPosition(coord);

    const source = footprintLayer.getSource();
    if (!source) return;
    source.clear();

    // Emprise : geom_groupe (GeoJSON Polygon/MultiPolygon, EPSG:2154)
    if (batiment.geom_groupe) {
      try {
        const wgs = geomToWgs84(batiment.geom_groupe as Record<string, unknown>);
        const features = wgs
          ? geoJsonFormat.readFeatures(wgs, {
              dataProjection: 'EPSG:4326',
              featureProjection: 'EPSG:3857',
            })
          : [];
        source.addFeatures(features);
      } catch (err) {
        console.warn('BdnbMap — geom_groupe illisible :', err);
      }
    }

    // Fit : emprise + marqueur, sinon marqueur seul.
    // Garde-fou : si le bâtiment BDNB est anormalement loin de l'adresse
    // géocodée (le géocodeur BDNB peut retomber sur une autre rue — cas vu
    // en réel, ~2,6 km), on ne laisse pas l'emprise étirer la vue jusqu'à
    // perdre le bâtiment : on se cale sur le marqueur d'adresse.
    const doFit = () => {
      const featExtent = source.getExtent();
      const base: number[] = featExtent
        ? [...featExtent]
        : [coord[0], coord[1], coord[0], coord[1]];
      // Emprise + marqueur d'adresse : c'est l'étendue réelle à cadrer. On
      // mesure sa diagonale : si elle est déraisonnable (bâtiment BDNB à
      // plus de 2 km du point d'adresse — le géocodeur BDNB peut retomber
      // sur une autre rue, cas vu en réel ~2,6 km), on se cale sur le
      // marqueur d'adresse seul plutôt que d'afficher un vide entre les deux.
      const union = extendExtent(base, coord);
      const spanM = Math.hypot(union[2] - union[0], union[3] - union[1]);
      const extent = spanM > 2000 ? [coord[0], coord[1], coord[0], coord[1]] : union;
      view.fit(extent, { padding: [70, 70, 70, 70], maxZoom: 18, duration: 900 });
    };
    lastFitRef.current = doFit;

    // Si la section est déjà visible, on fit directement ; sinon le
    // ResizeObserver s'en chargera dès qu'elle le devient.
    const el = containerRef.current;
    if (el && el.clientWidth > 0 && el.clientHeight > 0) {
      map.updateSize();
      doFit();
    }
  }, [batiment, report]);

  /* ── Visibilité des couches ── */
  useEffect(() => {
    cadastreLayerRef.current?.setVisible(showCadastre);
  }, [showCadastre]);

  useEffect(() => {
    footprintLayerRef.current?.setVisible(showEmprise);
  }, [showEmprise]);

  /* L'accent peut changer (sélecteur) : on force le recalcul du style vecteur
     uniquement quand la valeur résolue diffère de la précédente. */
  const lastAccentRef = useRef<string>('');
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const accent = getComputedStyle(el).getPropertyValue('--accent').trim();
    if (accent && accent !== lastAccentRef.current) {
      lastAccentRef.current = accent;
      footprintLayerRef.current?.changed();
    }
  });

  return (
    <div className="bdnb-map">
      <div ref={containerRef} className="bdnb-map-canvas" />
      <div className="bdnb-map-tools" role="group" aria-label="Couches de la carte">
        <md-icon-button
          toggle
          selected={showEmprise}
          aria-label="Afficher / masquer l'emprise du bâtiment"
          title="Emprise du bâtiment (BDNB)"
          onClick={() => setShowEmprise((v) => !v)}
        >
          <md-icon>crop_square</md-icon>
          <md-icon slot="selected">crop_square</md-icon>
        </md-icon-button>
        <md-icon-button
          toggle
          selected={showCadastre}
          aria-label="Afficher / masquer les parcelles cadastrales"
          title="Parcelles cadastrales (IGN)"
          onClick={() => setShowCadastre((v) => !v)}
        >
          <md-icon>crop_landscape</md-icon>
          <md-icon slot="selected">crop_landscape</md-icon>
        </md-icon-button>
      </div>
    </div>
  );
}
