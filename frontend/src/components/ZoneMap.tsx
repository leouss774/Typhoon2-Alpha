// =============================================================================
//   TYPHOON — /zone : ZoneMap (OpenLayers, fond CARTO dark)
//   Reprend la logique du legacy zone.html : marqueur + popup + couches
//   WMS/WFS/cercle de repli, visibilité pilotée par visibleLayerKeys.
// =============================================================================

import { useEffect, useRef } from 'react';
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
import { easeIn } from 'ol/easing';
import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import Style from 'ol/style/Style';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import CircleStyle from 'ol/style/Circle';

import {
  WMS_BASE,
  WMS_LAYER_MAP,
  WFS_BASE,
  WFS_LAYER_MAP,
  bandForKey,
  escHtml,
  type RisqueReport,
} from '../zone/config';

type Layer = TileLayer | VectorLayer;

/** API impérative exposée au parent (Zone.tsx) pour l'animation d'approche. */
export interface ZoneMapApi {
  /**
   * Zoome sur le bâtiment (vue du dessus) en 1,2 s, easing OpenLayers.
   * @returns la largeur de sol (en mètres) couverte par la carte à
   *   l'arrivée — le jumeau 3D s'en sert pour démarrer au même cadrage.
   */
  zoomToBuilding(): Promise<number>;
}

interface ZoneMapProps {
  report: RisqueReport | null;
  visibleLayerKeys: ReadonlySet<string>;
  /** Clic (ou Entrée/Espace) sur le marqueur du bien → vol vers le jumeau. */
  onPinActivate?: () => void;
  apiRef?: React.MutableRefObject<ZoneMapApi | null>;
}

