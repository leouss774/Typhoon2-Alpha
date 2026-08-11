// =============================================================================
//   TYPHOON — Helpers cartographiques partagés (MapLibre / Mapbox)
//   Fonctions utilitaires partagées de la carte (ex-ZoneMap.tsx, désormais Mapbox)
//   dépendance cyclique après la migration vers Mapbox en moteur unique.
// =============================================================================

import { WMS_BASE, WFS_BASE, WFS_JSON_FORMAT } from '../zone/config';

/* ── CRS / Laplace ── */

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

function lambert93ToWgs84(x: number, y: number): [number, number] {
  // Lambert-93 (RGF93) → WGS84 (approximation standard)
  const x0 = 700_000;
  const y0 = 12_655_600;
  const c = 11754255.426;
  const n = 0.725607765;
  const e = 0.08181919106; // GRS80 (premiere excentricite)
  const dx = x - x0;
  const dy = y - y0;
  const r = Math.sqrt(dx * dx + dy * dy);
  // Theta = angle polaire (petit angle positif = est du meridien origine).
  const gamma = Math.atan2(dx, -dy);
  const lon = (gamma / n) * (180 / Math.PI) + 3; // 3° E (meridien de reference)
  const lat = 2 * Math.atan(Math.pow(c / r, 1 / n)) - Math.PI / 2;
  let lat2 = lat;
  for (let i = 0; i < 5; i++) {
    lat2 = 2 * Math.atan(Math.pow(c / r, 1 / n) * Math.pow((1 + e * Math.sin(lat2)) / (1 - e * Math.sin(lat2)), e / 2)) - Math.PI / 2;
  }
  return [lon, (lat2 * 180) / Math.PI];
}

