// =============================================================================
//   TYPHOON — /zone : couches de risque CesiumJS (portage Tier A).
//   Réutilise directement WMS_LAYER_MAP / WFS_LAYER_MAP / WMS_BASE / WFS_BASE
//   de src/zone/config.ts — une seule source de vérité pour la carte
//   OpenLayers (étape 2) et le globe Cesium (étape 4 « Vue terrain 3D »).
//
//   · WMS BRGM  → Cesium.WebMapServiceImageryProvider (drapé sur le terrain)
//   · WFS Géorisques (ssp) → Cesium.GeoJsonDataSource (fetch GeoJSON, même
//     pattern que ZoneMap.tsx)
//   · Toggle œil : imageryLayer.show / dataSource.show — même état
//     `visibleLayerKeys` que /zone.
// =============================================================================

import * as Cesium from 'cesium';
import {
  WMS_BASE,
  WMS_LAYER_MAP,
  WFS_BASE,
  WFS_LAYER_MAP,
  bandForKey,
  type AleaDetail,
} from '../zone/config';

export interface HazardLayer {
  code: string;
  libelle: string;
  kind: 'wms' | 'wfs';
  imageryLayer?: Cesium.ImageryLayer;
  dataSource?: Cesium.GeoJsonDataSource;
}

/** Applique l'état du toggle œil (équivalent Cesium de layer.setVisible()). */
export function setHazardLayerVisible(layer: HazardLayer, visible: boolean): void {
  if (layer.imageryLayer) layer.imageryLayer.show = visible;
  if (layer.dataSource) layer.dataSource.show = visible;
}

/** Couleur de la bande D03 de l'aléa (ou gris neutre par défaut). */
function bandColorFor(alea: AleaDetail): string {
  const band = alea.niveau ? bandForKey(alea.niveau) : undefined;
  return band?.color ?? '#7A9187';
}

/**
 * Monte les couches WMS/WFS des aléas du rapport sur le globe.
 * Toutes les couches sont ajoutées masquées ; la visibilité est pilotée
 * ensuite par `visibleLayerKeys` (état partagé avec l'étape 2).
 */
export async function buildHazardLayers(
  viewer: Cesium.Viewer,
  aleas: AleaDetail[],
  codeInsee: string
): Promise<HazardLayer[]> {
  const layers: HazardLayer[] = [];

  for (const alea of aleas) {
    const wmsLayerName = WMS_LAYER_MAP[alea.code];
    if (wmsLayerName) {
      try {
        const provider = new Cesium.WebMapServiceImageryProvider({
          url: WMS_BASE,
          layers: wmsLayerName,
          parameters: {
            transparent: 'true',
            format: 'image/png',
            tiled: 'true',
          },
          /* Échelle minimale : le WMS BRGM rejette les tuiles « monde entier »
             (zoom 0-4) — on évite des requêtes inutiles et du bruit de log. */
          minimumLevel: 5,
          enablePickFeatures: false,
          credit: `BRGM Géorisques — ${alea.libelle}`,
        });
        const imageryLayer = new Cesium.ImageryLayer(provider);
        viewer.imageryLayers.add(imageryLayer);
        imageryLayer.show = false;
        layers.push({ code: alea.code, libelle: alea.libelle, kind: 'wms', imageryLayer });
      } catch (err) {
        console.warn(`[cesium] WMS indisponible pour ${alea.code}:`, err);
      }
      continue;
    }

    if (WFS_LAYER_MAP[alea.code]) {
      for (const typeName of WFS_LAYER_MAP[alea.code]) {
        try {
          const dataSource = await loadWfsDataSource(typeName, codeInsee, bandColorFor(alea));
          if (dataSource) {
            viewer.dataSources.add(dataSource);
            dataSource.show = false;
            layers.push({ code: alea.code, libelle: alea.libelle, kind: 'wfs', dataSource });
          }
        } catch (err) {
          console.warn(`[cesium] WFS indisponible pour ${typeName}:`, err);
        }
      }
    }
  }

  return layers;
}

/** Fetch WFS Géorisques (même construction d'URL que ZoneMap.tsx) → GeoJSON. */
async function loadWfsDataSource(
  typeName: string,
  codeInsee: string,
  color: string
): Promise<Cesium.GeoJsonDataSource | null> {
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
  const geojson = (await resp.json()) as { features?: unknown[] };
  if (!geojson.features || geojson.features.length === 0) return null;

  return Cesium.GeoJsonDataSource.load(geojson, {
    stroke: Cesium.Color.fromCssColorString(color),
    strokeWidth: 2,
    fill: Cesium.Color.fromCssColorString(color).withAlpha(0.3),
    clampToGround: true,
  });
}
