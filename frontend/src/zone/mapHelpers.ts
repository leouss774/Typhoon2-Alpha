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
/* Le WFS Géorisques (GeoServer) ne sert que du GML — pas de JSON malgré
 * `outputFormat=application/json` (échoue silencieusement). On demande donc
 * du GML 3.2 et on le convertit nous-mêmes en GeoJSON (parser minimal :
 * gml:Point / gml:LineString / gml:Polygon / gml:MultiSurface, cf. réponse
 * réelle du service — élément wfs:member > <ms:Type> > ms:msGeometry). */

const GML_GEOMETRY_NAMES = new Set([
  'Point', 'LineString', 'Curve',
  'Polygon', 'Surface',
  'MultiPoint', 'MultiLineString', 'MultiCurve', 'MultiPolygon', 'MultiSurface',
]);

/** Vrai si le CRS utilise l'ordre d'axes (lat, lon) — cas des URN OGC pour
 *  EPSG:4326 (`urn:ogc:def:crs:EPSG::4326`), conformément à GML 3.2 / WFS 2.0. */
function isLatLonAxisOrder(srsName: string | null | undefined): boolean {
  if (!srsName) return false;
  return /^urn:/i.test(srsName) && /4326/.test(srsName);
}

function descendantsByLocalName(root: Element, name: string): Element[] {
  const out: Element[] = [];
  const walk = (el: Element) => {
    for (const child of Array.from(el.children)) {
      if (child.localName === name) out.push(child);
      walk(child);
    }
  };
  walk(root);
  return out;
}

function firstDescendantByLocalName(root: Element, name: string): Element | null {
  return descendantsByLocalName(root, name)[0] ?? null;
}

/** Premier élément géométrie GML rencontré en largeur (évite de prendre un
 *  gml:Polygon imbriqué dans un gml:MultiSurface à la place du MultiSurface). */
function firstGeometryDescendant(root: Element): Element | null {
  const queue: Element[] = Array.from(root.children);
  while (queue.length) {
    const el = queue.shift()!;
    if (GML_GEOMETRY_NAMES.has(el.localName)) return el;
    queue.push(...Array.from(el.children));
  }
  return null;
}

/** Parse une liste de coordonnées GML (`gml:posList`, ou une paire `gml:pos`)
 *  en tenant compte de l'ordre d'axes du CRS. */
function parseCoordText(text: string, srsName: string | null): Array<[number, number]> {
  const nums = (text || '').trim().split(/\s+/).map(Number).filter((n) => !Number.isNaN(n));
  const swap = isLatLonAxisOrder(srsName);
  const pts: Array<[number, number]> = [];
  for (let i = 0; i + 1 < nums.length; i += 2) {
    const a = nums[i];
    const b = nums[i + 1];
    pts.push(swap ? [b, a] : [a, b]);
  }
  return pts;
}

/** Coordonnées d'un anneau (`gml:LinearRing`) ou d'une ligne — supporte
 *  `gml:posList`, la variante legacy `gml:coordinates`, et une suite de
 *  `gml:pos`. */
function ringOrLineCoords(el: Element, inheritedSrs: string | null): Array<[number, number]> | null {
  const srs = el.getAttribute('srsName') || inheritedSrs;
  const posList = firstDescendantByLocalName(el, 'posList');
  if (posList) {
    const pts = parseCoordText(posList.textContent || '', posList.getAttribute('srsName') || srs);
    return pts.length ? pts : null;
  }
  const coordinates = firstDescendantByLocalName(el, 'coordinates');
  if (coordinates) {
    const pts = (coordinates.textContent || '')
      .trim()
      .split(/\s+/)
      .map((pair) => pair.split(',').map(Number) as [number, number])
      .filter(([x, y]) => !Number.isNaN(x) && !Number.isNaN(y));
    return pts.length ? pts : null;
  }
  const posEls = descendantsByLocalName(el, 'pos');
  if (posEls.length) {
    const pts = posEls
      .map((p) => parseCoordText(p.textContent || '', p.getAttribute('srsName') || srs)[0])
      .filter((p): p is [number, number] => !!p);
    return pts.length ? pts : null;
  }
  return null;
}

function closeRing(ring: Array<[number, number]>): Array<[number, number]> {
  if (ring.length < 2) return ring;
  const [fx, fy] = ring[0];
  const [lx, ly] = ring[ring.length - 1];
  return fx === lx && fy === ly ? ring : [...ring, ring[0]];
}

