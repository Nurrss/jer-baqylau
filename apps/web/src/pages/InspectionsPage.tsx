import { ClipboardCheck, Dices, Gauge, Loader2, MapPin, ShieldCheck, Sparkles, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MapGL, { Layer, Marker, Source } from 'react-map-gl/maplibre'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useCreatePlan,
  useInspection,
  useInspections,
  useParcels,
  useReviewInspection,
  useRisk,
} from '@/api/queries'
import type { Inspection, InspectionStatus, RiskItem } from '@/api/types'
import { EmptyState, ErrorState } from '@/components/common/States'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { PhotoGallery } from '@/features/common/PhotoGallery'
import { CheckList, VerdictBadge } from '@/features/integrity/CheckList'
import { InspectionLink } from '@/features/integrity/RequestInspectionDialog'
import { baseStyle } from '@/features/map/mapStyle'
import { Section } from '@/features/common/Section'
import { useDateFns } from '@/lib/dates'
import { PARCEL_STATUS_COLORS } from '@/lib/status'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { cn } from '@/lib/utils'

const STATUS_TABS: Record<string, InspectionStatus[]> = {
  review: ['SUBMITTED'],
  waiting: ['REQUESTED'],
  closed: ['ACCEPTED', 'REJECTED', 'EXPIRED'],
  all: [],
}

function InspectionStatusBadge({ status }: { status: InspectionStatus }) {
  const { t } = useTranslation()
  const variant = {
    REQUESTED: 'secondary',
    SUBMITTED: 'warning',
    ACCEPTED: 'success',
    REJECTED: 'destructive',
    EXPIRED: 'outline',
  }[status] as 'secondary' | 'warning' | 'success' | 'destructive' | 'outline'
  return <Badge variant={variant}>{t(`inspectionStatus.${status}`)}</Badge>
}

// ── Risk plan ───────────────────────────────────────────────────────────────

