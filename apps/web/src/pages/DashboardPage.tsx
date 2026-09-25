import { AlarmClock, AreaChart, Clock3, Hourglass, Megaphone, ShieldAlert, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useDashboard } from '@/api/queries'
import { ErrorState } from '@/components/common/States'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { DeadlineChip } from '@/features/parcel/ParcelPanel'
import { useDateFns } from '@/lib/dates'
import { PARCEL_STATUS_COLORS } from '@/lib/status'
import { formatArea } from '@/lib/utils'

const BAR_COLOR = '#0b6aa8'

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string
  value: ReactNode
  icon: ReactNode
  tone?: 'danger' | 'warn'
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="text-xs font-medium">{label}</span>
        <span className={tone === 'danger' ? 'text-destructive' : tone === 'warn' ? 'text-warning' : ''}>
          {icon}
        </span>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
    </Card>
  )
}

function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean
  payload?: { value: number }[]
  label?: string
  unit: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border bg-card px-3 py-2 text-xs shadow-lg">
      <p className="text-muted-foreground">{label}</p>
      <p className="font-semibold text-foreground tabular-nums">
        {payload[0]!.value} {unit}
      </p>
    </div>
  )
}

export function DashboardPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { locale } = useDateFns()
  const query = useDashboard()
  const data = query.data

  if (query.isError)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} className="h-full" />

  const days = (data?.signals_by_day ?? []).map((d) => ({
    label: new Intl.DateTimeFormat(locale.code, { day: '2-digit', month: '2-digit' }).format(
      new Date(d.date),
    ),
    count: d.count,
  }))
  const types = (data?.violations_by_type ?? []).map((v) => ({
    label: t(`violationType.${v.violation_type}`),
    count: v.count,
  }))
  const totalParcels = data?.kpi.parcels_total ?? 0

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="mx-auto grid max-w-7xl gap-4 p-4 md:p-6">
        <div>
          <h2 className="text-xl font-semibold">{t('dashboard.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('dashboard.subtitle')}</p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {!data ? (
            Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)
          ) : (
            <>
              <Kpi
                label={t('dashboard.kpi.parcels')}
                value={
                  <>
                    {data.kpi.parcels_total}
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      {formatArea(data.kpi.area_total_ha, i18n.language)} {t('units.ha')}
                    </span>
                  </>
                }
                icon={<AreaChart className="size-4" />}
              />
              <Kpi
                label={t('dashboard.kpi.violations')}
                value={data.kpi.violations_active}
                icon={<ShieldAlert className="size-4" />}
                tone="danger"
              />
              <Kpi
                label={t('dashboard.kpi.remediation')}
                value={data.kpi.in_remediation}
                icon={<Wrench className="size-4" />}
              />
              <Kpi
                label={t('dashboard.kpi.overdue')}
                value={data.kpi.overdue}
                icon={<AlarmClock className="size-4" />}
                tone="danger"
              />
              <Kpi
                label={t('dashboard.kpi.signals7d')}
                value={
                  <>
                    {data.kpi.signals_7d}
                    {data.kpi.signals_new > 0 && (
                      <span className="ml-2 text-sm font-normal text-signal">
                        {t('dashboard.kpi.newCount', { count: data.kpi.signals_new })}
                      </span>
                    )}
                  </>
                }
                icon={<Megaphone className="size-4" />}
              />
              <Kpi
                label={t('dashboard.kpi.reaction')}
                value={
                  data.kpi.avg_reaction_hours === null
                    ? '—'
                    : t('dashboard.hours', { value: data.kpi.avg_reaction_hours })
                }
                icon={<Clock3 className="size-4" />}
              />
            </>
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>{t('dashboard.signalsByDay')}</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              {!data ? (
                <Skeleton className="h-full" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={days} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--muted)' }}
                      content={<ChartTooltip unit={t('dashboard.signalsUnit')} />}
                    />
                    <Bar dataKey="count" fill={BAR_COLOR} radius={[4, 4, 0, 0]} maxBarSize={28} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.statuses')}</CardTitle>
            </CardHeader>
            <CardContent>
              {!data ? (
                <Skeleton className="h-52" />
              ) : (
                <ul className="grid gap-2.5">
                  {data.status_counts.map((s) => (
                    <li key={s.status} className="grid gap-1">
                      <div className="flex items-center justify-between text-sm">
                        <span>{t(`parcelStatus.${s.status}`)}</span>
                        <span className="text-muted-foreground tabular-nums">{s.count}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${totalParcels ? (s.count / totalParcels) * 100 : 0}%`,
                            backgroundColor: PARCEL_STATUS_COLORS[s.status],
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.byType')}</CardTitle>
            </CardHeader>
            <CardContent className="h-60">
              {!data ? (
                <Skeleton className="h-full" />
              ) : types.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('dashboard.noViolations')}</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={types} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
                    <CartesianGrid horizontal={false} stroke="var(--border)" />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                    />
                    <YAxis
                      type="category"
                      dataKey="label"
                      width={150}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 12, fill: 'var(--foreground)' }}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--muted)' }}
                      content={<ChartTooltip unit={t('dashboard.parcelsUnit')} />}
                    />
                    <Bar dataKey="count" fill={BAR_COLOR} radius={[0, 4, 4, 0]} maxBarSize={22} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Hourglass className="size-4" /> {t('dashboard.deadlines')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!data ? (
                <Skeleton className="h-52" />
              ) : data.upcoming_deadlines.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('dashboard.noDeadlines')}</p>
              ) : (
                <ul className="divide-y">
                  {data.upcoming_deadlines.map((d) => (
                    <li key={d.parcel_id}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-3 py-2 text-left hover:bg-muted/50"
                        onClick={() => navigate(`/map?parcel=${d.parcel_id}`)}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block font-mono text-sm font-medium">{d.cadastral_number}</span>
                          <span className="block text-xs text-muted-foreground">
                            {d.violation_type ? t(`violationType.${d.violation_type}`) : ''}
                          </span>
                        </span>
                        <StatusBadge kind="parcel" status={d.status} />
                        <DeadlineChip deadline={d.deadline_at} active />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
