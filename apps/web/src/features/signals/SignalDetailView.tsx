import { Languages, MapPin, Megaphone, Ruler, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MapGL, { Layer, Marker, Source } from 'react-map-gl/maplibre'
import { useParcels } from '@/api/queries'
import type { SignalDetail, SignalStatus } from '@/api/types'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { HistoryTimeline } from '@/features/common/History'
import { PhotoGallery } from '@/features/common/PhotoGallery'
import { baseStyle } from '@/features/map/mapStyle'
import { Section } from '@/features/common/Section'
import { useDateFns } from '@/lib/dates'
import { PARCEL_STATUS_COLORS, SIGNAL_STATUS_COLORS } from '@/lib/status'
import { formatCoords } from '@/lib/utils'
import { SignalTransitionDialog } from './SignalTransitionDialog'

export function MiniMap({ signal }: { signal: SignalDetail }) {
  const parcels = useParcels().data
  const style = useMemo(() => baseStyle(), [])
  const parcel = useMemo(
    () => parcels?.features.find((f) => f.properties.id === signal.parcel_id),
    [parcels, signal.parcel_id],
  )
  return (
    <div className="h-44 overflow-hidden rounded-lg border">
      <MapGL
        key={signal.id}
        initialViewState={{ longitude: signal.lon, latitude: signal.lat, zoom: 16.2 }}
        mapStyle={style}
        interactive={false}
        attributionControl={false}
        style={{ width: '100%', height: '100%' }}
      >
        {parcel && (
          <Source id="mini-parcel" type="geojson" data={parcel}>
            <Layer
              id="mini-parcel-fill"
              type="fill"
              paint={{ 'fill-color': PARCEL_STATUS_COLORS[parcel.properties.status], 'fill-opacity': 0.3 }}
            />
            <Layer
              id="mini-parcel-line"
              type="line"
              paint={{ 'line-color': PARCEL_STATUS_COLORS[parcel.properties.status], 'line-width': 2 }}
            />
          </Source>
        )}
        <Marker longitude={signal.lon} latitude={signal.lat} anchor="center">
          <span className="relative grid size-5 place-items-center">
            <span
              className="absolute inset-0 animate-pulse-ring rounded-full"
              style={{ backgroundColor: SIGNAL_STATUS_COLORS[signal.status] }}
            />
            <span
              className="relative size-3.5 rounded-full border-2 border-white shadow"
              style={{ backgroundColor: SIGNAL_STATUS_COLORS[signal.status] }}
            />
          </span>
        </Marker>
      </MapGL>
    </div>
  )
}

export function SignalActions({ signal }: { signal: SignalDetail }) {
  const { t } = useTranslation()
  const [target, setTarget] = useState<SignalStatus | null>(null)
  if (!signal.allowed_transitions.length) return null
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {signal.allowed_transitions.map((to) => (
          <Button
            key={to}
            size="sm"
            variant={to === 'CONFIRMED' ? 'destructive' : to === 'REJECTED' ? 'outline' : 'default'}
            onClick={() => setTarget(to)}
          >
            {t(`transition.action.SIGNAL.${to}`)}
          </Button>
        ))}
      </div>
      {target && (
        <SignalTransitionDialog
          key={target}
          signal={signal}
          target={target}
          onClose={() => setTarget(null)}
        />
      )}
    </>
  )
}

export function SignalDetailView({
  signal,
  onOpenParcel,
}: {
  signal: SignalDetail
  onOpenParcel?: (parcelId: string) => void
}) {
  const { t } = useTranslation()
  const { dateTime, relative } = useDateFns()

  return (
    <>
      <Section title={t('signals.actions')}>
        <SignalActions signal={signal} />
        {!signal.allowed_transitions.length && (
          <div className="text-sm">
            <p className="text-muted-foreground">{t('signals.closed')}</p>
            {signal.resolution_comment && <p className="mt-1 font-medium">«{signal.resolution_comment}»</p>}
          </div>
        )}
      </Section>

      <Section title={t('signals.details')}>
        <div className="grid gap-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">{t(`signalCategory.${signal.category}`)}</Badge>
            {signal.reports_count > 1 && (
              <Badge>
                <Users className="size-3" /> {t('signals.reports', { count: signal.reports_count })}
              </Badge>
            )}
            <Badge variant="outline">
              <Languages className="size-3" /> {signal.reporter_lang.toUpperCase()}
            </Badge>
          </div>
          {signal.description ? (
            <p className="rounded-lg bg-muted/60 p-3 whitespace-pre-line">{signal.description}</p>
          ) : (
            <p className="text-muted-foreground italic">{t('signals.noDescription')}</p>
          )}
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted-foreground">{t('signals.received')}</dt>
            <dd>
              {dateTime(signal.created_at)}{' '}
              <span className="text-muted-foreground">({relative(signal.created_at)})</span>
            </dd>
            <dt className="text-muted-foreground">{t('signals.location')}</dt>
            <dd className="flex items-center gap-1">
              <MapPin className="size-3.5" /> {signal.address ?? formatCoords(signal.lat, signal.lon)}
            </dd>
            <dt className="text-muted-foreground">{t('signals.parcel')}</dt>
            <dd>
              {signal.parcel_id && signal.parcel_cadastral_number ? (
                <button
                  type="button"
                  className="font-mono text-primary hover:underline"
                  onClick={() => onOpenParcel?.(signal.parcel_id!)}
                >
                  {signal.parcel_cadastral_number}
                </button>
              ) : (
                <span className="text-muted-foreground">{t('signals.noParcel')}</span>
              )}
              {signal.parcel_distance_m !== null && signal.parcel_distance_m > 0 && (
                <span className="ml-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Ruler className="size-3" />{' '}
                  {t('signals.distance', { meters: Math.round(signal.parcel_distance_m) })}
                </span>
              )}
            </dd>
          </dl>
          <MiniMap signal={signal} />
        </div>
      </Section>

      <Section
        title={t('photos.title')}
        aside={<span className="text-xs text-muted-foreground">{signal.photos.length}</span>}
      >
        <PhotoGallery photos={signal.photos} />
      </Section>

      {signal.duplicates.length > 0 && (
        <Section title={t('signals.duplicates')} icon={<Megaphone className="size-3.5" />}>
          <ul className="grid gap-2">
            {signal.duplicates.map((dup) => (
              <li
                key={dup.id}
                className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm"
              >
                <span>
                  <span className="font-mono text-xs font-semibold">{dup.tracking_code}</span>
                  <span className="block text-xs text-muted-foreground">
                    {dup.description ?? t('signals.noDescription')}
                  </span>
                </span>
                <StatusBadge kind="signal" status={dup.status} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={t('history.title')}>
        <HistoryTimeline items={signal.history} kind="signal" />
      </Section>
    </>
  )
}
