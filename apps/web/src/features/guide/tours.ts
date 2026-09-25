import type { TourId } from '@/store/guide'

export interface TourStep {
  /** Value of the `data-tour` attribute to highlight; omitted → centered card. */
  target?: string
  key: string
  placement?: 'right' | 'bottom' | 'left' | 'top'
}

export const TOURS: Record<TourId, TourStep[]> = {
  main: [
    { key: 'welcome' },
    { target: 'nav', key: 'nav', placement: 'right' },
    { target: 'nav-home', key: 'home', placement: 'right' },
    { target: 'nav-map', key: 'map', placement: 'right' },
    { target: 'nav-signals', key: 'signals', placement: 'right' },
    { target: 'palette', key: 'palette', placement: 'bottom' },
    { target: 'realtime', key: 'realtime', placement: 'bottom' },
    { target: 'lang', key: 'lang', placement: 'bottom' },
    { target: 'help', key: 'help', placement: 'bottom' },
    { key: 'done' },
  ],
  map: [
    { target: 'map-search', key: 'mapSearch', placement: 'bottom' },
    { target: 'map-legend', key: 'mapLegend', placement: 'right' },
    { target: 'map-layers', key: 'mapLayers', placement: 'left' },
    { key: 'mapClick' },
  ],
  parcel: [
    { target: 'parcel-next', key: 'parcelNext', placement: 'left' },
    { target: 'parcel-actions', key: 'parcelActions', placement: 'left' },
    { target: 'parcel-tabs', key: 'parcelTabs', placement: 'left' },
  ],
}