function polygonRings(
  polygonEl: Element,
  inheritedSrs: string | null
): { exterior: Array<[number, number]>; interiors: Array<[number, number]>[] } | null {
  const srs = polygonEl.getAttribute('srsName') || inheritedSrs;
  const exteriorWrap = firstDescendantByLocalName(polygonEl, 'exterior');
  const ext = exteriorWrap
    ? firstDescendantByLocalName(exteriorWrap, 'LinearRing')
    : firstDescendantByLocalName(polygonEl, 'LinearRing');
  if (!ext) return null;
  const exterior = ringOrLineCoords(ext, srs);
  if (!exterior || exterior.length < 3) return null;
  const interiors: Array<[number, number]>[] = [];
  for (const interiorWrap of descendantsByLocalName(polygonEl, 'interior')) {
    const ring = firstDescendantByLocalName(interiorWrap, 'LinearRing');
    const coords = ring ? ringOrLineCoords(ring, srs) : null;
    if (coords && coords.length >= 3) interiors.push(closeRing(coords));
  }
  return { exterior: closeRing(exterior), interiors };
}

/** Convertit un élément géométrie GML (Point/LineString/Polygon/Multi*) en
 *  géométrie GeoJSON. Couvre les cas rencontrés dans les couches Géorisques
 *  (2-3 attributs utiles suffisent, on ne cherche pas l'exhaustivité GML). */
function gmlGeometryToGeoJson(geomEl: Element, inheritedSrs: string | null): GeoJSON.Geometry | null {
  const srs = geomEl.getAttribute('srsName') || inheritedSrs;
  switch (geomEl.localName) {
    case 'Point': {
      const pos = firstDescendantByLocalName(geomEl, 'pos');
      const pt = pos ? parseCoordText(pos.textContent || '', pos.getAttribute('srsName') || srs)[0] : null;
      return pt ? { type: 'Point', coordinates: pt } : null;
    }
    case 'LineString':
    case 'Curve': {
      const coords = ringOrLineCoords(geomEl, srs);
      return coords && coords.length >= 2 ? { type: 'LineString', coordinates: coords } : null;
    }
    case 'Polygon':
    case 'Surface': {
      const rings = polygonRings(geomEl, srs);
      return rings ? { type: 'Polygon', coordinates: [rings.exterior, ...rings.interiors] } : null;
    }
    case 'MultiSurface':
    case 'MultiPolygon': {
      const coordinates: number[][][][] = [];
      for (const p of descendantsByLocalName(geomEl, 'Polygon')) {
        const rings = polygonRings(p, srs);
        if (rings) coordinates.push([rings.exterior, ...rings.interiors] as unknown as number[][][]);
      }
      return coordinates.length ? { type: 'MultiPolygon', coordinates } : null;
    }
    case 'MultiCurve':
    case 'MultiLineString': {
      const coordinates: number[][][] = [];
      for (const l of descendantsByLocalName(geomEl, 'LineString')) {
        const coords = ringOrLineCoords(l, srs);
        if (coords && coords.length >= 2) coordinates.push(coords as unknown as number[][]);
      }
      return coordinates.length ? { type: 'MultiLineString', coordinates } : null;
    }
    case 'MultiPoint': {
      const coordinates: number[][] = [];
      for (const p of descendantsByLocalName(geomEl, 'Point')) {
        const pos = firstDescendantByLocalName(p, 'pos');
        const pt = pos ? parseCoordText(pos.textContent || '', pos.getAttribute('srsName') || srs)[0] : null;
        if (pt) coordinates.push(pt as unknown as number[]);
      }
      return coordinates.length ? { type: 'MultiPoint', coordinates } : null;
    }
    default:
      return null;
  }
}

function elementContains(ancestor: Element, target: Element): boolean {
  let node: Element | null = target;
  while (node) {
    if (node === ancestor) return true;
    node = node.parentElement;
  }
  return false;
}

/** Convertit une réponse WFS GetFeature (GML 3.2) en FeatureCollection
 *  GeoJSON. Ne garde que la géométrie + les propriétés scalaires du feature
 *  (pas de types complexes imbriqués) — suffisant pour le rendu carte. */
export function gmlToGeoJson(xmlText: string): GeoJSON.FeatureCollection | null {
  let doc: Document;
  try {
    doc = new DOMParser().parseFromString(xmlText, 'text/xml');
  } catch {
    return null;
  }
  if (doc.getElementsByTagName('parsererror').length) return null;
  const root = doc.documentElement;
  if (!root) return null;

  const members = [
    ...descendantsByLocalName(root, 'member'),
    ...descendantsByLocalName(root, 'featureMember'),
  ];
  const features: GeoJSON.Feature[] = [];
  for (const member of members) {
    const featureEl = member.children[0];
    if (!featureEl) continue;
    const geomEl = firstGeometryDescendant(featureEl);
    const geometry = geomEl ? gmlGeometryToGeoJson(geomEl, null) : null;
    if (!geometry) continue;
    const properties: Record<string, string> = {};
    for (const child of Array.from(featureEl.children)) {
      if (child.localName === 'boundedBy') continue;
      if (geomEl && elementContains(child, geomEl)) continue;
      const text = (child.textContent || '').trim();
      if (text) properties[child.localName] = text;
    }
    features.push({ type: 'Feature', geometry, properties });
  }
  return { type: 'FeatureCollection', features };
}

