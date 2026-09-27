import { Loader2, Satellite } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useParcelSatellite } from '@/api/queries'
import { ErrorState } from '@/components/common/States'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Section } from '@/features/common/Section'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'

const LINE = 'var(--primary)'
const THRESHOLD = 'var(--destructive)'

interface Point {
  ts: number
  ndvi: number
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const { date } = useDateFns()
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <div className="rounded-md border bg-card px-2.5 py-1.5 text-xs shadow">
      <p className="text-muted-foreground">{date(new Date(point.ts).toISOString())}</p>
      <p className="font-semibold tabular-nums">NDVI {point.ndvi.toFixed(2)}</p>
    </div>
  )
}

/** NDVI over time from Sentinel-2 with the "unused" threshold, yearly peaks and before/after chips. */
export function SatelliteTab({ parcelId }: { parcelId: string }) {
  const { t, i18n } = useTranslation()
  const { date } = useDateFns()
  const query = useParcelSatellite(parcelId, true)
  const data = query.data

  if (query.isLoading) return <Skeleton className="m-5 h-56" />
  if (query.isError || !data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />

  const points: Point[] = data.points.map((p) => ({ ts: new Date(p.date).getTime(), ndvi: p.ndvi }))
  const monthFmt = new Intl.DateTimeFormat(i18n.language === 'kk' ? 'kk-KZ' : 'ru-RU', {
    month: 'short',
    year: '2-digit',
  })

  return (
    <>
      <Section
        title={t('satellite.title')}
        icon={<Satellite className="size-3.5" />}
        aside={
          data.is_demo ? (
            <Badge variant="warning">{t('map.demoBadge')}</Badge>
          ) : (
            <Badge variant="success">Sentinel-2</Badge>
          )
        }
      >
        {data.status === 'loading' && (
          <p className="mb-3 flex items-center gap-2 rounded-lg bg-muted p-2.5 text-xs">
            <Loader2 className="size-3.5 animate-spin" /> {t('satellite.loading')}
          </p>
        )}
        {points.length === 0 ? (
          data.status !== 'loading' && <p className="text-sm text-muted-foreground">{t('satellite.empty')}</p>
        ) : (
          <div className="h-48" role="img" aria-label={t('satellite.chartLabel')}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -28 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis
                  dataKey="ts"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(v: number) => monthFmt.format(v)}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                  tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                />
                <YAxis
                  domain={[0, 1]}
                  ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                />
                <ReferenceLine y={data.threshold} stroke={THRESHOLD} strokeDasharray="4 4" />
                <Tooltip content={<PointTooltip />} cursor={{ stroke: 'var(--border)' }} />
                <Line
                  dataKey="ndvi"
                  stroke={LINE}
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: LINE, strokeWidth: 0 }}
                  activeDot={{ r: 5, stroke: 'var(--card)', strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {points.length > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            {t('satellite.legend', { threshold: data.threshold })}
          </p>
        )}
      </Section>

      {data.yearly_peaks.length > 0 && (
        <Section title={t('satellite.peaks')}>
          <ul className="grid gap-1.5">
            {data.yearly_peaks.map((p) => (
              <li key={p.year} className="grid grid-cols-[3rem_1fr_2.5rem] items-center gap-2 text-sm">
                <span className="text-muted-foreground tabular-nums">{p.year}</span>
                <span className="h-2 overflow-hidden rounded-full bg-muted">
                  <span
                    className={cn(
                      'block h-full rounded-full',
                      p.peak < data.threshold ? 'bg-destructive' : 'bg-primary',
                    )}
                    style={{ width: `${Math.max(0, Math.min(1, p.peak)) * 100}%` }}
                  />
                </span>
                <span className="text-right font-medium tabular-nums">{p.peak.toFixed(2)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">{t('satellite.peaksHint')}</p>
        </Section>
      )}

      {data.images.length > 0 && (
        <Section title={t('satellite.images')}>
          <div className="grid grid-cols-3 gap-2">
            {data.images.map((img) => (
              <figure key={img.scene_id} className="grid gap-1">
                <a href={img.url} target="_blank" rel="noreferrer">
                  <img
                    src={img.url}
                    alt={t('satellite.imageAlt', { date: date(img.date) })}
                    className="aspect-square w-full rounded-md border object-cover [image-rendering:pixelated]"
                  />
                </a>
                <figcaption className="text-center text-[11px] text-muted-foreground">
                  {date(img.date)}
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{t('satellite.imagesHint')}</p>
        </Section>
      )}
    </>
  )
}
