import { BellRing, FileText, Loader2, MessageCircle, Search, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useApplications, useApplicationTransition } from '@/api/queries'
import { APPLICATION_STATUSES, type Application, type ApplicationStatus } from '@/api/types'
import { CopyButton } from '@/components/common/CopyButton'
import { EmptyState, ErrorState } from '@/components/common/States'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { Checkbox, Tabs, TabsList, TabsTrigger } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { HistoryTimeline } from '@/features/common/History'
import { Section } from '@/features/common/Section'
import { toDateInput, useDateFns } from '@/lib/dates'
import { formatArea } from '@/lib/utils'

function TransitionDialog({
  application,
  target,
  onClose,
}: {
  application: Application
  target: ApplicationStatus
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const errorMessage = useErrorMessage()
  const mutation = useApplicationTransition(application.id)
  const [commentRu, setCommentRu] = useState('')
  const [commentKk, setCommentKk] = useState('')
  const [inspectionDate, setInspectionDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const needsDate = target === 'INSPECTION_SCHEDULED'
  const grants = target === 'APPROVED' && application.parcels.length > 0
  // Housing: one parcel per citizen (first choice by default); agricultural lease: all fields.
  const [granted, setGranted] = useState<string[]>(() =>
    application.type === 'IZHS_ALLOCATION'
      ? application.parcels.slice(0, 1).map((p) => p.id)
      : application.parcels.map((p) => p.id),
  )
  const valid =
    commentRu.trim().length >= 3 &&
    commentKk.trim().length >= 3 &&
    (!needsDate || inspectionDate) &&
    (!grants || granted.length > 0)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    setError(null)
    try {
      const result = await mutation.mutateAsync({
        to: target,
        comment_ru: commentRu.trim(),
        comment_kk: commentKk.trim(),
        inspection_date: needsDate ? inspectionDate : null,
        grant_parcel_ids: grants ? granted : null,
      })
      toast.success(
        result.subscribers_count
          ? t('applications.pushed', { count: result.subscribers_count })
          : t('transition.done', { status: t(`applicationStatus.${target}`) }),
      )
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{t(`transition.action.APPLICATION.${target}`)}</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{application.tracking_number}</span> · {application.applicant_name}
            </DialogDescription>
          </DialogHeader>
          {grants && (
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">{t('land.panel.grantTitle')}</legend>
              {application.parcels.map((p) => (
                <label key={p.id} className="flex items-center gap-3 rounded-lg border p-2 text-sm">
                  <Checkbox
                    checked={granted.includes(p.id)}
                    onCheckedChange={(v) =>
                      setGranted((prev) => (v === true ? [...prev, p.id] : prev.filter((id) => id !== p.id)))
                    }
                  />
                  <span className="text-xs text-muted-foreground">{p.priority}.</span>
                  <span className="font-mono font-semibold">{p.cadastral_number}</span>
                  <span className="text-muted-foreground">
                    {formatArea(p.area_ha, i18n.language)} {t('units.ha')}
                  </span>
                </label>
              ))}
              <p className="text-xs text-muted-foreground">{t(`land.panel.grantHint.${application.type}`)}</p>
            </fieldset>
          )}
          {needsDate && (
            <div className="grid gap-2">
              <Label htmlFor="inspection-date">{t('applications.inspectionDate')} *</Label>
              <Input
                id="inspection-date"
                type="date"
                min={toDateInput(new Date().toISOString())}
                value={inspectionDate}
                onChange={(e) => setInspectionDate(e.target.value)}
              />
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="comment-ru">{t('applications.commentRu')} *</Label>
            <Textarea
              id="comment-ru"
              value={commentRu}
              onChange={(e) => setCommentRu(e.target.value)}
              autoFocus
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="comment-kk">{t('applications.commentKk')} *</Label>
            <Textarea id="comment-kk" value={commentKk} onChange={(e) => setCommentKk(e.target.value)} />
          </div>
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <BellRing className="size-3.5" />{' '}
            {t('applications.pushHint', { count: application.subscribers_count })}
          </p>
          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={!valid || mutation.isPending}
              variant={target === 'REJECTED' ? 'destructive' : 'default'}
            >
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {t('common.confirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ApplicationPanel({ application, onClose }: { application: Application; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { date, dateTime } = useDateFns()
  const [target, setTarget] = useState<ApplicationStatus | null>(null)
  const comment = i18n.language === 'kk' ? application.status_comment_kk : application.status_comment_ru

  return (
    <aside className="absolute top-0 right-0 bottom-0 z-20 flex w-full max-w-[440px] animate-slide-in flex-col border-l bg-card shadow-2xl">
      <header className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{t(`applicationType.${application.type}`)}</p>
          <div className="flex items-center gap-1">
            <h2 className="font-mono text-lg font-semibold">{application.tracking_number}</h2>
            <CopyButton value={application.tracking_number} />
          </div>
          <StatusBadge kind="application" status={application.status} className="mt-1" />
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t('common.close')}>
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Section title={t('applications.actions')}>
          {application.allowed_transitions.length ? (
            <div className="flex flex-wrap gap-2">
              {application.allowed_transitions.map((to) => (
                <Button
                  key={to}
                  size="sm"
                  variant={to === 'REJECTED' ? 'destructive' : to === 'APPROVED' ? 'success' : 'default'}
                  onClick={() => setTarget(to)}
                >
                  {t(`transition.action.APPLICATION.${to}`)}
                </Button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('applications.final')}</p>
          )}
        </Section>
        <Section title={t('applications.details')}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">{t('applications.applicant')}</dt>
            <dd className="font-medium">{application.applicant_name}</dd>
            {application.source === 'miniapp' && (
              <>
                <dt className="text-muted-foreground">{t('land.panel.source')}</dt>
                <dd>
                  <Badge variant="secondary">
                    <MessageCircle className="size-3" /> Telegram Mini App
                  </Badge>
                </dd>
                <dt className="text-muted-foreground">{t('land.panel.iin')}</dt>
                <dd className="font-mono">{application.applicant_iin_masked}</dd>
                <dt className="text-muted-foreground">{t('land.panel.phone')}</dt>
                <dd className="font-mono">{application.applicant_phone_masked}</dd>
              </>
            )}
            <dt className="text-muted-foreground">{t('applications.submitted')}</dt>
            <dd>{dateTime(application.submitted_at)}</dd>
            {application.inspection_date && (
              <>
                <dt className="text-muted-foreground">{t('applications.inspectionDate')}</dt>
                <dd>{date(application.inspection_date)}</dd>
              </>
            )}
            {application.parcels.length === 0 && (
              <>
                <dt className="text-muted-foreground">{t('signals.parcel')}</dt>
                <dd>
                  {application.parcel_id ? (
                    <button
                      type="button"
                      className="font-mono text-primary hover:underline"
                      onClick={() => navigate(`/map?parcel=${application.parcel_id}`)}
                    >
                      {application.parcel_cadastral_number}
                    </button>
                  ) : (
                    '—'
                  )}
                </dd>
              </>
            )}
            <dt className="text-muted-foreground">{t('applications.subscribers')}</dt>
            <dd>
              <Badge variant="secondary">
                <BellRing className="size-3" /> {application.subscribers_count}
              </Badge>
            </dd>
          </dl>
          {application.applicant_comment && (
            <p className="mt-3 rounded-lg bg-muted/60 p-3 text-sm">«{application.applicant_comment}»</p>
          )}
          {comment && <p className="mt-3 rounded-lg bg-muted/60 p-3 text-sm">{comment}</p>}
        </Section>
        {application.parcels.length > 0 && (
          <Section title={t('land.panel.parcels', { count: application.parcels.length })}>
            <ol className="grid gap-2">
              {application.parcels.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/map?parcel=${p.id}`)}
                    className="flex w-full items-center gap-3 rounded-lg border p-2 text-left text-sm hover:bg-muted"
                  >
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold">
                      {p.priority}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono font-semibold">{p.cadastral_number}</span>
                      <span className="block text-xs text-muted-foreground">
                        {t(`purpose.${p.purpose}`)} · {formatArea(p.area_ha, i18n.language)} {t('units.ha')}
                      </span>
                    </span>
                    {p.granted ? (
                      <Badge variant="success">{t('land.panel.granted')}</Badge>
                    ) : (
                      <Badge variant="outline">{t(`allocation.${p.allocation_status}`)}</Badge>
                    )}
                  </button>
                </li>
              ))}
            </ol>
            {application.parcels.length > 1 && (
              <p className="mt-2 text-xs text-muted-foreground">{t('land.panel.priorityNote')}</p>
            )}
          </Section>
        )}
        <Section title={t('history.title')}>
          <HistoryTimeline items={application.history} kind="application" />
        </Section>
      </div>
      {target && (
        <TransitionDialog
          key={target}
          application={application}
          target={target}
          onClose={() => setTarget(null)}
        />
      )}
    </aside>
  )
}

export function ApplicationsPage() {
  const { t } = useTranslation()
  const { date } = useDateFns()
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('all')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [params] = useSearchParams()
  // Deep link from «Сегодня» / search: /applications?id=<uuid>
  const [selectedId, setSelectedId] = useState<string | null>(params.get('id'))
  const query = useApplications(status === 'all' ? [] : [status], q)
  const selected = query.data?.items.find((a) => a.id === selectedId) ?? null

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-7xl p-4 md:p-6">
          <h2 className="text-xl font-semibold">{t('applications.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('applications.subtitle')}</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Tabs value={status} onValueChange={(v) => setStatus(v as ApplicationStatus | 'all')}>
              <TabsList>
                <TabsTrigger value="all">{t('common.all')}</TabsTrigger>
                {APPLICATION_STATUSES.map((s) => (
                  <TabsTrigger key={s} value={s}>
                    {t(`applicationStatus.${s}`)}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <div className="relative w-64">
              <Search className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('applications.search')}
                className="pl-9"
              />
            </div>
          </div>
          <div className="mt-4 overflow-x-auto rounded-xl border bg-card">
            {query.isLoading ? (
              <div className="grid gap-2 p-4">
                {Array.from({ length: 6 }, (_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : query.isError ? (
              <ErrorState error={query.error} onRetry={() => void query.refetch()} />
            ) : !query.data?.items.length ? (
              <EmptyState icon={<FileText className="size-6" />} title={t('applications.empty')} />
            ) : (
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground uppercase">
                  <tr>
                    <th className="px-4 py-3 font-semibold">{t('applications.number')}</th>
                    <th className="px-4 py-3 font-semibold">{t('applications.applicant')}</th>
                    <th className="px-4 py-3 font-semibold">{t('applications.type')}</th>
                    <th className="px-4 py-3 font-semibold">{t('parcel.status')}</th>
                    <th className="px-4 py-3 font-semibold">{t('applications.submitted')}</th>
                    <th className="px-4 py-3 font-semibold">{t('applications.subscribers')}</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((a) => (
                    <tr
                      key={a.id}
                      onClick={() => setSelectedId(a.id)}
                      className={`cursor-pointer border-b last:border-0 hover:bg-muted/50 ${selectedId === a.id ? 'bg-primary/5' : ''}`}
                    >
                      <td className="px-4 py-3 font-mono font-medium">{a.tracking_number}</td>
                      <td className="px-4 py-3">{a.applicant_name}</td>
                      <td className="px-4 py-3">{t(`applicationType.${a.type}`)}</td>
                      <td className="px-4 py-3">
                        <StatusBadge kind="application" status={a.status} />
                      </td>
                      <td className="px-4 py-3 tabular-nums">{date(a.submitted_at)}</td>
                      <td className="px-4 py-3 tabular-nums">{a.subscribers_count || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
      {selected && (
        <ApplicationPanel key={selected.id} application={selected} onClose={() => setSelectedId(null)} />
      )}
    </div>
  )
}
