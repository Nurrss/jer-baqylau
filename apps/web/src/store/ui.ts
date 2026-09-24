import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ParcelPurpose, ParcelStatus, ViolationType } from '@/api/types'

export type Basemap = 'osm' | 'satellite'
export type Theme = 'light' | 'dark'

export interface MapFilters {
  statuses: ParcelStatus[]
  violationTypes: ViolationType[]
  purposes: ParcelPurpose[]
  overdueOnly: boolean
}

export const EMPTY_FILTERS: MapFilters = {
  statuses: [],
  violationTypes: [],
  purposes: [],
  overdueOnly: false,
}

export interface FlyTarget {
  bbox?: [number, number, number, number]
  center?: [number, number]
  zoom?: number
  /** Changes on every request so the same target can be flown to twice. */
  nonce: number
}

interface UiState {
  // persisted preferences
  theme: Theme
  basemap: Basemap
  ndviLayer: boolean
  signalsLayer: boolean
  soundEnabled: boolean
  // session state
  selectedParcelId: string | null
  selectedSignalId: string | null
  filters: MapFilters
  flyTarget: FlyTarget | null
  freshSignalIds: string[]

  setTheme: (theme: Theme) => void
  setBasemap: (basemap: Basemap) => void
  toggleNdvi: () => void
  toggleSignals: () => void
  toggleSound: () => void
  selectParcel: (id: string | null) => void
  selectSignal: (id: string | null) => void
  setFilters: (patch: Partial<MapFilters>) => void
  resetFilters: () => void
  flyTo: (target: Omit<FlyTarget, 'nonce'>) => void
  markFresh: (signalId: string) => void
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
      basemap: 'osm',
      ndviLayer: false,
      signalsLayer: true,
      soundEnabled: true,
      selectedParcelId: null,
      selectedSignalId: null,
      filters: EMPTY_FILTERS,
      flyTarget: null,
      freshSignalIds: [],

      setTheme: (theme) => set({ theme }),
      setBasemap: (basemap) => set({ basemap }),
      toggleNdvi: () => set((s) => ({ ndviLayer: !s.ndviLayer })),
      toggleSignals: () => set((s) => ({ signalsLayer: !s.signalsLayer })),
      toggleSound: () => set((s) => ({ soundEnabled: !s.soundEnabled })),
      selectParcel: (id) => set({ selectedParcelId: id, selectedSignalId: null }),
      selectSignal: (id) => set({ selectedSignalId: id, selectedParcelId: null }),
      setFilters: (patch) => set((s) => ({ filters: { ...s.filters, ...patch } })),
      resetFilters: () => set({ filters: EMPTY_FILTERS }),
      flyTo: (target) => set({ flyTarget: { ...target, nonce: Date.now() } }),
      markFresh: (signalId) => {
        set((s) => ({ freshSignalIds: [...s.freshSignalIds, signalId] }))
        window.setTimeout(
          () => set((s) => ({ freshSignalIds: s.freshSignalIds.filter((id) => id !== signalId) })),
          12_000,
        )
      },
    }),
    {
      name: 'jer-ui',
      partialize: (s) => ({
        theme: s.theme,
        basemap: s.basemap,
        ndviLayer: s.ndviLayer,
        signalsLayer: s.signalsLayer,
        soundEnabled: s.soundEnabled,
      }),
    },
  ),
)
