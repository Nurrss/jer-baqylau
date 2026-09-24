import type {
  DataDrivenPropertyValueSpecification,
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
} from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MapGL, {
  Layer,
  NavigationControl,
  Popup,
  ScaleControl,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import type { ParcelFeatureCollection, ParcelProperties, SignalSummary } from '@/api/types'
import { NDVI_STOPS, PARCEL_STATUS_COLORS, SIGNAL_STATUS_COLORS } from '@/lib/status'
import { formatArea } from '@/lib/utils'
import { useUiStore } from '@/store/ui'
import { buildParcelFilter } from './filters'
import { baseStyle, INITIAL_VIEW, REGION_BOUNDS } from './mapStyle'

const PARCEL_LAYERS = ['parcels-fill'] as const
const SIGNAL_LAYERS = ['signal-point', 'signal-clusters'] as const

function statusColor(): ExpressionSpecification {
  const pairs = Object.entries(PARCEL_STATUS_COLORS).flat()
  return ['match', ['get', 'status'], ...pairs, '#94a3b8'] as unknown as ExpressionSpecification
}

function ndviColor(): ExpressionSpecification {
  return [
    'case',
    ['==', ['typeof', ['get', 'ndvi']], 'number'],
    ['interpolate', ['linear'], ['get', 'ndvi'], ...NDVI_STOPS.flat()],
    '#94a3b8',
  ] as unknown as ExpressionSpecification
}

interface HoverInfo {
  lng: number
  lat: number
  parcel: ParcelProperties
}

interface Props {
  parcels: ParcelFeatureCollection | undefined
  signals: SignalSummary[]
  onSelectParcel: (id: string) => void
  onSelectSignal: (id: string) => void
}

export function ParcelMap({ parcels, signals, onSelectParcel, onSelectSignal }: Props) {
  const { t, i18n } = useTranslation()
  const mapRef = useRef<MapRef>(null)
  const [loaded, setLoaded] = useState(false)
  const [hover, setHover] = useState<HoverInfo | null>(null)
  const hoveredId = useRef<string | null>(null)
  const {
    basemap,
    ndviLayer,
    signalsLayer,
    filters,
    selectedParcelId,
    selectedSignalId,
    flyTarget,
    freshSignalIds,
    theme,
  } = useUiStore()

  const style = useMemo(() => baseStyle(), [])
  const parcelFilter = useMemo(() => buildParcelFilter(filters), [filters])

  const signalsGeoJson = useMemo(
    () => ({
      type: 'FeatureCollection' as const,
      features: signals
        .filter((s) => s.status !== 'REJECTED')
        .map((s) => ({
          type: 'Feature' as const,
          geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] },
          properties: {
            id: s.id,
            status: s.status,
            code: s.tracking_code,
            reports: s.reports_count,
            fresh: freshSignalIds.includes(s.id),
          },
        })),
    }),
    [signals, freshSignalIds],
  )

  // Basemap switch + dimming in dark theme.
  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!map || !loaded) return
    map.setLayoutProperty('osm', 'visibility', basemap === 'osm' ? 'visible' : 'none')
    map.setLayoutProperty('satellite', 'visibility', basemap === 'satellite' ? 'visible' : 'none')
    map.setPaintProperty('osm', 'raster-brightness-max', theme === 'dark' ? 0.72 : 1)
    map.setPaintProperty('osm', 'raster-saturation', theme === 'dark' ? -0.35 : 0)
  }, [basemap, theme, loaded])

  // Fly to a requested target (search result, toast "show on map", signal queue).
  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyTarget) return
    if (flyTarget.bbox) {
      const [x0, y0, x1, y1] = flyTarget.bbox
      map.fitBounds(
        [
          [x0, y0],
          [x1, y1],
        ],
        { padding: { top: 80, bottom: 80, left: 80, right: 460 }, maxZoom: 17.5, duration: 1200 },
      )
    } else if (flyTarget.center) {
      map.flyTo({ center: flyTarget.center, zoom: flyTarget.zoom ?? 16, duration: 1200, offset: [-180, 0] })
    }
  }, [flyTarget])

  // Pulsing halo for NEW signals (animated paint property; works with clustering).
  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!map || !loaded) return
    let frame = 0
    const animate = (now: number) => {
      if (map.getLayer('signal-pulse')) {
        const phase = (now % 1600) / 1600
        map.setPaintProperty('signal-pulse', 'circle-radius', [
          'case',
          ['==', ['get', 'fresh'], true],
          10 + phase * 34,
          8 + phase * 18,
        ])
        map.setPaintProperty('signal-pulse', 'circle-opacity', 0.55 * (1 - phase))
      }
      frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [loaded])

  const setHoverState = (id: string | null) => {
    const map = mapRef.current?.getMap()
    if (!map?.getSource('parcels')) return
    if (hoveredId.current) map.setFeatureState({ source: 'parcels', id: hoveredId.current }, { hover: false })
    hoveredId.current = id
    if (id) map.setFeatureState({ source: 'parcels', id }, { hover: true })
  }

  const onMouseMove = (event: MapLayerMouseEvent) => {
    const feature = event.features?.[0]
    if (feature && feature.layer.id === 'parcels-fill') {
      const props = feature.properties as unknown as ParcelProperties
      setHoverState(props.id)
      setHover({ lng: event.lngLat.lng, lat: event.lngLat.lat, parcel: props })
    } else {
      setHoverState(null)
      setHover(null)
    }
  }

  const onClick = async (event: MapLayerMouseEvent) => {
    const feature = event.features?.[0]
    if (!feature) return
    const map = mapRef.current?.getMap()
    if (feature.layer.id === 'signal-clusters' && map) {
      const source = map.getSource('signals') as GeoJSONSource
      const zoom = await source.getClusterExpansionZoom(feature.properties.cluster_id as number)
      const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates
      map.easeTo({ center: [lng, lat], zoom: zoom + 0.5 })
      return
    }
    if (feature.layer.id === 'signal-point') onSelectSignal(feature.properties.id as string)
    else if (feature.layer.id === 'parcels-fill') onSelectParcel(feature.properties.id as string)
  }

  const interactiveLayerIds = signalsLayer ? [...SIGNAL_LAYERS, ...PARCEL_LAYERS] : [...PARCEL_LAYERS]
  const fillColor = (ndviLayer ? ndviColor() : statusColor()) as DataDrivenPropertyValueSpecification<string>

  return (
    <MapGL
      ref={mapRef}
      initialViewState={INITIAL_VIEW}
      mapStyle={style}
      maxBounds={REGION_BOUNDS.flat() as [number, number, number, number]}
      minZoom={7}
      maxZoom={19}
      interactiveLayerIds={interactiveLayerIds}
      onMouseMove={onMouseMove}
      onMouseLeave={() => {
        setHoverState(null)
        setHover(null)
      }}
      onClick={(e) => void onClick(e)}
      onLoad={() => setLoaded(true)}
      cursor={hover ? 'pointer' : 'grab'}
      attributionControl={{ compact: true }}
      style={{ width: '100%', height: '100%' }}
    >
      <NavigationControl position="bottom-right" showCompass={false} />
      <ScaleControl position="bottom-right" unit="metric" />

      {parcels && (
        <Source id="parcels" type="geojson" data={parcels} promoteId="id">
          <Layer
            id="parcels-fill"
            type="fill"
            filter={parcelFilter}
            paint={{
              'fill-color': fillColor,
              'fill-opacity': [
                'case',
                ['boolean', ['feature-state', 'hover'], false],
                0.62,
                ['==', ['get', 'id'], selectedParcelId ?? ''],
                0.6,
                ['==', ['get', 'status'], 'IN_REMEDIATION'],
                0.26,
                ndviLayer ? 0.62 : 0.38,
              ],
            }}
          />
          <Layer
            id="parcels-outline"
            type="line"
            filter={['all', parcelFilter, ['!=', ['get', 'status'], 'IN_REMEDIATION']] as FilterSpecification}
            paint={{
              'line-color': ndviLayer ? '#1f2937' : statusColor(),
              'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.6, 16, 1.8],
              'line-opacity': ndviLayer ? 0.45 : 0.95,
            }}
          />
          <Layer
            id="parcels-outline-dashed"
            type="line"
            filter={['all', parcelFilter, ['==', ['get', 'status'], 'IN_REMEDIATION']] as FilterSpecification}
            paint={{
              'line-color': ndviLayer ? '#1f2937' : PARCEL_STATUS_COLORS.IN_REMEDIATION,
              'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1, 16, 2.4],
              'line-dasharray': [2, 1.5],
            }}
          />
          {ndviLayer && (
            <Layer
              id="parcels-ndvi-flagged"
              type="line"
              filter={['all', parcelFilter, ['==', ['get', 'ndvi_flagged'], true]] as FilterSpecification}
              paint={{ 'line-color': '#f97316', 'line-width': 3.2, 'line-dasharray': [1, 1] }}
            />
          )}
          <Layer
            id="parcels-selected"
            type="line"
            filter={['==', ['get', 'id'], selectedParcelId ?? '']}
            paint={{ 'line-color': '#0b6aa8', 'line-width': 4, 'line-opacity': 0.95 }}
          />
          <Layer
            id="parcels-label"
            type="symbol"
            minzoom={16}
            filter={parcelFilter}
            layout={{
              'text-field': ['get', 'cadastral_number'],
              'text-font': ['Noto Sans Regular'],
              'text-size': 11,
              'text-allow-overlap': false,
            }}
            paint={{ 'text-color': '#0f1b2d', 'text-halo-color': '#ffffff', 'text-halo-width': 1.4 }}
          />
        </Source>
      )}

      {signalsLayer && (
        <Source
          id="signals"
          type="geojson"
          data={signalsGeoJson}
          cluster
          clusterMaxZoom={14}
          clusterRadius={42}
        >
          <Layer
            id="signal-clusters"
            type="circle"
            filter={['has', 'point_count']}
            paint={{
              'circle-color': SIGNAL_STATUS_COLORS.NEW,
              'circle-opacity': 0.88,
              'circle-radius': ['step', ['get', 'point_count'], 15, 5, 19, 15, 24],
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': 2,
            }}
          />
          <Layer
            id="signal-cluster-count"
            type="symbol"
            filter={['has', 'point_count']}
            layout={{
              'text-field': ['get', 'point_count_abbreviated'],
              'text-font': ['Noto Sans Bold'],
              'text-size': 12,
            }}
            paint={{ 'text-color': '#ffffff' }}
          />
          <Layer
            id="signal-pulse"
            type="circle"
            filter={['all', ['!', ['has', 'point_count']], ['==', ['get', 'status'], 'NEW']]}
            paint={{ 'circle-color': SIGNAL_STATUS_COLORS.NEW, 'circle-radius': 10, 'circle-opacity': 0.4 }}
          />
          <Layer
            id="signal-point"
            type="circle"
            filter={['!', ['has', 'point_count']]}
            paint={{
              'circle-color': [
                'match',
                ['get', 'status'],
                ...Object.entries(SIGNAL_STATUS_COLORS).flat(),
                '#64748b',
              ] as unknown as ExpressionSpecification,
              'circle-radius': ['case', ['==', ['get', 'id'], selectedSignalId ?? ''], 10, 7],
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': ['case', ['==', ['get', 'id'], selectedSignalId ?? ''], 3.5, 2],
            }}
          />
          <Layer
            id="signal-reports"
            type="symbol"
            filter={['all', ['!', ['has', 'point_count']], ['>', ['get', 'reports'], 1]]}
            layout={{
              'text-field': ['concat', '×', ['to-string', ['get', 'reports']]],
              'text-font': ['Noto Sans Bold'],
              'text-size': 11,
              'text-offset': [1.3, -1.1],
              'text-allow-overlap': true,
            }}
            paint={{ 'text-color': '#7c3aed', 'text-halo-color': '#ffffff', 'text-halo-width': 1.6 }}
          />
        </Source>
      )}

      {hover && (
        <Popup
          longitude={hover.lng}
          latitude={hover.lat}
          closeButton={false}
          closeOnClick={false}
          offset={14}
          anchor="bottom"
          maxWidth="280px"
          className="pointer-events-none"
        >
          <div className="px-3 py-2 text-xs">
            <p className="font-mono text-[13px] font-semibold">{hover.parcel.cadastral_number}</p>
            <p className="mt-0.5 text-muted-foreground">
              {t(`parcelStatus.${hover.parcel.status}`)} · {formatArea(hover.parcel.area_ha, i18n.language)}{' '}
              {t('units.ha')}
              {ndviLayer && typeof hover.parcel.ndvi === 'number' && (
                <> · NDVI {hover.parcel.ndvi.toFixed(2)}</>
              )}
            </p>
          </div>
        </Popup>
      )}
    </MapGL>
  )
}
