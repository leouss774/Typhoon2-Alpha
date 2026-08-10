// =============================================================================
//   TYPHOON — Helpers cartographiques partagés (MapLibre / Mapbox)
//   Fonctions utilitaires partagées de la carte (ex-ZoneMap.tsx, désormais Mapbox)
//   dépendance cyclique après la migration vers Mapbox en moteur unique.
// =============================================================================

import { WMS_BASE, WFS_BASE } from '../zone/config';

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
  codeInsee: string
): Promise<{ features?: unknown[] } | null> {
  const url = new URL(WFS_BASE);
  url.searchParams.set('SERVICE', 'WFS');
  url.searchParams.set('VERSION', '2.0.0');
  url.searchParams.set('REQUEST', 'GetFeature');
  url.searchParams.set('TYPENAMES', typeName);
  url.searchParams.set('outputFormat', 'application/json');
  url.searchParams.set('count', '100');
  url.searchParams.set('cql_filter', `code_insee='${codeInsee}'`);
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