import * as Popover from '@radix-ui/react-popover'
import {
  Bell,
  BellOff,
  ChevronDown,
  Filter,
  Layers,
  Loader2,
  Megaphone,
  Satellite,
  Search,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNdvi, useParcelSearch } from '@/api/queries'
import {
  PARCEL_STATUSES,
  PURPOSES,
  VIOLATION_TYPES,
  type ParcelFeatureCollection,
  type ParcelSearchResult,
} from '@/api/types'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Checkbox, Switch } from '@/components/ui/misc'
import { useDateFns } from '@/lib/dates'
import { NDVI_STOPS, PARCEL_STATUS_COLORS } from '@/lib/status'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/store/ui'

// ── Search ──────────────────────────────────────────────────────────────────

export function MapSearch({ onPick }: { onPick: (result: ParcelSearchResult) => void }) {
  const { t, i18n } = useTranslation()
  const [value, setValue] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), 220)
    return () => window.clearTimeout(timer)
  }, [value])

  const { data, isFetching } = useParcelSearch(debounced)
  const results = debounced.trim().length >= 2 ? (data ?? []) : []

  const pick = (result: ParcelSearchResult) => {
    onPick(result)
    setValue(result.cadastral_number)
    setOpen(false)
    inputRef.current?.blur()
  }

  return (
    <div className="relative w-full max-w-md">
      <div className="flex h-11 items-center gap-2 rounded-xl border bg-card px-3 shadow-lg">
        {isFetching ? (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        ) : (
          <Search className="size-4 text-muted-foreground" />
        )}
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setOpen(true)
            setActive(0)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') setActive((i) => Math.min(i + 1, results.length - 1))
            if (e.key === 'ArrowUp') setActive((i) => Math.max(i - 1, 0))
            if (e.key === 'Enter' && results[active]) pick(results[active])
            if (e.key === 'Escape') setOpen(false)
          }}
          placeholder={t('map.searchPlaceholder')}
          className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          aria-label={t('map.searchPlaceholder')}
          role="combobox"
          aria-expanded={open && results.length > 0}
        />
        {value && (
          <button
            type="button"
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            onClick={() => {
              setValue('')
              setDebounced('')
              inputRef.current?.focus()
            }}
            aria-label={t('common.clear')}
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
      {open && debounced.trim().length >= 2 && (
        <div className="absolute top-12 right-0 left-0 z-30 overflow-hidden rounded-xl border bg-card shadow-xl">
          {results.length === 0 && !isFetching ? (
            <p className="px-4 py-3 text-sm text-muted-foreground">{t('map.searchEmpty')}</p>
          ) : (
            <ul role="listbox">
              {results.map((result, index) => (
                <li key={result.id} role="option" aria-selected={index === active}>
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => pick(result)}
                    onMouseEnter={() => setActive(index)}
                    className={cn(
                      'flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left',
                      index === active && 'bg-muted',
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block font-mono text-sm font-medium">{result.cadastral_number}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {i18n.language === 'kk' ? result.address_kk : result.address_ru}
                      </span>
                    </span>
                    <StatusBadge kind="parcel" status={result.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ── Layers / basemap ────────────────────────────────────────────────────────

export function LayerControls() {
  const { t } = useTranslation()
  const {
    basemap,
    setBasemap,
    ndviLayer,
    toggleNdvi,
    signalsLayer,
    toggleSignals,
    soundEnabled,
    toggleSound,
  } = useUiStore()
  const { dateTime } = useDateFns()
  const ndvi = useNdvi(ndviLayer)

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex rounded-xl border bg-card p-1 shadow-lg">
        {(['osm', 'satellite'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setBasemap(mode)}
            aria-pressed={basemap === mode}
            className={cn(
              'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
              basemap === mode
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted',
            )}
          >
            {t(`map.basemap.${mode}`)}
          </button>
        ))}
      </div>

      <Popover.Root>
        <Popover.Trigger className="flex items-center gap-2 rounded-xl border bg-card px-3 py-2 text-xs font-medium shadow-lg hover:bg-muted">
          <Layers className="size-4" /> {t('map.layers')}
          {ndviLayer && <span className="size-1.5 rounded-full bg-success" />}
          <ChevronDown className="size-3.5 opacity-60" />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            align="end"
            sideOffset={6}
            className="z-40 w-72 rounded-xl border bg-card p-3 text-card-foreground shadow-xl"
          >
            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg p-2 hover:bg-muted">
              <span className="flex items-center gap-2 text-sm">
                <Megaphone className="size-4 text-signal" /> {t('map.layerSignals')}
              </span>
              <Switch checked={signalsLayer} onCheckedChange={toggleSignals} />
            </label>
            <label className="flex cursor-pointer items-start justify-between gap-3 rounded-lg p-2 hover:bg-muted">
              <span className="text-sm">
                <span className="flex items-center gap-2">
                  <Satellite className="size-4 text-success" /> {t('map.layerNdvi')}
                </span>
                <Badge variant="warning" className="mt-1.5">
                  {t('map.demoBadge')}
                </Badge>
              </span>
              <Switch checked={ndviLayer} onCheckedChange={toggleNdvi} />
            </label>
            {ndviLayer && ndvi.data && (
              <p className="px-2 pt-1 text-[11px] text-muted-foreground">
                {t('map.ndviProvider', { provider: ndvi.data.provider })} ·{' '}
                {t('map.ndviScanned', { date: dateTime(ndvi.data.scanned_at) })}
              </p>
            )}
            <div className="my-2 h-px bg-border" />
            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg p-2 hover:bg-muted">
              <span className="flex items-center gap-2 text-sm">
                {soundEnabled ? <Bell className="size-4" /> : <BellOff className="size-4" />}
                {t('map.sound')}
              </span>
              <Switch checked={soundEnabled} onCheckedChange={toggleSound} />
            </label>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  )
}

// ── Legend with counters and filters ────────────────────────────────────────

export function Legend({ parcels }: { parcels: ParcelFeatureCollection | undefined }) {
  const { t } = useTranslation()
  const { filters, setFilters, resetFilters, ndviLayer } = useUiStore()
  const [expanded, setExpanded] = useState(true)
  const [showFilters, setShowFilters] = useState(false)

  const counts = useMemo(() => {
    const byStatus: Record<string, number> = {}
    let overdue = 0
    for (const f of parcels?.features ?? []) {
      byStatus[f.properties.status] = (byStatus[f.properties.status] ?? 0) + 1
      if (f.properties.is_overdue) overdue += 1
    }
    return { byStatus, overdue, total: parcels?.features.length ?? 0 }
  }, [parcels])

  const activeFilters =
    filters.statuses.length +
    filters.violationTypes.length +
    filters.purposes.length +
    (filters.overdueOnly ? 1 : 0)

  const toggle = <T extends string>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value]

  return (
    <div className="w-72 overflow-hidden rounded-xl border bg-card/95 shadow-lg backdrop-blur">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-semibold"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span>
          {ndviLayer ? t('map.legendNdvi') : t('map.legend')}{' '}
          <span className="font-normal text-muted-foreground">· {counts.total}</span>
        </span>
        <ChevronDown className={cn('size-4 transition-transform', !expanded && '-rotate-90')} />
      </button>
      {expanded && (
        <div className="border-t px-2 pt-1.5 pb-2">
          {ndviLayer ? (
            <div className="px-1 py-1">
              <div
                className="h-2.5 rounded-full"
                style={{
                  background: `linear-gradient(90deg, ${NDVI_STOPS.map(([v, c]) => `${c} ${(v / 0.8) * 100}%`).join(', ')})`,
                }}
              />
              <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
                <span>{t('map.ndviLow')}</span>
                <span>{t('map.ndviHigh')}</span>
              </div>
              <p className="mt-2 flex items-center gap-2 text-xs">
                <span className="inline-block h-0 w-6 border-t-[3px] border-dotted border-orange-500" />
                {t('map.ndviFlagged')}
              </p>
            </div>
          ) : (
            <ul className="grid gap-0.5">
              {PARCEL_STATUSES.map((status) => {
                const selected = filters.statuses.includes(status)
                return (
                  <li key={status}>
                    <button
                      type="button"
                      onClick={() => setFilters({ statuses: toggle(filters.statuses, status) })}
                      aria-pressed={selected}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted',
                        selected && 'bg-primary/10',
                        filters.statuses.length > 0 && !selected && 'opacity-50',
                      )}
                    >
                      <span
                        className={cn(
                          'size-3.5 shrink-0 rounded-[4px] border-2',
                          status === 'IN_REMEDIATION' && 'border-dashed',
                        )}
                        style={{
                          borderColor: PARCEL_STATUS_COLORS[status],
                          backgroundColor: `${PARCEL_STATUS_COLORS[status]}${status === 'IN_REMEDIATION' ? '33' : '66'}`,
                        }}
                      />
                      <span className="flex-1">{t(`parcelStatus.${status}`)}</span>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {counts.byStatus[status] ?? 0}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="mt-1.5 flex items-center justify-between gap-2 border-t px-1 pt-2">
            <button
              type="button"
              onClick={() => setShowFilters((v) => !v)}
              className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
              aria-expanded={showFilters}
            >
              <Filter className="size-3.5" /> {t('map.filters')}
              {activeFilters > 0 && <Badge className="px-1.5 py-0">{activeFilters}</Badge>}
            </button>
            {activeFilters > 0 && (
              <button
                type="button"
                onClick={resetFilters}
                className="text-xs text-muted-foreground hover:underline"
              >
                {t('map.resetFilters')}
              </button>
            )}
          </div>

          {showFilters && (
            <div className="mt-2 grid gap-3 px-1 text-sm">
              <label className="flex items-center justify-between gap-2">
                <span>
                  {t('map.overdueOnly')}{' '}
                  <span className="text-xs text-muted-foreground tabular-nums">({counts.overdue})</span>
                </span>
                <Switch
                  checked={filters.overdueOnly}
                  onCheckedChange={(v) => setFilters({ overdueOnly: v })}
                />
              </label>
              <fieldset>
                <legend className="mb-1.5 text-xs font-semibold text-muted-foreground uppercase">
                  {t('parcel.violationType')}
                </legend>
                <div className="grid gap-1.5">
                  {VIOLATION_TYPES.map((vt) => (
                    <label key={vt} className="flex items-center gap-2">
                      <Checkbox
                        checked={filters.violationTypes.includes(vt)}
                        onCheckedChange={() =>
                          setFilters({ violationTypes: toggle(filters.violationTypes, vt) })
                        }
                      />
                      {t(`violationType.${vt}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend className="mb-1.5 text-xs font-semibold text-muted-foreground uppercase">
                  {t('parcel.purpose')}
                </legend>
                <div className="grid gap-1.5">
                  {PURPOSES.map((p) => (
                    <label key={p} className="flex items-center gap-2">
                      <Checkbox
                        checked={filters.purposes.includes(p)}
                        onCheckedChange={() => setFilters({ purposes: toggle(filters.purposes, p) })}
                      />
                      {t(`purpose.${p}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
