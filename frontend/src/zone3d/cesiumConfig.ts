// =============================================================================
//   TYPHOON — /zone : configuration CesiumJS (terrain + imagerie de fond).
//   Sources publiques et gratuites par défaut — aucune clé requise :
//     · Relief    : Esri World Elevation3D (quantized-mesh, couverture
//                   mondiale, libre d'accès) — la vue « recul » sur le relief.
//     · Imagerie  : CARTO dark_all (mêmes tuiles que la carte OpenLayers
//                   de l'étape 2, cohérence visuelle avec le thème sombre).
//   Si VITE_CESIUM_ION_TOKEN est fourni, on bascule sur Cesium ion
//   (terrain mondial + imagerie satellite) — choix documenté §2.3 du plan
//   d'implémentation, repli automatique sur les sources publiques sinon.
// =============================================================================

import * as Cesium from 'cesium';

const ION_TOKEN: string = (import.meta as any).env?.VITE_CESIUM_ION_TOKEN || '';

if (ION_TOKEN) {
  Cesium.Ion.defaultAccessToken = ION_TOKEN;
}

/** Vrai si un token Cesium ion a été fourni (VITE_CESIUM_ION_TOKEN). */
export const HAS_ION = Boolean(ION_TOKEN);

/** Altitude de prise de vue initiale (m) — vue « recul » sur le bassin versant. */
export const FLY_TO_HEIGHT = 2800;

/** Relief : Cesium ion (si token) → sinon Esri World Elevation3D (gratuit). */
export async function createTerrainProvider(): Promise<Cesium.TerrainProvider> {
  if (HAS_ION) {
    try {
      return await Cesium.createWorldTerrainAsync();
    } catch (err) {
      console.warn('[cesium] ion terrain indisponible — repli Esri :', err);
    }
  }
  return Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(
    'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer'
  );
}

/** Imagerie de fond : ion (si token) → sinon CARTO dark_all (comme /zone). */
export async function createBaseImagery(): Promise<Cesium.ImageryProvider> {
  if (HAS_ION) {
    try {
      return await Cesium.createWorldImageryAsync();
    } catch (err) {
      console.warn('[cesium] ion imagerie indisponible — repli CARTO :', err);
    }
  }
  return new Cesium.UrlTemplateImageryProvider({
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
    subdomains: ['a', 'b', 'c', 'd'],
    credit: '© CARTO · © OpenStreetMap contributors',
    maximumLevel: 19,
  });
}
