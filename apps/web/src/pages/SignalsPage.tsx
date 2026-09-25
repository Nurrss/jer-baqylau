import { ImageOff, Map as MapIcon, Megaphone, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useSignal, useSignals } from '@/api/queries'
import type { SignalStatus, SignalSummary } from '@/api/types'
import { CopyButton } from '@/components/common/CopyButton'
import { EmptyState, ErrorState } from '@/components/common/States'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { SignalDetailView } from '@/features/signals/SignalDetailView'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/store/ui'

const TABS: Record<string, SignalStatus[]> = {
  open: ['NEW', 'IN_REVIEW'],
  new: ['NEW'],
  review: ['IN_REVIEW'],
  closed: ['CONFIRMED', 'REJECTED'],
  all: [],
}

function SignalCard({
  signal,
  active,
  onClick,
}: {
  signal: SignalSummary
  active: boolean
  onClick: () => void
}) {
  const { t } = useTranslation()
  const { relative } = useDateFns()
  const fresh = useUiStore((s) => s.freshSignalIds.includes(signal.id))
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full gap-3 rounded-xl border bg-card p-3 text-left transition-all hover:border-primary/50 hover:shadow-sm',
        active && 'border-primary ring-2 ring-primary/20',
        fresh && 'animate-slide-in border-signal ring-2 ring-signal/30',
      )}
    >
      <div className="relative size-16 shrink-0 overflow-hidden rounded-lg bg-muted">
        {signal.thumb_url ? (
          <img src={signal.thumb_url} alt="" className="size-full object-cover" loading="lazy" />
        ) : (
          <span className="grid size-full place-items-center text-muted-foreground">
            <ImageOff className="size-5" />
          </span>
        )}
        {signal.photos_count > 1 && (
          <span className="absolute right-1 bottom-1 rounded bg-black/60 px-1 text-[10px] text-white">
            {signal.photos_count}
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <span className="font-mono text-sm font-semibold">{signal.tracking_code}</span>
          <StatusBadge kind="signal" status={signal.status} />
        </div>
        <p className="mt-0.5 text-sm">{t(`signalCategory.${signal.category}`)}</p>
        <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
          {signal.description ?? t('signals.noDescription')}
        </p>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>{relative(signal.created_at)}</span>
          {signal.parcel_cadastral_number && (
            <span className="font-mono">{signal.parcel_cadastral_number}</span>
          )}
          {signal.reports_count > 1 && (
            <span className="flex items-center gap-1 font-medium text-signal">
              <Users className="size-3" /> {t('signals.reports', { count: signal.reports_count })}
            </span>
          )}
        </p>
      </div>
    </button>
  )
}

export function SignalsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [tab, setTab] = useState<keyof typeof TABS>('open')
  const [selected, setSelected] = useState<string | null>(null)
  const statuses = useMemo(() => TABS[tab] ?? [], [tab])
  const list = useSignals(statuses)
  const all = useSignals()
  const detail = useSignal(selected)

  const counts = useMemo(() => {
    const items = all.data?.items ?? []
    return Object.fromEntries(
      Object.entries(TABS).map(([key, st]) => [
        key,
        st.length ? items.filter((s) => st.includes(s.status)).length : items.length,
      ]),
    )
  }, [all.data])

  return (
    <div className="absolute inset-0 grid grid-cols-1 md:grid-cols-[minmax(340px,440px)_1fr]">
      <section className="flex min-h-0 flex-col border-r bg-background">
        <div className="border-b bg-card px-4 pt-4 pb-3">
          <h2 className="text-lg font-semibold">{t('signals.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('signals.subtitle')}</p>
          <Tabs value={tab} onValueChange={(v) => setTab(v as keyof typeof TABS)} className="mt-3">
            <TabsList className="w-full justify-start overflow-x-auto">
              {(Object.keys(TABS) as (keyof typeof TABS)[]).map((key) => (
                <TabsTrigger key={key} value={key}>
                  {t(`signals.tabs.${key}`)}
                  <span className="text-xs text-muted-foreground tabular-nums">{counts[key] ?? 0}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {list.isLoading ? (
            <div className="grid gap-2">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-24 rounded-xl" />
              ))}
            </div>
          ) : list.isError ? (
            <ErrorState error={list.error} onRetry={() => void list.refetch()} />
          ) : list.data?.items.length ? (
            <div className="grid gap-2">
              {list.data.items.map((signal) => (
                <SignalCard
                  key={signal.id}
                  signal={signal}
                  active={selected === signal.id}
                  onClick={() =>
                    // Narrow screens have no detail pane: open the signal on the map instead.
                    window.matchMedia('(min-width: 768px)').matches
                      ? setSelected(signal.id)
                      : navigate(`/map?signal=${signal.id}`)
                  }
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Megaphone className="size-6" />}
              title={t('signals.emptyTitle')}
              description={t('signals.emptyText')}
            />
          )}
        </div>
      </section>

      <section className="hidden min-h-0 overflow-y-auto bg-card md:block">
        {!selected ? (
          <EmptyState
            title={t('signals.selectTitle')}
            description={t('signals.selectText')}
            className="h-full"
          />
        ) : detail.isLoading ? (
          <div className="grid gap-3 p-6">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-44" />
            <Skeleton className="h-32" />
          </div>
        ) : detail.isError ? (
          <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
        ) : detail.data ? (
          <div className="mx-auto max-w-2xl">
            <header className="flex flex-wrap items-center gap-3 px-5 pt-5 pb-4">
              <h2 className="font-mono text-xl font-semibold">{detail.data.tracking_code}</h2>
              <CopyButton value={detail.data.tracking_code} />
              <StatusBadge kind="signal" status={detail.data.status} />
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={() => navigate(`/map?signal=${detail.data.id}`)}
              >
                <MapIcon /> {t('realtime.showOnMap')}
              </Button>
            </header>
            <SignalDetailView
              signal={detail.data}
              onOpenParcel={(parcelId) => navigate(`/map?parcel=${parcelId}`)}
            />
          </div>
        ) : null}
      </section>
    </div>
  )
}
