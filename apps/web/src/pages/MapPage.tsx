import { Loader2 } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useParcels, useSignals } from '@/api/queries'
import { ErrorState } from '@/components/common/States'
import { LayerControls, Legend, MapSearch } from '@/features/map/MapOverlays'
import { ParcelMap } from '@/features/map/ParcelMap'
import { ParcelPanel } from '@/features/parcel/ParcelPanel'
import { SignalPanel } from '@/features/signals/SignalPanel'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/store/ui'

export function MapPage() {
  const { t } = useTranslation()
  const parcels = useParcels()
  const signals = useSignals()
  const { selectedParcelId, selectedSignalId, selectParcel, selectSignal, flyTo } = useUiStore()
  const [params, setParams] = useSearchParams()

  // Deep links: /?parcel=<id> or /?signal=<id> (from tables and the signal queue).
  useEffect(() => {
    const parcelId = params.get('parcel')
    const signalId = params.get('signal')
    if (!parcelId && !signalId) return
    if (parcelId) {
      selectParcel(parcelId)
      const feature = parcels.data?.features.find((f) => f.id === parcelId)
      if (!feature) return
      const coords = feature.geometry.coordinates as number[][][][]
      const points = coords.flat(2)
      const xs = points.map((p) => p[0]!)
      const ys = points.map((p) => p[1]!)
      flyTo({ bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] })
    }
    if (signalId) {
      selectSignal(signalId)
      const signal = signals.data?.items.find((s) => s.id === signalId)
      if (!signal) return
      flyTo({ center: [signal.lon, signal.lat], zoom: 17 })
    }
    setParams({}, { replace: true })
  }, [params, parcels.data, signals.data, selectParcel, selectSignal, flyTo, setParams])

  const openParcel = (id: string) => {
    selectParcel(id)
    const feature = parcels.data?.features.find((f) => f.id === id)
    if (feature) {
      const points = (feature.geometry.coordinates as number[][][][]).flat(2)
      const xs = points.map((p) => p[0]!)
      const ys = points.map((p) => p[1]!)
      flyTo({ bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] })
    }
  }

  return (
    <div className="absolute inset-0">
      {parcels.isError ? (
        <ErrorState error={parcels.error} onRetry={() => void parcels.refetch()} className="h-full" />
      ) : (
        <ParcelMap
          parcels={parcels.data}
          signals={signals.data?.items ?? []}
          onSelectParcel={selectParcel}
          onSelectSignal={selectSignal}
        />
      )}

      {parcels.isLoading && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-background/40">
          <span className="flex items-center gap-2 rounded-full bg-card px-4 py-2 text-sm shadow">
            <Loader2 className="size-4 animate-spin" /> {t('map.loading')}
          </span>
        </div>
      )}

      <div className="pointer-events-none absolute top-3 right-3 left-3 z-10 flex items-start justify-between gap-3">
        <div className="pointer-events-auto w-full max-w-md">
          <MapSearch
            onPick={(result) => {
              selectParcel(result.id)
              flyTo({ bbox: result.bbox as [number, number, number, number] })
            }}
          />
        </div>
        <div
          className={cn(
            'pointer-events-auto transition-[margin] duration-200',
            (selectedParcelId || selectedSignalId) && 'hidden md:mr-[440px] md:block',
          )}
        >
          <LayerControls />
        </div>
      </div>

      <div className="absolute bottom-6 left-3 z-10">
        <Legend parcels={parcels.data} />
      </div>

      {selectedParcelId && <ParcelPanel parcelId={selectedParcelId} onClose={() => selectParcel(null)} />}
      {selectedSignalId && (
        <SignalPanel
          signalId={selectedSignalId}
          onClose={() => selectSignal(null)}
          onOpenParcel={openParcel}
        />
      )}
    </div>
  )
}
