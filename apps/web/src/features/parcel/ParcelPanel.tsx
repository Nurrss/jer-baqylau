import {
  AlarmClock,
  Building2,
  CalendarClock,
  Check,
  CheckCircle2,
  CircleAlert,
  Database,
  FileDown,
  Info,
  Lightbulb,
  Loader2,
  Megaphone,
  X,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { downloadFile } from '@/api/client'
import { useCadastre, useParcel, useParcelUpdate, usePhotoUpload } from '@/api/queries'
import type { ParcelDetail, ParcelStatus } from '@/api/types'
import { CopyButton } from '@/components/common/CopyButton'
import { ErrorState } from '@/components/common/States'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { HistoryTimeline } from '@/features/common/History'
import { PhotoGallery, PhotoUploader } from '@/features/common/PhotoGallery'
import { daysUntil, fromDateInput, toDateInput, useDateFns } from '@/lib/dates'
import { LIFECYCLE_STEPS, lifecycleIndex } from '@/lib/status'
import { cn, formatArea } from '@/lib/utils'
import { useGuideStore } from '@/store/guide'
import { useUiStore } from '@/store/ui'
import { ParcelTransitionDialog } from './ParcelTransitionDialog'

export function Section({
  title,
  icon,
  children,
  aside,
}: {
  title: string
  icon?: ReactNode
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <section className="border-t px-5 py-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          {icon}
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function DeadlineChip({ deadline, active }: { deadline: string; active: boolean }) {
  const { t } = useTranslation()
  const days = daysUntil(deadline)
  if (!active) return null
  const overdue = days < 0
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold',
        overdue
          ? 'bg-destructive text-destructive-foreground'
          : days <= 7
            ? 'bg-accent/25 text-warning'
            : 'bg-muted',
      )}
    >
      <AlarmClock className="size-3" />
      {overdue
        ? t('deadline.overdue', { count: Math.abs(days) })
        : days === 0
          ? t('deadline.today')
          : t('deadline.left', { count: days })}
    </span>
  )
}