/** Bbox [west, south, east, north] (degrés WGS84) centrée sur un point, avec
 *  une marge fixe — utilisée pour restreindre les requêtes WFS au voisinage
 *  de l'adresse diagnostiquée. */
export function bboxAround(lon: number, lat: number, marginDeg = 0.012): [number, number, number, number] {
  return [lon - marginDeg, lat - marginDeg, lon + marginDeg, lat + marginDeg];
}

/** Bbox [west, south, east, north] centrée sur un point, avec une marge en
 *  **mètres** (approximation sphérique — largement suffisante à l'échelle
 *  d'un rayon de quelques centaines de mètres) : ÷111320 pour la latitude,
 *  ÷(111320·cos(lat)) pour la longitude (la longueur d'un degré de longitude
 *  se réduit avec la latitude). Utilisée par le mode carte « Bâtiments »
 *  (rayon ~100 m autour de l'adresse), distincte de `bboxAround` qui couvre
 *  une zone plus large (~1,2 km) pour les périmètres PPR/canalisations. */
export function bboxAroundMeters(lon: number, lat: number, meters: number): [number, number, number, number] {
  const dLat = meters / 111_320;
  const dLon = meters / (111_320 * Math.cos((lat * Math.PI) / 180));
  return [lon - dLon, lat - dLat, lon + dLon, lat + dLat];
}

/** Point-en-polygone par ray casting (algorithme standard, anneau extérieur
 *  uniquement — les trous ne sont pas pris en compte, approximation
 *  acceptable pour attribuer un bâtiment à une zone de risque). */
export function pointInPolygon(point: [number, number], ring: Array<[number, number]>): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

/** Vrai si `point` tombe dans l'empreinte d'une feature GeoJSON
 *  Polygon/MultiPolygon (teste chaque anneau extérieur des polygones qui la
 *  composent) — utilisé pour attribuer à chaque bâtiment le niveau D03 de la
 *  zone de risque (PPR/canalisations/SSP) dans laquelle il se trouve. */
export function featureContainsPoint(feature: GeoJSON.Feature, point: [number, number]): boolean {
  const geom = feature.geometry;
  if (!geom) return false;
  if (geom.type === 'Polygon') {
    return pointInPolygon(point, geom.coordinates[0] as Array<[number, number]>);
  }
  if (geom.type === 'MultiPolygon') {
    return geom.coordinates.some((poly) => pointInPolygon(point, poly[0] as Array<[number, number]>));
  }
  return false;
}

/** Récupère une couche WFS Géorisques en GeoJSON (GML→GeoJSON, cf. ci-dessus).
 *
 *  Filtre spatial (`BBOX`) plutôt qu'attributaire : vérifié en direct sur le
 *  service, `cql_filter=code_insee='...'` est silencieusement ignoré (les
 *  résultats ne varient pas avec le filtre — bug latent qui faisait
 *  remonter des features d'une commune quelconque). De plus, le nom du champ
 *  commune varie selon la couche (`code_insee` pour SSP, `num_com` pour les
 *  canalisations, absent pour les périmètres PPR) : `BBOX` est le seul filtre
 *  qui fonctionne uniformément quelle que soit la couche interrogée. */
export async function fetchWfsLayer(
  typeName: string,
  bbox: [number, number, number, number]
): Promise<GeoJSON.FeatureCollection | null> {
  const [west, south, east, north] = bbox;
  const url = new URL(WFS_BASE);
  url.searchParams.set('SERVICE', 'WFS');
  url.searchParams.set('VERSION', '2.0.0');
  url.searchParams.set('REQUEST', 'GetFeature');
  url.searchParams.set('TYPENAMES', typeName);
  url.searchParams.set('outputFormat', 'text/xml; subtype=gml/3.2.1');
  url.searchParams.set('count', '200');
  // Ordre d'axes (lat, lon) — URN EPSG:4326 en GML 3.2 / WFS 2.0 (cf. isLatLonAxisOrder).
  url.searchParams.set('BBOX', `${south},${west},${north},${east},urn:ogc:def:crs:EPSG::4326`);
  try {
    const resp = await fetch(url.toString());
    if (!resp.ok) return null;
    const text = await resp.text();
    return gmlToGeoJson(text);
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