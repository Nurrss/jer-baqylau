import type { StyleSpecification } from 'maplibre-gl'

/** Taraz and its surroundings. */
export const INITIAL_VIEW = { longitude: 71.362, latitude: 42.944, zoom: 12.3 }
export const REGION_BOUNDS: [[number, number], [number, number]] = [
  [69.0, 42.2],
  [75.5, 45.6],
]

/** Raster base layers (no API keys): OpenStreetMap and Esri World Imagery; toggled by visibility. */
export function baseStyle(): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
      },
      satellite: {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        maxzoom: 18,
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
      },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#e9eef3' } },
      { id: 'osm', type: 'raster', source: 'osm', layout: { visibility: 'visible' } },
      { id: 'satellite', type: 'raster', source: 'satellite', layout: { visibility: 'none' } },
    ],
  }
}