export function ZoneMap({ report, visibleLayerKeys, onPinActivate, apiRef }: ZoneMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<OLMap | null>(null);
  const viewRef = useRef<View | null>(null);
  const markerOverlayRef = useRef<Overlay | null>(null);
  const popupOverlayRef = useRef<Overlay | null>(null);
  const pinElRef = useRef<HTMLDivElement>(null);
  const popupElRef = useRef<HTMLDivElement>(null);
  const layersByKeyRef = useRef<Map<string, Layer[]>>(new Map());
  const renderSeqRef = useRef(0);
  const visibleKeysRef = useRef(visibleLayerKeys);
  visibleKeysRef.current = visibleLayerKeys;
  /* Callback toujours à jour, lue au moment du clic : le listener DOM du pin
     est posé une seule fois (init de la carte) et ne doit pas capturer une
     version périmée de la prop. */
  const onPinActivateRef = useRef(onPinActivate);
  onPinActivateRef.current = onPinActivate;
  const reportRef = useRef(report);
  reportRef.current = report;
  /* Vol d'approche en cours : neutralise le fly-to « zoom 14 » du rendu de
     rapport, qui sinon annulerait l'animation et couperait le zoom net. */
  const flyingRef = useRef(false);

  /* ── Init map (une seule fois) ── */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const cartoLayer = new TileLayer({
      source: new XYZ({
        urls: [
          'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
          'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        ],
        tileSize: 256,
        maxZoom: 19,
      }),
    });

    const view = new View({
      center: fromLonLat([2.35, 46.8]),
      zoom: 5,
      minZoom: 3,
      maxZoom: 19,
    });

    const pinEl = document.createElement('div');
    pinEl.className = 'map-pin';
    pinEl.style.display = 'none';
    /* Le marqueur est un bouton : sans affordance (curseur, survol, focus,
       intitulé), personne ne devine qu'il ouvre le jumeau 3D. */
    pinEl.setAttribute('role', 'button');
    pinEl.setAttribute('tabindex', '0');
    pinEl.setAttribute('aria-label', 'Ouvrir le jumeau numérique 3D de ce bien');
    pinEl.title = 'Ouvrir le jumeau numérique 3D de ce bien';
    const activate = () => onPinActivateRef.current?.();
    pinEl.addEventListener('click', (e) => {
      e.stopPropagation(); // ne pas déclencher aussi un clic carte
      activate();
    });
    pinEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        activate();
      }
    });
    container.appendChild(pinEl);
    pinElRef.current = pinEl;

    const popupEl = document.createElement('div');
    popupEl.id = 'ol-popup';
    popupEl.innerHTML = `
      <button type="button" id="ol-popup-closer" aria-label="Fermer">×</button>
      <div id="ol-popup-content"></div>
    `;
    container.appendChild(popupEl);
    popupElRef.current = popupEl;

    const markerOverlay = new Overlay({
      element: pinEl,
      positioning: 'center-center',
      stopEvent: false,
    });
    const popupOverlay = new Overlay({
      element: popupEl,
      positioning: 'bottom-center',
      stopEvent: true,
      autoPan: { animation: { duration: 250 } },
    });
    markerOverlayRef.current = markerOverlay;
    popupOverlayRef.current = popupOverlay;

    const map = new OLMap({
      target: container,
      layers: [cartoLayer],
      view,
      overlays: [markerOverlay, popupOverlay],
      controls: defaultControls({ attribution: false, rotate: false, zoom: true }),
    });
    mapRef.current = map;
    viewRef.current = view;

    popupEl.querySelector('#ol-popup-closer')!.addEventListener('click', () => {
      popupOverlay.setPosition(undefined);
      popupEl.classList.remove('visible');
    });

    return () => {
      map.setTarget(undefined);
      pinEl.remove();
      popupEl.remove();
      mapRef.current = null;
      viewRef.current = null;
      markerOverlayRef.current = null;
      popupOverlayRef.current = null;
      pinElRef.current = null;
      popupElRef.current = null;
      layersByKeyRef.current.clear();
    };
  }, []);

  /* ── API impérative : zoom d'approche sur le bâtiment ──
     Exposée au parent, qui enchaîne ensuite le morphing vers la section BIM. */
  useEffect(() => {
    if (!apiRef) return;
    apiRef.current = {
      zoomToBuilding() {
        const view = viewRef.current;
        const map = mapRef.current;
        const rep = reportRef.current;
        if (!view || !map || !rep) return Promise.resolve(0);

        flyingRef.current = true;
        const coord = fromLonLat([rep.lon, rep.lat]);
        const zoom = Math.min(19, view.getMaxZoom());
        /* Un fly-to du rendu de rapport peut encore courir : on l'annule,
           sinon il annulerait le nôtre et le callback tomberait aussitôt. */
        view.cancelAnimations();

        return new Promise<number>((resolve) => {
          let done = false;
          const finish = () => {
            if (done) return;
            done = true;
            window.clearTimeout(guard);
            /* Largeur de sol réellement couverte, en mètres.
               EPSG:3857 : la résolution est en mètres "Mercator", dilatés
               d'un facteur 1/cos(latitude) — sans cette correction on se
               tromperait de 34 % à Paris et le raccord d'échelle sauterait. */
            const res = view.getResolution() ?? 0;
            const widthPx = map.getSize()?.[0] ?? 0;
            const metres = res * Math.cos((rep.lat * Math.PI) / 180) * widthPx;
            flyingRef.current = false;
            resolve(metres > 0 ? metres : 0);
          };
          /* Filet de sécurité : les animations OpenLayers avancent au rythme
             de requestAnimationFrame, gelé si l'onglet passe en arrière-plan.
             Sans ce garde-fou, le callback ne viendrait jamais et la séquence
             resterait bloquée sur la carte. */
          const guard = window.setTimeout(finish, 1200 + 600);
          view.animate(
            { center: coord, zoom, duration: 1200, easing: easeIn },
            // Appelé aussi si l'animation est interrompue : on résout quand
            // même, le vol ne doit jamais rester bloqué.
            () => finish()
          );
        });
      },
    };
    return () => {
      apiRef.current = null;
    };
  }, [apiRef]);

  /* ── Appliquer la visibilité quand visibleLayerKeys change ── */
  useEffect(() => {
    for (const [key, layers] of layersByKeyRef.current) {
      const visible = visibleLayerKeys.has(key);
      for (const l of layers) l.setVisible(visible);
    }
  }, [visibleLayerKeys]);

  /* ── Rendu couches + marqueur/popup quand le rapport change ── */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Nettoyage des couches précédentes + invalidation de tout rendu en cours
    for (const layers of layersByKeyRef.current.values()) {
      for (const l of layers) map.removeLayer(l);
    }
    layersByKeyRef.current.clear();
    const seq = ++renderSeqRef.current;

    if (!report) {
      if (pinElRef.current) pinElRef.current.style.display = 'none';
      markerOverlayRef.current?.setPosition(undefined);
      popupOverlayRef.current?.setPosition(undefined);
      return;
    }

    // Marqueur + popup
    const coord = fromLonLat([report.lon, report.lat]);
    const pinEl = pinElRef.current;
    const popupEl = popupElRef.current;
    if (pinEl) pinEl.style.display = 'block';
    markerOverlayRef.current?.setPosition(coord);

    const topAleas = (report.aleas || [])
      .filter((a) => a.present === true && a.niveau)
      .map((a) => {
        const band = bandForKey(a.niveau);
        const color = band?.color ?? '#E8E6DC';
        const label = band?.label ?? a.niveau ?? '';
        return `<div class="pop-row"><span>${escHtml(a.libelle)}</span><span style="color:${color}">${label}</span></div>`;
      })
      .join('');

    const ignLink = `https://www.geoportail.gouv.fr/carte?lon=${report.lon}&lat=${report.lat}&z=18`;
    const osmLink = `https://www.openstreetmap.org/?mlat=${report.lat}&mlon=${report.lon}&zoom=18`;

    const contentEl = popupEl?.querySelector('#ol-popup-content');
    if (contentEl) {
      contentEl.innerHTML = `
        <div class="pop-title">${escHtml(report.adresse_normalisee)}</div>
        ${topAleas || '<div class="pop-row"><span>Aucun aléa présent</span><span>—</span></div>'}
        <div class="pop-links">
          <a href="${ignLink}" target="_blank" rel="noopener">IGN Géoportail</a>
          <a href="${osmLink}" target="_blank" rel="noopener">OpenStreetMap</a>
        </div>
      `;
    }
    popupEl?.classList.add('visible');
    popupOverlayRef.current?.setPosition(coord);

    if (!flyingRef.current) {
      viewRef.current?.animate({ center: coord, zoom: 14, duration: 1200 });
    }

    // Couches aléas (niveau 1 WMS → niveau 2 WFS → niveau 3 cercle)
    const renderLayers = async () => {
      for (const a of report.aleas || []) {
        if (seq !== renderSeqRef.current) return;
        const band = a.niveau ? bandForKey(a.niveau) : undefined;
        const color = band?.color || '#7A9187';

        const track = (key: string, layer: Layer) => {
          map.addLayer(layer);
          if (!layersByKeyRef.current.has(key)) layersByKeyRef.current.set(key, []);
          layersByKeyRef.current.get(key)!.push(layer);
        };

        if (WMS_LAYER_MAP[a.code]) {
          const layer = new TileLayer({
            source: new TileWMS({
              url: WMS_BASE,
              params: {
                SERVICE: 'WMS',
                VERSION: '1.3.0',
                LAYERS: WMS_LAYER_MAP[a.code],
                FORMAT: 'image/png',
                TRANSPARENT: 'true',
                CRS: 'EPSG:3857',
              },
              serverType: 'geoserver',
              crossOrigin: 'anonymous',
              transition: 300,
            }),
            opacity: 0.65,
          });
          layer.setVisible(visibleKeysRef.current.has(a.code));
          track(a.code, layer);
          continue;
        }

        if (WFS_LAYER_MAP[a.code]) {
          let wfsRendered = false;
          for (const typeName of WFS_LAYER_MAP[a.code]) {
            try {
              const geojson = await fetchWfsLayer(typeName, report.code_insee);
              if (seq !== renderSeqRef.current) return;
              if (!geojson || !geojson.features || !geojson.features.length) continue;
              const layer = buildVectorLayer(geojson, color);
          layer.setVisible(visibleKeysRef.current.has(a.code));
          track(a.code, layer);
          wfsRendered = true;
            } catch (err) {
              console.warn(`WFS indisponible pour ${typeName}:`, err);
            }
          }
          if (wfsRendered) continue;
        }

        const layer = buildCircleLayer(report.lon, report.lat, color);
        layer.setVisible(visibleKeysRef.current.has(a.code));
        track(a.code, layer);
      }
    };
    void renderLayers();
  }, [report]);

  return <div ref={containerRef} className="zone-map" />;
}