function RiskRow({ item }: { item: RiskItem }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      onClick={() => navigate(`/map?parcel=${item.parcel_id}`)}
      className="grid w-full grid-cols-[3.5rem_1fr] items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-muted"
    >
      <span className="grid gap-1">
        <span className="text-lg font-semibold tabular-nums">{item.score}</span>
        <span className="h-1.5 overflow-hidden rounded-full bg-muted">
          <span
            className={cn(
              'block h-full rounded-full',
              item.score >= 50 ? 'bg-destructive' : item.score >= 25 ? 'bg-accent' : 'bg-primary',
            )}
            style={{ width: `${item.score}%` }}
          />
        </span>
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold">{item.cadastral_number}</span>
          <StatusBadge kind="parcel" status={item.status} />
        </span>
        <span className="mt-1 flex flex-wrap gap-1.5">
          {item.factors.length ? (
            item.factors.map((f) => (
              <span key={f.code} className="rounded-md bg-muted px-1.5 py-0.5 text-[11px]">
                {t(`risk.${f.code}`, f.params)} <span className="text-muted-foreground">+{f.points}</span>
              </span>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">{t('risk.none')}</span>
          )}
        </span>
      </span>
    </button>
  )
}

function PlanDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const plan = useCreatePlan()
  const [size, setSize] = useState(5)
  const [randomShare, setRandomShare] = useState(20)
  const result = plan.data
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent wide>
        <DialogHeader>
          <DialogTitle>{t('plan.title')}</DialogTitle>
          <DialogDescription>{t('plan.subtitle')}</DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="grid gap-3">
            <p className="text-sm">
              {t('plan.created', { count: result.created.length })}{' '}
              <span className="text-muted-foreground">{t('plan.seed', { seed: result.seed })}</span>
            </p>
            <div className="grid max-h-[55vh] gap-3 overflow-y-auto sm:grid-cols-2 [&>*]:min-w-0">
              {result.created.map((item) => (
                <Card key={item.id} className="grid gap-2 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-semibold">{item.cadastral_number}</span>
                    <Badge variant={item.reason === 'RANDOM' ? 'secondary' : 'warning'}>
                      {t(`inspectionReason.${item.reason}`)}
                    </Badge>
                  </div>
                  <InspectionLink inspection={item} />
                </Card>
              ))}
            </div>
            <DialogFooter>
              <Button onClick={onClose}>{t('common.close')}</Button>
            </DialogFooter>
          </div>
        ) : (
          <form
            className="grid gap-4"
            onSubmit={async (e) => {
              e.preventDefault()
              try {
                await plan.mutateAsync({ size, random_share: randomShare / 100 })
              } catch (err) {
                toast.error(errorMessage(err))
              }
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="plan-size">{t('plan.size')}</Label>
                <Input
                  id="plan-size"
                  type="number"
                  min={1}
                  max={20}
                  value={size}
                  onChange={(e) => setSize(Number(e.target.value))}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="plan-random">{t('plan.randomShare')}</Label>
                <Input
                  id="plan-random"
                  type="number"
                  min={0}
                  max={100}
                  step={10}
                  value={randomShare}
                  onChange={(e) => setRandomShare(Number(e.target.value))}
                />
              </div>
            </div>
            <ul className="grid gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
              <li className="flex gap-2">
                <Gauge className="size-4 shrink-0" /> {t('plan.explainRisk')}
              </li>
              <li className="flex gap-2">
                <Dices className="size-4 shrink-0" /> {t('plan.explainRandom')}
              </li>
            </ul>
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={plan.isPending}>
                {plan.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} {t('plan.create')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Owner report detail ─────────────────────────────────────────────────────

function ReportMap({ inspection }: { inspection: Inspection }) {
  const parcels = useParcels().data
  const style = useMemo(() => baseStyle(), [])
  const parcel = parcels?.features.find((f) => f.id === inspection.parcel_id)
  const center = (inspection.device ?? parcel?.properties) ? inspection.device : null
  if (!parcel && !inspection.device) return null
  const points = parcel ? (parcel.geometry.coordinates as number[][][][]).flat(2) : []
  const lon = center?.lon ?? (points.length ? points.reduce((s, p) => s + p[0]!, 0) / points.length : 71.36)
  const lat = center?.lat ?? (points.length ? points.reduce((s, p) => s + p[1]!, 0) / points.length : 42.93)
  return (
    <div className="h-52 overflow-hidden rounded-lg border">
      <MapGL
        key={inspection.id}
        initialViewState={{ longitude: lon, latitude: lat, zoom: 16 }}
        mapStyle={style}
        attributionControl={false}
        style={{ width: '100%', height: '100%' }}
      >
        {parcel && (
          <Source id="report-parcel" type="geojson" data={parcel}>
            <Layer
              id="report-parcel-fill"
              type="fill"
              paint={{ 'fill-color': PARCEL_STATUS_COLORS[parcel.properties.status], 'fill-opacity': 0.25 }}
            />
            <Layer
              id="report-parcel-line"
              type="line"
              paint={{ 'line-color': '#0b6aa8', 'line-width': 2.5 }}
            />
          </Source>
        )}
        {inspection.device && (
          <Marker longitude={inspection.device.lon} latitude={inspection.device.lat} anchor="bottom">
            <MapPin className="size-7 fill-destructive text-white drop-shadow" />
          </Marker>
        )}
      </MapGL>
    </div>
  )
}

function ReviewDialog({
  inspection,
  decision,
  onClose,
}: {
  inspection: Inspection
  decision: 'ACCEPTED' | 'REJECTED'
  onClose: () => void
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const review = useReviewInspection(inspection.id)
  const [comment, setComment] = useState('')
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={async (e) => {
            e.preventDefault()
            try {
              await review.mutateAsync({ decision, comment: comment.trim() })
              toast.success(t(`inspections.reviewed.${decision}`))
              onClose()
            } catch (err) {
              toast.error(errorMessage(err))
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{t(`inspections.decide.${decision}`)}</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{inspection.code}</span> · {inspection.cadastral_number}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="review-comment">{t('transition.comment')} *</Label>
            <Textarea
              id="review-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={comment.trim().length < 3 || review.isPending}
              variant={decision === 'REJECTED' ? 'destructive' : 'success'}
            >
              {review.isPending && <Loader2 className="animate-spin" />} {t('common.confirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ReportPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { dateTime } = useDateFns()
  const query = useInspection(id)
  const [decision, setDecision] = useState<'ACCEPTED' | 'REJECTED' | null>(null)
  const item = query.data
  return (
    <aside className="absolute top-0 right-0 bottom-0 z-20 flex w-full max-w-[460px] animate-slide-in flex-col border-l bg-card shadow-2xl">
      <header className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{t('inspections.report')}</p>
          {item ? (
            <>
              <h2 className="font-mono text-lg font-semibold">{item.code}</h2>
              <div className="mt-1 flex flex-wrap gap-2">
                <InspectionStatusBadge status={item.status} />
                <VerdictBadge verdict={item.verdict} />
              </div>
            </>
          ) : (
            <Skeleton className="mt-1 h-7 w-40" />
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t('common.close')}>
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {item && (
          <>
            {item.status === 'SUBMITTED' && (
              <Section title={t('inspections.decision')}>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="success"
                    disabled={item.verdict === 'FAIL'}
                    onClick={() => setDecision('ACCEPTED')}
                  >
                    {t('inspections.decide.ACCEPTED')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setDecision('REJECTED')}>
                    {t('inspections.decide.REJECTED')}
                  </Button>
                </div>
                {item.verdict === 'FAIL' && (
                  <p className="mt-2 text-xs text-destructive">{t('inspections.failNote')}</p>
                )}
              </Section>
            )}
            {item.checks.length > 0 && (
              <Section title={t('inspections.antifraud')} icon={<ShieldCheck className="size-3.5" />}>
                <CheckList checks={item.checks} />
              </Section>
            )}
            {item.status === 'REQUESTED' && (
              <Section title={t('inspections.waitingOwner')}>
                <InspectionLink inspection={item} />
              </Section>
            )}
            <Section title={t('inspections.details')}>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">{t('signals.parcel')}</dt>
                <dd>
                  <button
                    type="button"
                    className="font-mono text-primary hover:underline"
                    onClick={() => navigate(`/map?parcel=${item.parcel_id}`)}
                  >
                    {item.cadastral_number}
                  </button>
                </dd>
                <dt className="text-muted-foreground">{t('inspections.reason')}</dt>
                <dd>{t(`inspectionReason.${item.reason}`)}</dd>
                <dt className="text-muted-foreground">{t('inspections.requested')}</dt>
                <dd>{dateTime(item.created_at)}</dd>
                <dt className="text-muted-foreground">{t('inspections.due')}</dt>
                <dd>{dateTime(item.due_at)}</dd>
                {item.submitted_at && (
                  <>
                    <dt className="text-muted-foreground">{t('inspections.submitted')}</dt>
                    <dd>{dateTime(item.submitted_at)}</dd>
                  </>
                )}
                {item.declared_use && (
                  <>
                    <dt className="text-muted-foreground">{t('inspections.declared')}</dt>
                    <dd className="font-medium">{t(`declaredUse.${item.declared_use}`)}</dd>
                  </>
                )}
                {item.accuracy_m != null && (
                  <>
                    <dt className="text-muted-foreground">GPS</dt>
                    <dd>± {Math.round(item.accuracy_m)} м</dd>
                  </>
                )}
              </dl>
              {item.owner_comment && (
                <p className="mt-3 rounded-lg bg-muted/60 p-3 text-sm">«{item.owner_comment}»</p>
              )}
              {item.review_comment && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {t('inspections.reviewComment')}: «{item.review_comment}»
                </p>
              )}
            </Section>
            {(item.device || item.photos.length > 0) && (
              <Section title={t('inspections.evidence')}>
                <div className="grid gap-3">
                  <ReportMap inspection={item} />
                  {item.device && (
                    <p className="text-xs text-muted-foreground">{t('inspections.mapLegend')}</p>
                  )}
                  <PhotoGallery photos={item.photos} />
                </div>
              </Section>
            )}
          </>
        )}
      </div>
      {item && decision && (
        <ReviewDialog inspection={item} decision={decision} onClose={() => setDecision(null)} />
      )}
    </aside>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export function InspectionsPage() {
  const { t } = useTranslation()
  const { relative } = useDateFns()
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(params.get('id') ? 'reports' : 'plan')
  const [statusTab, setStatusTab] = useState<keyof typeof STATUS_TABS>('review')
  const [planOpen, setPlanOpen] = useState(false)
  const selected = params.get('id')
  const risk = useRisk(40)
  const inspections = useInspections(STATUS_TABS[statusTab] ?? [])

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="h-full overflow-y-auto">
        <div className="mx-auto grid max-w-6xl gap-4 p-4 md:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">{t('inspections.title')}</h2>
              <p className="text-sm text-muted-foreground">{t('inspections.subtitle')}</p>
            </div>
            <Button onClick={() => setPlanOpen(true)}>
              <Sparkles /> {t('plan.open')}
            </Button>
          </div>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="plan">
                <Gauge className="size-4" /> {t('inspections.tabs.risk')}
              </TabsTrigger>
              <TabsTrigger value="reports">
                <ClipboardCheck className="size-4" /> {t('inspections.tabs.reports')}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="plan" className="mt-4">
              <Card className="p-2">
                <p className="px-3 pt-2 pb-1 text-xs text-muted-foreground">{t('risk.explain')}</p>
                {risk.isLoading ? (
                  <div className="grid gap-2 p-3">
                    {Array.from({ length: 6 }, (_, i) => (
                      <Skeleton key={i} className="h-12" />
                    ))}
                  </div>
                ) : risk.isError ? (
                  <ErrorState error={risk.error} onRetry={() => void risk.refetch()} />
                ) : (
                  risk.data?.map((item) => <RiskRow key={item.parcel_id} item={item} />)
                )}
              </Card>
            </TabsContent>

            <TabsContent value="reports" className="mt-4 grid gap-3">
              <Tabs value={statusTab} onValueChange={(v) => setStatusTab(v as keyof typeof STATUS_TABS)}>
                <TabsList>
                  {Object.keys(STATUS_TABS).map((key) => (
                    <TabsTrigger key={key} value={key}>
                      {t(`inspections.status.${key}`)}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <Card className="overflow-hidden">
                {inspections.isLoading ? (
                  <div className="grid gap-2 p-3">
                    {Array.from({ length: 4 }, (_, i) => (
                      <Skeleton key={i} className="h-12" />
                    ))}
                  </div>
                ) : inspections.isError ? (
                  <ErrorState error={inspections.error} onRetry={() => void inspections.refetch()} />
                ) : !inspections.data?.items.length ? (
                  <EmptyState
                    icon={<ClipboardCheck className="size-6" />}
                    title={t('inspections.empty')}
                    description={t('inspections.emptyHint')}
                  />
                ) : (
                  <ul className="divide-y">
                    {inspections.data.items.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setParams({ id: item.id })}
                          className={cn(
                            'flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/60',
                            selected === item.id && 'bg-primary/5',
                          )}
                        >
                          {item.photos[0] ? (
                            <img
                              src={item.photos[0].thumb_url}
                              alt=""
                              className="size-10 rounded object-cover"
                            />
                          ) : (
                            <span className="grid size-10 place-items-center rounded bg-muted">
                              <ClipboardCheck className="size-4 text-muted-foreground" />
                            </span>
                          )}
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="font-mono text-sm font-semibold">{item.code}</span>
                              <span className="font-mono text-xs text-muted-foreground">
                                {item.cadastral_number}
                              </span>
                            </span>
                            <span className="block text-xs text-muted-foreground">
                              {t(`inspectionReason.${item.reason}`)} ·{' '}
                              {relative(item.submitted_at ?? item.created_at)}
                            </span>
                          </span>
                          <VerdictBadge verdict={item.verdict} />
                          <InspectionStatusBadge status={item.status} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
      {selected && <ReportPanel key={selected} id={selected} onClose={() => setParams({})} />}
      {planOpen && <PlanDialog onClose={() => setPlanOpen(false)} />}
    </div>
  )
}
