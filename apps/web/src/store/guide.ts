import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type TourId = 'main' | 'map' | 'parcel'

interface GuideState {
  seen: TourId[]
  active: TourId | null
  helpOpen: boolean
  paletteOpen: boolean
  start: (id: TourId) => void
  finish: () => void
  /** Start a tour only if the user has not seen it yet. */
  startOnce: (id: TourId) => void
  setHelpOpen: (open: boolean) => void
  setPaletteOpen: (open: boolean) => void
}

export const useGuideStore = create<GuideState>()(
  persist(
    (set, get) => ({
      seen: [],
      active: null,
      helpOpen: false,
      paletteOpen: false,
      start: (id) => set({ active: id, helpOpen: false }),
      finish: () => {
        const { active, seen } = get()
        set({ active: null, seen: active && !seen.includes(active) ? [...seen, active] : seen })
      },
      startOnce: (id) => {
        const { seen, active } = get()
        if (!seen.includes(id) && active === null) set({ active: id })
      },
      setHelpOpen: (helpOpen) => set({ helpOpen }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
    }),
    { name: 'jer-guide', partialize: (s) => ({ seen: s.seen }) },
  ),
)
