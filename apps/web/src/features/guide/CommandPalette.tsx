import * as DialogPrimitive from '@radix-ui/react-dialog'
import {
  BarChart3,
  ClipboardCheck,
  CornerDownLeft,
  FileText,
  Home,
  Loader2,
  Map as MapIcon,
  Megaphone,
  Search,
  ShieldAlert,
  SquareDashed,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useApplications, useParcelSearch, useSignals } from '@/api/queries'
import { StatusBadge } from '@/components/common/StatusBadge'
import { cn } from '@/lib/utils'
import { useGuideStore } from '@/store/guide'
import { useUiStore } from '@/store/ui'

interface Item {
  id: string
  group: 'pages' | 'parcels' | 'signals' | 'applications'
  icon: ReactNode
  title: string
  subtitle?: string
  badge?: ReactNode
  run: () => void
}

const MAX_PER_GROUP = 5

export function CommandPalette() {
  const open = useGuideStore((s) => s.paletteOpen)
  const setOpen = useGuideStore((s) => s.setPaletteOpen)
  // Mounted only while open, so the query resets every time.
  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      {open && <PaletteBody setOpen={setOpen} />}
    </DialogPrimitive.Root>
  )
}

function PaletteBody({ setOpen }: { setOpen: (open: boolean) => void }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 200)
    return () => window.clearTimeout(timer)
  }, [query])

  const parcels = useParcelSearch(debounced)
  const signals = useSignals()
  const applications = useApplications([], '')

  const go = (fn: () => void) => () => {
    setOpen(false)
    fn()
  }

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase()
    const pages: Item[] = [
      { id: 'p-home', to: '/', icon: <Home />, key: 'home' },
      { id: 'p-map', to: '/map', icon: <MapIcon />, key: 'map' },
      { id: 'p-signals', to: '/signals', icon: <Megaphone />, key: 'signals' },
      { id: 'p-violations', to: '/violations', icon: <ShieldAlert />, key: 'violations' },
      { id: 'p-applications', to: '/applications', icon: <FileText />, key: 'applications' },
      { id: 'p-inspections', to: '/inspections', icon: <ClipboardCheck />, key: 'inspections' },
      { id: 'p-dashboard', to: '/dashboard', icon: <BarChart3 />, key: 'dashboard' },
    ]
      .filter((p) => !q || t(`nav.${p.key}`).toLowerCase().includes(q))
      .map((p) => ({
        id: p.id,
        group: 'pages' as const,
        icon: p.icon,
        title: t(`nav.${p.key}`),
        subtitle: t(`nav.hint.${p.key}`),
        run: go(() => navigate(p.to)),
      }))
    if (!q) return pages

    const parcelItems: Item[] = (parcels.data ?? []).slice(0, MAX_PER_GROUP).map((p) => ({
      id: `parcel-${p.id}`,
      group: 'parcels',
      icon: <SquareDashed />,
      title: p.cadastral_number,
      subtitle: i18n.language === 'kk' ? p.address_kk : p.address_ru,
      badge: <StatusBadge kind="parcel" status={p.status} />,
      run: go(() => {
        navigate('/map')
        useUiStore.getState().selectParcel(p.id)
        useUiStore.getState().flyTo({ bbox: p.bbox as [number, number, number, number] })
      }),
    }))
    const signalItems: Item[] = (signals.data?.items ?? [])
      .filter((s) =>
        `${s.tracking_code} ${s.description ?? ''} ${s.parcel_cadastral_number ?? ''}`
          .toLowerCase()
          .includes(q),
      )
      .slice(0, MAX_PER_GROUP)
      .map((s) => ({
        id: `signal-${s.id}`,
        group: 'signals',
        icon: <Megaphone />,
        title: s.tracking_code,
        subtitle: `${t(`signalCategory.${s.category}`)}${s.description ? ` · ${s.description}` : ''}`,
        badge: <StatusBadge kind="signal" status={s.status} />,
        run: go(() => navigate(`/map?signal=${s.id}`)),
      }))
    const applicationItems: Item[] = (applications.data?.items ?? [])
      .filter((a) => `${a.tracking_number} ${a.applicant_name}`.toLowerCase().includes(q))
      .slice(0, MAX_PER_GROUP)
      .map((a) => ({
        id: `app-${a.id}`,
        group: 'applications',
        icon: <FileText />,
        title: a.tracking_number,
        subtitle: `${a.applicant_name} · ${t(`applicationType.${a.type}`)}`,
        badge: <StatusBadge kind="application" status={a.status} />,
        run: go(() => navigate(`/applications?id=${a.id}`)),
      }))
    return [...pages, ...parcelItems, ...signalItems, ...applicationItems]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, parcels.data, signals.data, applications.data, i18n.language])

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      items[active]?.run()
    }
  }

  let lastGroup = ''
  return (
    <>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[90] bg-black/40 backdrop-blur-[1px]" />
        <DialogPrimitive.Content
          className="fixed top-[12vh] left-1/2 z-[91] w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-card text-card-foreground shadow-2xl"
          onKeyDown={onKeyDown}
        >
          <DialogPrimitive.Title className="sr-only">{t('palette.title')}</DialogPrimitive.Title>
          <div className="flex items-center gap-3 border-b px-4">
            {parcels.isFetching ? (
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            ) : (
              <Search className="size-4 text-muted-foreground" />
            )}
            <input
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setActive(0)
              }}
              placeholder={t('palette.placeholder')}
              className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <kbd className="rounded border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">Esc</kbd>
          </div>
          <div ref={listRef} className="max-h-[60vh] overflow-y-auto p-2">
            {items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t('palette.empty')}</p>
            ) : (
              items.map((item, index) => {
                const header = item.group !== lastGroup
                lastGroup = item.group
                return (
                  <div key={item.id}>
                    {header && (
                      <p className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                        {t(`palette.group.${item.group}`)}
                      </p>
                    )}
                    <button
                      type="button"
                      data-index={index}
                      onMouseMove={() => setActive(index)}
                      onClick={item.run}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left [&_svg]:size-4 [&_svg]:shrink-0',
                        index === active ? 'bg-primary/10' : 'hover:bg-muted',
                      )}
                    >
                      <span className="text-muted-foreground">{item.icon}</span>
                      <span className="min-w-0 flex-1">
                        <span
                          className={cn(
                            'block truncate text-sm font-medium',
                            item.group !== 'pages' && 'font-mono',
                          )}
                        >
                          {item.title}
                        </span>
                        {item.subtitle && (
                          <span className="block truncate text-xs text-muted-foreground">
                            {item.subtitle}
                          </span>
                        )}
                      </span>
                      {item.badge}
                      {index === active && <CornerDownLeft className="text-muted-foreground" />}
                    </button>
                  </div>
                )
              })
            )}
          </div>
          <div className="flex items-center gap-4 border-t px-4 py-2 text-[11px] text-muted-foreground">
            <span>↑↓ {t('palette.navigate')}</span>
            <span>↵ {t('palette.open')}</span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </>
  )
}