/** Convertit une géométrie BDNB (Lambert-93 → WGS84 si nécessaire). */
export function geomToWgs84(
  geom: Record<string, unknown> | null | undefined
): Record<string, unknown> | null {
  if (!geom || typeof geom !== 'object') return null;
  const crs = geom.crs as { properties?: { name?: unknown } } | undefined;
  const crsName = String(crs?.properties?.name || '');
  const is4326 = /4326|CRS84/i.test(crsName);
  const coords = geom.coordinates as unknown;
  if (!is4326) {
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

/* ── URL des tuiles ── */

export const CADASTRE_WMS =
  'https://data.geopf.fr/wms-r/wms';

/** URL des tuiles cadastrales IGN (WMS). */
export function cadastreTileUrl(): string {
  const params = new URLSearchParams({
    service: 'WMS',
    version: '1.3.0',
    request: 'GetMap',
    layers: 'CADASTRALPARCELS.PARCELLAIRE_EXPRESS',
    styles: '',
    format: 'image/png',
    transparent: 'true',
    width: '256',
    height: '256',
    crs: 'EPSG:3857',
  });
  return `${CADASTRE_WMS}?${params.toString()}&bbox={bbox-epsg-3857}`;
}

/** URL des tuiles WMS BRGM pour une couche donnée. */
export function wmsTileUrl(layerName: string): string {
  const params = new URLSearchParams({
    service: 'WMS',
    version: '1.3.0',
    request: 'GetMap',
    layers: layerName,
    format: 'image/png',
    transparent: 'true',
    width: '256',
    height: '256',
    crs: 'EPSG:3857',
  });
  return `${WMS_BASE}?${params.toString()}&bbox={bbox-epsg-3857}`;
}

/* ── WFS ── */

/** Récupère une couche WFS Géorisques en GeoJSON. */
export async function fetchWfsLayer(
  typeName: string,
  codeInsee: string,
  opts: { filterAttr?: string; count?: number } = {}
): Promise<{ features?: unknown[] } | null> {
  const { filterAttr = 'code_insee', count = 100 } = opts;
  const url = new URL(WFS_BASE);
  url.searchParams.set('SERVICE', 'WFS');
  url.searchParams.set('VERSION', '2.0.0');
  url.searchParams.set('REQUEST', 'GetFeature');
  url.searchParams.set('TYPENAMES', typeName);
  // Le WFS Géorisques refuse outputFormat=application/json sur la plupart des
  // couches — le format GeoJSON explicite est accepté par toutes.
  url.searchParams.set('outputFormat', WFS_JSON_FORMAT);
  url.searchParams.set('count', String(count));
  url.searchParams.set('cql_filter', `${filterAttr}='${codeInsee}'`);
  try {
    const resp = await fetch(url.toString());
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/* ── Géométrie ── */

/** Centre approximatif d'un Polygon/MultiPolygon GeoJSON (en WGS84). */
export function polygonCenter(
  coords: unknown
): [number, number] | null {
  const ring = firstRing(coords);
  if (!ring || ring.length < 3) return null;
  let lon = 0;
  let lat = 0;
  for (const p of ring) {
    lon += p[0];
    lat += p[1];
  }
  return [lon / ring.length, lat / ring.length];
}

/** Tous les anneaux d'une géométrie Polygon/MultiPolygon GeoJSON. */
export function geometryRings(geom: {
  type?: string;
  coordinates?: unknown;
} | null | undefined): number[][][] {
  if (!geom || !geom.type || !Array.isArray(geom.coordinates)) return [];
  if (geom.type === 'Polygon') return geom.coordinates as number[][][];
  if (geom.type === 'MultiPolygon') return (geom.coordinates as number[][][][]).flat();
  return [];
}

/** Points de test d'une empreinte de bâtiment (sommets + centroïde). */
export function buildingSamplePoints(
  geom: { type?: string; coordinates?: unknown } | null | undefined
): Array<[number, number]> {
  const pts: Array<[number, number]> = [];
  for (const ring of geometryRings(geom)) {
    for (const p of ring) pts.push([p[0], p[1]]);
  }
  const c = polygonCenter(geom?.coordinates);
  if (c) pts.push(c);
  return pts;
}

/* ── Échantillonnage WMS pour la coloration des bâtiments par aléa ── */

/** Conversion WGS84 → Web Mercator (EPSG:3857). */
export function wgs84ToWebMercator(lon: number, lat: number): [number, number] {
  const x = (lon * 20037508.34) / 180;
  const y =
    (Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) / (Math.PI / 180)) *
    (20037508.34 / 180);
  return [x, y];
}

export interface RiskZoneImage {
  width: number;
  height: number;
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
  /** Pixels RGBA bruts (getImageData). */
  data: Uint8ClampedArray;
}

/** GetMap WMS (transparent, bbox 3857) → pixels RGBA décodés en canvas. */
export async function fetchRiskZoneImage(
  layer: string,
  bbox3857: [number, number, number, number],
  size = 512
): Promise<RiskZoneImage | null> {
  const [xmin, ymin, xmax, ymax] = bbox3857;
  const params = new URLSearchParams({
    service: 'WMS',
    version: '1.3.0',
    request: 'GetMap',
    layers: layer,
    format: 'image/png',
    transparent: 'true',
    width: String(size),
    height: String(size),
    crs: 'EPSG:3857',
    bbox: `${xmin},${ymin},${xmax},${ymax}`,
  });
  try {
    const resp = await fetch(`${WMS_BASE}?${params.toString()}`);
    if (!resp.ok) return null;
    const blob = await resp.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      bitmap.close();
      return null;
    }
    ctx.drawImage(bitmap, 0, 0);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    bitmap.close();
    return {
      width: canvas.width,
      height: canvas.height,
      xmin,
      ymin,
      xmax,
      ymax,
      data: img.data,
    };
  } catch {
    return null;
  }
}

/** Couleur dominante (hex #rrggbb) de la couche WMS à la position d'un point,
 *  ou null si le point est hors zone (pixels transparents). Les pixels non
 *  transparents du voisinage tolPx sont moyennés (anti-alias des bords) —
 *  c'est « la couleur de la couche WFS/WMS » à cet endroit, utilisée pour
 *  colorer le bâtiment comme la zone (vert/orange/rouge selon la légende de
 *  la couche). tolPx : rayon en pixels (0-2 pour zonages, ~10 pour points). */
export function riskPixelColor(
  img: RiskZoneImage,
  lon: number,
  lat: number,
  tolPx: number
): string | null {
  const [mx, my] = wgs84ToWebMercator(lon, lat);
  const px = ((mx - img.xmin) / (img.xmax - img.xmin)) * img.width;
  const py = ((img.ymax - my) / (img.ymax - img.ymin)) * img.height;
  if (px < 0 || py < 0 || px >= img.width || py >= img.height) return null;
  const r = Math.max(0, Math.min(Math.round(tolPx), 24));
  const x0 = Math.max(0, Math.floor(px - r));
  const x1 = Math.min(img.width - 1, Math.ceil(px + r));
  const y0 = Math.max(0, Math.floor(py - r));
  const y1 = Math.min(img.height - 1, Math.ceil(py + r));
  let rr = 0, gg = 0, bb = 0, n = 0;
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const i = (y * img.width + x) * 4;
      if (img.data[i + 3] > 20) {
        rr += img.data[i];
        gg += img.data[i + 1];
        bb += img.data[i + 2];
        n++;
      }
    }
  }
  if (!n) return null;
  const hex = (v: number) => Math.round(v / n).toString(16).padStart(2, '0');
  return `#${hex(rr)}${hex(gg)}${hex(bb)}`;
}

/** Un point (bâtiment) tombe-t-il sur la zone de risque (pixels non transparents) ?
 *  Déclinaison de riskPixelColor : hors zone → false. */
export function riskPixelHits(
  img: RiskZoneImage,
  lon: number,
  lat: number,
  tolPx: number
): boolean {
  return riskPixelColor(img, lon, lat, tolPx) !== null;
}

/** Premier anneau externe d'un Polygon/MultiPolygon. */
export function firstRing(
  node: unknown
): Array<[number, number]> | null {
  if (!Array.isArray(node)) return null;
  if (node.length >= 3 && Array.isArray(node[0]) && typeof node[0][0] === 'number') {
    return node as Array<[number, number]>;
  }
  for (const sub of node) {
    const r = firstRing(sub);
    if (r) return r;
  }
  return null;
}