/* ── Helpers ── */

async function fetchWfsLayer(typeName: string, codeInsee: string): Promise<{ features?: unknown[] } | null> {
  const url = new URL(WFS_BASE);
  url.searchParams.set('SERVICE', 'WFS');
  url.searchParams.set('VERSION', '2.0.0');
  url.searchParams.set('REQUEST', 'GetFeature');
  url.searchParams.set('TYPENAMES', typeName);
  url.searchParams.set('OUTPUTFORMAT', 'application/json');
  url.searchParams.set('CQL_FILTER', `code_insee='${codeInsee}'`);
  url.searchParams.set('COUNT', '50');

  const resp = await fetch(url.toString());
  if (!resp.ok) throw new Error(`WFS ${typeName} HTTP ${resp.status}`);
  return (await resp.json()) as { features?: unknown[] };
}

function buildVectorLayer(geojson: { features?: unknown[] }, bandColor: string): VectorLayer {
  const format = new GeoJSON();
  const features = format.readFeatures(geojson as object, {
    dataProjection: 'EPSG:4326',
    featureProjection: 'EPSG:3857',
  });
  const source = new VectorSource({ features });
  return new VectorLayer({
    source,
    style: new Style({
      fill: new Fill({ color: bandColor + '55' }),
      stroke: new Stroke({ color: bandColor, width: 1.5 }),
    }),
  });
}

function buildCircleLayer(lon: number, lat: number, bandColor: string): VectorLayer {
  const feature = new Feature({
    geometry: new Point(fromLonLat([lon, lat])),
  });
  const source = new VectorSource({ features: [feature] });
  return new VectorLayer({
    source,
    style: new Style({
      image: new CircleStyle({
        radius: 46,
        fill: new Fill({ color: bandColor + '44' }),
        stroke: new Stroke({ color: bandColor, width: 1.5 }),
      }),
    }),
  });
}
