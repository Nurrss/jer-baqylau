import {
  AlarmClock,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  FileText,
  GraduationCap,
  Map as MapIcon,
  Megaphone,
  MessageSquareReply,
  Search,
  ShieldCheck,
  Smartphone,
  X,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { useApplications, useDashboard, useSignals } from '@/api/queries'
import { EmptyState, ErrorState } from '@/components/common/States'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { DeadlineChip } from '@/features/parcel/ParcelPanel'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { useGuideStore } from '@/store/guide'

const LIST_LIMIT = 4

function TaskCard({
  icon,
  title,
  count,
  tone,
  hint,
  children,
  footer,
  loading,
}: {
  icon: ReactNode
  title: string
  count: number | undefined
  tone: 'signal' | 'danger' | 'primary'
  hint: string
  children: ReactNode
  footer: ReactNode
  loading: boolean
}) {
  const toneClass = {
    signal: 'bg-signal/10 text-signal',
    danger: 'bg-destructive/10 text-destructive',
    primary: 'bg-primary/10 text-primary',
  }[tone]
  return (
    <Card className="flex flex-col">
      <div className="flex items-start gap-3 p-4 pb-3">
        <span className={cn('grid size-10 shrink-0 place-items-center rounded-xl [&_svg]:size-5', toneClass)}>
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <span className="text-2xl font-semibold tabular-nums">{loading ? '…' : (count ?? 0)}</span>
      </div>
      <div className="flex-1 px-2">{loading ? <Skeleton className="mx-2 h-32" /> : children}</div>
      <div className="border-t p-2">{footer}</div>
    </Card>
  )
}

function Row({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted"
    >
      {children}
      <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  )
}

function HowItWorks() {
  const { t } = useTranslation()
  const steps = [
    { icon: <Smartphone />, key: 'report' },
    { icon: <MapIcon />, key: 'map' },
    { icon: <ShieldCheck />, key: 'inspect' },
    { icon: <MessageSquareReply />, key: 'notify' },
  ]
  return (
    <Card className="p-4">
      <p className="mb-3 text-sm font-semibold">{t('home.how.title')}</p>
      <ol className="grid gap-3 md:grid-cols-4">
        {steps.map((step, i) => (
          <li key={step.key} className="relative flex gap-3 rounded-xl bg-muted/50 p-3">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-card text-primary shadow-xs [&_svg]:size-4">
              {step.icon}
            </span>
            <span className="text-sm">
              <span className="block font-medium">
                {i + 1}. {t(`home.how.${step.key}.title`)}
              </span>
              <span className="block text-xs text-muted-foreground">{t(`home.how.${step.key}.text`)}</span>
            </span>
          </li>
        ))}
      </ol>
    </Card>
  )
}

export function HomePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { relative, locale } = useDateFns()
  const user = useAuthStore((s) => s.user)
  const { seen, startOnce, start, setPaletteOpen } = useGuideStore()
  const [bannerHidden, setBannerHidden] = useState(false)

  const signals = useSignals(['NEW', 'IN_REVIEW'])
  const dashboard = useDashboard()
  const applications = useApplications(['UNDER_REVIEW', 'INSPECTION_SCHEDULED'], '')

  // First visit: offer the guided tour automatically.
  useEffect(() => {
    const timer = window.setTimeout(() => startOnce('main'), 600)
    return () => window.clearTimeout(timer)
  }, [startOnce])

  const deadlines = dashboard.data?.upcoming_deadlines ?? []
  const overdue = deadlines.filter((d) => d.days_left < 0).length
  const newSignals = (signals.data?.items ?? []).filter((s) => s.status === 'NEW').length
  const pendingApps = applications.data?.total ?? 0
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'morning' : hour < 18 ? 'day' : 'evening'
  const today = new Intl.DateTimeFormat(locale.code, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date())
  const allClear =
    !signals.isLoading && !dashboard.isLoading && newSignals === 0 && overdue === 0 && pendingApps === 0

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="mx-auto grid max-w-7xl gap-5 p-4 md:p-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm text-muted-foreground first-letter:uppercase">{today}</p>
            <h2 className="text-2xl font-semibold tracking-tight">
              {t(`home.greeting.${greeting}`, { name: user?.name ?? '' })}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {allClear
                ? t('home.allClear')
                : t('home.summary', { signals: newSignals, overdue, applications: pendingApps })}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setPaletteOpen(true)}>
              <Search /> {t('home.actions.find')}
              <kbd className="ml-1 rounded border bg-muted px-1 text-[10px] text-muted-foreground">
                Ctrl K
              </kbd>
            </Button>
            <Button onClick={() => navigate('/map')}>
              <MapIcon /> {t('home.actions.map')}
            </Button>
          </div>
        </header>

        {!seen.includes('main') && !bannerHidden && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4">
            <GraduationCap className="size-6 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{t('home.onboarding.title')}</p>
              <p className="text-xs text-muted-foreground">{t('home.onboarding.text')}</p>
            </div>
            <Button size="sm" onClick={() => start('main')}>
              {t('home.onboarding.start')}
            </Button>
            <button
              type="button"
              className="rounded p-1 text-muted-foreground hover:bg-muted"
              onClick={() => setBannerHidden(true)}
              aria-label={t('common.close')}
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-3" data-tour="home-tasks">
          <TaskCard
            icon={<Megaphone />}
            tone="signal"
            title={t('home.tasks.signals.title')}
            hint={t('home.tasks.signals.hint')}
            count={signals.data?.total}
            loading={signals.isLoading}
            footer={
              <Button variant="ghost" size="sm" className="w-full" asChild>
                <Link to="/signals">
                  {t('home.tasks.signals.all')} <ArrowRight />
                </Link>
              </Button>
            }
          >
            {signals.isError ? (
              <ErrorState error={signals.error} className="py-4" />
            ) : signals.data?.items.length ? (
              signals.data.items.slice(0, LIST_LIMIT).map((s) => (
                <Row key={s.id} onClick={() => navigate(`/map?signal=${s.id}`)}>
                  {s.thumb_url ? (
                    <img src={s.thumb_url} alt="" className="size-9 shrink-0 rounded-md object-cover" />
                  ) : (
                    <span className="grid size-9 place-items-center rounded-md bg-muted">
                      <Megaphone className="size-4 text-muted-foreground" />
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-xs font-semibold">{s.tracking_code}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {t(`signalCategory.${s.category}`)} · {relative(s.created_at)}
                    </span>
                  </span>
                  <StatusBadge kind="signal" status={s.status} />
                </Row>
              ))
            ) : (
              <EmptyState
                icon={<CheckCircle2 className="size-6" />}
                title={t('home.tasks.signals.empty')}
                className="py-6"
              />
            )}
          </TaskCard>

          <TaskCard
            icon={<AlarmClock />}
            tone="danger"
            title={t('home.tasks.deadlines.title')}
            hint={t('home.tasks.deadlines.hint', { overdue })}
            count={deadlines.length}
            loading={dashboard.isLoading}
            footer={
              <Button variant="ghost" size="sm" className="w-full" asChild>
                <Link to="/violations">
                  {t('home.tasks.deadlines.all')} <ArrowRight />
                </Link>
              </Button>
            }
          >
            {dashboard.isError ? (
              <ErrorState error={dashboard.error} className="py-4" />
            ) : deadlines.length ? (
              deadlines.slice(0, LIST_LIMIT).map((d) => (
                <Row key={d.parcel_id} onClick={() => navigate(`/map?parcel=${d.parcel_id}`)}>
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-xs font-semibold">{d.cadastral_number}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {d.violation_type ? t(`violationType.${d.violation_type}`) : ''}
                    </span>
                  </span>
                  <DeadlineChip deadline={d.deadline_at} active />
                </Row>
              ))
            ) : (
              <EmptyState
                icon={<CheckCircle2 className="size-6" />}
                title={t('home.tasks.deadlines.empty')}
                className="py-6"
              />
            )}
          </TaskCard>

          <TaskCard
            icon={<FileText />}
            tone="primary"
            title={t('home.tasks.applications.title')}
            hint={t('home.tasks.applications.hint')}
            count={applications.data?.total}
            loading={applications.isLoading}
            footer={
              <Button variant="ghost" size="sm" className="w-full" asChild>
                <Link to="/applications">
                  {t('home.tasks.applications.all')} <ArrowRight />
                </Link>
              </Button>
            }
          >
            {applications.isError ? (
              <ErrorState error={applications.error} className="py-4" />
            ) : applications.data?.items.length ? (
              applications.data.items.slice(0, LIST_LIMIT).map((a) => (
                <Row key={a.id} onClick={() => navigate(`/applications?id=${a.id}`)}>
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-xs font-semibold">{a.tracking_number}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {a.applicant_name} · {t(`applicationType.${a.type}`)}
                    </span>
                  </span>
                  <StatusBadge kind="application" status={a.status} />
                </Row>
              ))
            ) : (
              <EmptyState
                icon={<CheckCircle2 className="size-6" />}
                title={t('home.tasks.applications.empty')}
                className="py-6"
              />
            )}
          </TaskCard>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <HowItWorks />
          <Card className="grid content-start gap-2 p-4 lg:w-72">
            <p className="text-sm font-semibold">{t('home.quick.title')}</p>
            <Button variant="outline" className="justify-start" asChild>
              <Link to="/dashboard">
                <BarChart3 /> {t('home.quick.dashboard')}
              </Link>
            </Button>
            <Button variant="outline" className="justify-start" asChild>
              <Link to="/violations">
                <AlarmClock /> {t('home.quick.overdue')}
              </Link>
            </Button>
            <Button
              variant="outline"
              className="justify-start"
              onClick={() => useGuideStore.getState().setHelpOpen(true)}
            >
              <GraduationCap /> {t('home.quick.help')}
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