function LifecycleStepper({ status }: { status: ParcelStatus }) {
  const { t } = useTranslation()
  const current = lifecycleIndex(status)
  if (current < 0) {
    return <p className="text-sm text-muted-foreground">{t(`lifecycle.hint.${status}`)}</p>
  }
  const finalLabel =
    status === 'RETURNED_TO_STATE' ? t('lifecycle.returned') : t('lifecycle.resolvedOrReturned')
  return (
    <ol className="flex items-start">
      {LIFECYCLE_STEPS.map((step, i) => {
        const done = i < current || (i === current && i === 2)
        const active = i === current && i !== 2
        const label =
          step === 'FINAL'
            ? status === 'RESOLVED'
              ? t('lifecycle.resolved')
              : finalLabel
            : t(`lifecycle.${step}`)
        return (
          <li key={step} className="relative flex flex-1 flex-col items-center text-center">
            {i > 0 && (
              <span
                className={cn(
                  'absolute top-3.5 right-1/2 h-0.5 w-full -translate-y-1/2',
                  i <= current ? 'bg-primary' : 'bg-border',
                )}
              />
            )}
            <span
              className={cn(
                'relative z-10 grid size-7 place-items-center rounded-full border-2 text-xs font-bold',
                done && 'border-primary bg-primary text-primary-foreground',
                active && 'border-destructive bg-destructive/10 text-destructive',
                !done && !active && 'border-border bg-card text-muted-foreground',
              )}
            >
              {done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
            </span>
            <span
              className={cn(
                'mt-1.5 px-1 text-[11px] leading-tight',
                active || done ? 'font-medium' : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Characteristics({ parcel }: { parcel: ParcelDetail }) {
  const { t, i18n } = useTranslation()
  const { date } = useDateFns()
  const rows: [string, ReactNode][] = [
    [t('parcel.purpose'), t(`purpose.${parcel.purpose}`)],
    [t('parcel.area'), `${formatArea(parcel.area_ha, i18n.language)} ${t('units.ha')}`],
    [t('parcel.ownerType'), t(`ownerType.${parcel.owner_type}`)],
    [t('parcel.address'), i18n.language === 'kk' ? parcel.address_kk : parcel.address_ru],
    [t('parcel.district'), parcel.district],
  ]
  if (parcel.lease_until) rows.push([t('parcel.leaseUntil'), date(parcel.lease_until)])
  if (parcel.violation_type)
    rows.push([t('parcel.violationType'), t(`violationType.${parcel.violation_type}`)])
  if (typeof parcel.ndvi === 'number')
    rows.push([
      'NDVI',
      <span key="ndvi" className="flex items-center gap-2">
        {parcel.ndvi.toFixed(2)}
        {parcel.ndvi_observed_at && (
          <span className="text-xs font-normal text-muted-foreground">
            {t('parcel.ndviObserved', { date: date(parcel.ndvi_observed_at) })}
          </span>
        )}
        {parcel.ndvi_flagged && <Badge variant="warning">{t('parcel.ndviFlagged')}</Badge>}
      </span>,
    ])
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function DeadlineEditor({ parcel }: { parcel: ParcelDetail }) {
  const { t } = useTranslation()
  const { date } = useDateFns()
  const errorMessage = useErrorMessage()
  const update = useParcelUpdate(parcel.id)
  const [value, setValue] = useState(toDateInput(parcel.deadline_at))
  const active = parcel.status === 'VIOLATION' || parcel.status === 'IN_REMEDIATION'
  const changed = value !== toDateInput(parcel.deadline_at)

  if (!active && !parcel.deadline_at) return null
  return (
    <Section title={t('parcel.deadline')} icon={<CalendarClock className="size-3.5" />}>
      <div className="flex flex-wrap items-center gap-2">
        {parcel.deadline_at && <DeadlineChip deadline={parcel.deadline_at} active={active} />}
        {!active && parcel.deadline_at && <span className="text-sm">{date(parcel.deadline_at)}</span>}
      </div>
      {active && (
        <div className="mt-3 flex items-center gap-2">
          <Input
            type="date"
            value={value}
            min={toDateInput(new Date().toISOString())}
            onChange={(e) => setValue(e.target.value)}
            className="max-w-44"
            aria-label={t('parcel.deadline')}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!changed || !value || update.isPending}
            onClick={async () => {
              try {
                await update.mutateAsync({ deadline_at: fromDateInput(value) })
                toast.success(t('parcel.deadlineSaved'))
              } catch (err) {
                toast.error(errorMessage(err))
              }
            }}
          >
            {update.isPending && <Loader2 className="animate-spin" />}
            {t('common.save')}
          </Button>
        </div>
      )}
    </Section>
  )
}

function CadastreCheck({ parcelId }: { parcelId: string }) {
  const { t } = useTranslation()
  const { date } = useDateFns()
  const [open, setOpen] = useState(false)
  const query = useCadastre(parcelId, open)
  const record = query.data
  return (
    <Section
      title={t('cadastre.title')}
      icon={<Database className="size-3.5" />}
      aside={<Badge variant="warning">{t('map.demoBadge')}</Badge>}
    >
      {!open ? (
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          <Building2 /> {t('cadastre.check')}
        </Button>
      ) : query.isLoading ? (
        <Skeleton className="h-24" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} className="py-4" />
      ) : record ? (
        <div className="grid gap-2 text-sm">
          <p
            className={cn(
              'flex items-center gap-2 font-medium',
              record.matches_local ? 'text-success' : 'text-warning',
            )}
          >
            {record.matches_local ? <Check className="size-4" /> : <CircleAlert className="size-4" />}
            {record.matches_local ? t('cadastre.match') : t('cadastre.mismatch')}
          </p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-muted-foreground">{t('cadastre.holder')}</dt>
            <dd>{record.right_holder}</dd>
            <dt className="text-muted-foreground">{t('cadastre.right')}</dt>
            <dd>{record.right_type}</dd>
            <dt className="text-muted-foreground">{t('cadastre.registryArea')}</dt>
            <dd className={cn(record.discrepancies.includes('area') && 'font-semibold text-warning')}>
              {record.area_ha} {t('units.ha')}
            </dd>
            <dt className="text-muted-foreground">{t('cadastre.registered')}</dt>
            <dd>{date(record.registered_at)}</dd>
            <dt className="text-muted-foreground">{t('cadastre.encumbrances')}</dt>
            <dd>{record.encumbrances.length ? record.encumbrances.join(', ') : '—'}</dd>
          </dl>
          <p className="text-[11px] text-muted-foreground">
            {t('cadastre.note', { provider: record.provider })}
          </p>
        </div>
      ) : null}
    </Section>
  )
}

function PanelSkeleton() {
  return (
    <div className="grid gap-4 p-5">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-14" />
      <Skeleton className="h-32" />
      <Skeleton className="h-24" />
    </div>
  )
}

function TabCount({ n }: { n: number }) {
  return n > 0 ? <span className="text-xs text-muted-foreground tabular-nums">{n}</span> : null
}

type NextStepKind = 'info' | 'warning' | 'danger' | 'success' | 'muted'

/** What the inspector should do next, derived from the parcel state (the state machine is the source of truth). */
function nextStep(parcel: ParcelDetail): { key: string; kind: NextStepKind; action?: ParcelStatus } {
  const overdue = parcel.is_overdue
  switch (parcel.status) {
    case 'OK':
      return parcel.open_signals_count > 0
        ? { key: 'okWithSignals', kind: 'warning', action: 'UNDER_CHECK' }
        : { key: 'ok', kind: 'muted' }
    case 'UNDER_CHECK':
      return { key: 'underCheck', kind: 'warning', action: 'VIOLATION' }
    case 'VIOLATION':
      return { key: overdue ? 'violationOverdue' : 'violation', kind: 'danger', action: 'IN_REMEDIATION' }
    case 'IN_REMEDIATION':
      return overdue
        ? { key: 'remediationOverdue', kind: 'danger', action: 'RETURNED_TO_STATE' }
        : { key: 'remediation', kind: 'info', action: 'RESOLVED' }
    case 'RESOLVED':
      return { key: 'resolved', kind: 'success' }
    default:
      return { key: 'returned', kind: 'muted' }
  }
}

function NextStep({ parcel, onAction }: { parcel: ParcelDetail; onAction: (to: ParcelStatus) => void }) {
  const { t } = useTranslation()
  const { date } = useDateFns()
  const step = nextStep(parcel)
  const styles: Record<NextStepKind, string> = {
    info: 'border-primary/30 bg-primary/5',
    warning: 'border-accent/50 bg-accent/10',
    danger: 'border-destructive/30 bg-destructive/5',
    success: 'border-success/30 bg-success/5',
    muted: 'border-border bg-muted/40',
  }
  const Icon = step.kind === 'success' ? CheckCircle2 : step.kind === 'muted' ? Info : Lightbulb
  return (
    <div className={cn('mx-5 mb-2 rounded-xl border p-3', styles[step.kind])} data-tour="parcel-next">
      <p className="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
        <Icon className="size-3.5" /> {t('nextStep.title')}
      </p>
      <p className="mt-1 text-sm">
        {t(`nextStep.${step.key}`, {
          count: parcel.open_signals_count,
          date: date(parcel.deadline_at),
        })}
      </p>
      {step.action && parcel.allowed_transitions.includes(step.action) && (
        <Button
          size="sm"
          className="mt-2.5"
          variant={
            step.action === 'VIOLATION' || step.action === 'RETURNED_TO_STATE' ? 'destructive' : 'default'
          }
          onClick={() => onAction(step.action!)}
        >
          {t(`transition.action.PARCEL.${step.action}`)}
        </Button>
      )}
    </div>
  )
}

export function ParcelPanel({ parcelId, onClose }: { parcelId: string; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const errorMessage = useErrorMessage()
  const query = useParcel(parcelId)
  const upload = usePhotoUpload(parcelId)
  const selectSignal = useUiStore((s) => s.selectSignal)
  const [target, setTarget] = useState<ParcelStatus | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [tab, setTab] = useState('overview')
  const parcel = query.data
  const startOnce = useGuideStore((s) => s.startOnce)

  useEffect(() => {
    if (!parcel) return
    const timer = window.setTimeout(() => startOnce('parcel'), 700)
    return () => window.clearTimeout(timer)
  }, [parcel, startOnce])

  return (
    <aside
      className="absolute top-0 right-0 bottom-0 z-20 flex w-full max-w-[440px] animate-slide-in flex-col border-l bg-card shadow-2xl"
      aria-label={t('parcel.card')}
    >
      <header className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{t('parcel.cadastralNumber')}</p>
          {parcel ? (
            <div className="flex items-center gap-1">
              <h2 className="font-mono text-lg font-semibold tracking-tight">{parcel.cadastral_number}</h2>
              <CopyButton value={parcel.cadastral_number} />
            </div>
          ) : (
            <Skeleton className="mt-1 h-7 w-48" />
          )}
          {parcel && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge kind="parcel" status={parcel.status} />
              {parcel.deadline_at && (
                <DeadlineChip
                  deadline={parcel.deadline_at}
                  active={parcel.status === 'VIOLATION' || parcel.status === 'IN_REMEDIATION'}
                />
              )}
              {parcel.open_signals_count > 0 && (
                <Badge variant="secondary">
                  <Megaphone className="size-3" />{' '}
                  {t('parcel.openSignals', { count: parcel.open_signals_count })}
                </Badge>
              )}
            </div>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t('common.close')}>
          <X />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {query.isLoading && <PanelSkeleton />}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {parcel && (
          <>
            <NextStep parcel={parcel} onAction={setTarget} />
            <Tabs value={tab} onValueChange={setTab} className="mt-1">
              <div className="sticky top-0 z-10 border-b bg-card px-5 pb-2" data-tour="parcel-tabs">
                <TabsList className="w-full">
                  <TabsTrigger value="overview" className="flex-1">
                    {t('parcel.tabs.overview')}
                  </TabsTrigger>
                  <TabsTrigger value="photos" className="flex-1">
                    {t('parcel.tabs.photos')} <TabCount n={parcel.photos.length} />
                  </TabsTrigger>
                  <TabsTrigger value="signals" className="flex-1">
                    {t('parcel.tabs.signals')} <TabCount n={parcel.signals.length} />
                  </TabsTrigger>
                  <TabsTrigger value="history" className="flex-1">
                    {t('parcel.tabs.history')}
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="overview">
                <Section title={t('lifecycle.title')}>
                  <LifecycleStepper status={parcel.status} />
                  {parcel.allowed_transitions.length > 0 ? (
                    <div className="mt-4 grid gap-2" data-tour="parcel-actions">
                      <p className="text-xs text-muted-foreground">{t('parcel.allActions')}</p>
                      <div className="flex flex-wrap gap-2">
                        {parcel.allowed_transitions.map((to) => (
                          <Button
                            key={to}
                            size="sm"
                            variant={
                              to === 'VIOLATION' || to === 'RETURNED_TO_STATE'
                                ? 'destructive'
                                : to === 'RESOLVED' || to === 'OK'
                                  ? 'success'
                                  : 'default'
                            }
                            onClick={() => setTarget(to)}
                          >
                            {t(`transition.action.PARCEL.${to}`)}
                          </Button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-muted-foreground">{t('lifecycle.terminal')}</p>
                  )}
                </Section>
                <DeadlineEditor key={parcel.deadline_at ?? 'none'} parcel={parcel} />
                <Section title={t('parcel.characteristics')}>
                  <Characteristics parcel={parcel} />
                </Section>
                <CadastreCheck parcelId={parcel.id} />
              </TabsContent>

              <TabsContent value="photos">
                <Section title={t('photos.title')}>
                  <div className="grid gap-3">
                    <PhotoUploader
                      upload={(files, onProgress) => upload.mutateAsync({ files, onProgress })}
                    />
                    <PhotoGallery photos={parcel.photos} />
                  </div>
                </Section>
              </TabsContent>

              <TabsContent value="signals">
                <Section title={t('parcel.relatedSignals')} icon={<Megaphone className="size-3.5" />}>
                  {parcel.signals.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t('parcel.noSignals')}</p>
                  ) : (
                    <ul className="grid gap-2">
                      {parcel.signals.map((signal) => (
                        <li key={signal.id}>
                          <button
                            type="button"
                            onClick={() => selectSignal(signal.id)}
                            className="flex w-full items-center gap-3 rounded-lg border p-2 text-left hover:bg-muted"
                          >
                            {signal.thumb_url ? (
                              <img src={signal.thumb_url} alt="" className="size-10 rounded object-cover" />
                            ) : (
                              <span className="grid size-10 place-items-center rounded bg-muted">
                                <Megaphone className="size-4 text-muted-foreground" />
                              </span>
                            )}
                            <span className="min-w-0 flex-1">
                              <span className="block font-mono text-xs font-semibold">
                                {signal.tracking_code}
                              </span>
                              <span className="block truncate text-xs text-muted-foreground">
                                {t(`signalCategory.${signal.category}`)}
                                {signal.reports_count > 1 &&
                                  ` · ${t('signals.reports', { count: signal.reports_count })}`}
                              </span>
                            </span>
                            <StatusBadge kind="signal" status={signal.status} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>
              </TabsContent>

              <TabsContent value="history">
                <Section title={t('history.title')}>
                  <HistoryTimeline items={parcel.history} kind="parcel" />
                </Section>
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>

      {parcel && (
        <footer className="border-t bg-muted/40 px-5 py-3">
          <Button
            variant="outline"
            className="w-full"
            disabled={downloading}
            onClick={async () => {
              setDownloading(true)
              try {
                await downloadFile(
                  `/api/v1/parcels/${parcel.id}/act.pdf?lang=${i18n.language}`,
                  `act_${parcel.cadastral_number.replaceAll(':', '-')}.pdf`,
                )
              } catch (err) {
                toast.error(errorMessage(err))
              } finally {
                setDownloading(false)
              }
            }}
          >
            {downloading ? <Loader2 className="animate-spin" /> : <FileDown />}
            {t('parcel.act')}
          </Button>
        </footer>
      )}

      {parcel && target && (
        <ParcelTransitionDialog
          key={target}
          parcel={parcel}
          target={target}
          onClose={() => setTarget(null)}
        />
      )}
    </aside>
  )
}
