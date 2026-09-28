import {
  ArrowUp,
  CheckCircle2,
  ChevronLeft,
  FileText,
  Layers,
  Loader2,
  MapPinned,
  MessageCircle,
  Send,
  Sprout,
  House,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MapGL, { Layer, Source, type MapLayerMouseEvent, type MapRef } from 'react-map-gl/maplibre'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useCreateLandApplication, useLandFund, useMyLandApplications } from '@/api/queries'
import type { LandApplicationDraft } from '@/api/types'
import { LanguageSwitch } from '@/components/layout/AppShell'
import { Logo } from '@/components/common/Logo'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/misc'
import { Skeleton } from '@/components/ui/skeleton'
import { baseStyle } from '@/features/map/mapStyle'
import { iinIsValid, normalizePhone } from '@/lib/person'
import { ALLOCATION_COLORS } from '@/lib/status'
import { BOT_USERNAME, haptic, useTelegram } from '@/lib/telegram'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { cn, formatArea } from '@/lib/utils'

const MAX_PARCELS = 5
const SELECTED = '#f97316'

type Kind = 'IZHS_ALLOCATION' | 'AGRO_LEASE'

interface LandProps {
  id: string
  cadastral_number: string
  area_ha: number
  purpose: string
  application_type: Kind | null
  address_ru: string
  address_kk: string
  allocation_status: 'OFFERED' | 'RESERVED'
  lon: number
  lat: number
}

type Ring = [number, number][]
type LandGeometry = { type: 'Polygon'; coordinates: Ring[] } | { type: 'MultiPolygon'; coordinates: Ring[][] }

interface LandFeature {
  type: 'Feature'
  id: string
  geometry: LandGeometry
  properties: LandProps
}

function boundsOf(features: LandFeature[]): [[number, number], [number, number]] | null {
  const coords = features.flatMap((f) =>
    f.geometry.type === 'MultiPolygon'
      ? f.geometry.coordinates.flat(2)
      : f.geometry.type === 'Polygon'
        ? f.geometry.coordinates.flat()
        : [],
  )
  if (!coords.length) return null
  const lons = coords.map((c) => c[0]!)
  const lats = coords.map((c) => c[1]!)
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ]
}

// ── Application form ────────────────────────────────────────────────────────

function ApplicationForm({
  parcels,
  initData,
  onBack,
  onDone,
}: {
  parcels: LandProps[]
  initData: string | null
  onBack: () => void
  onDone: (draft: LandApplicationDraft) => void
}) {
  const { t, i18n } = useTranslation()
  const errorMessage = useErrorMessage()
  const create = useCreateLandApplication(initData ?? '', i18n.language)
  const [name, setName] = useState('')
  const [iin, setIin] = useState('')
  const [phone, setPhone] = useState('+7 ')
  const [comment, setComment] = useState('')
  const [consent, setConsent] = useState(false)
  const [touched, setTouched] = useState(false)

  const nameOk = name.trim().split(/\s+/).length >= 2
  const iinOk = iinIsValid(iin)
  const phoneOk = normalizePhone(phone) !== null
  const valid = nameOk && iinOk && phoneOk && consent && Boolean(initData)
  const kind = parcels[0]?.application_type
  const area = parcels.reduce((s, p) => s + p.area_ha, 0)

  return (
    <form
      className="grid gap-4 p-4 pb-28"
      onSubmit={async (e) => {
        e.preventDefault()
        setTouched(true)
        if (!valid) return
        try {
          const draft = await create.mutateAsync({
            parcel_ids: parcels.map((p) => p.id),
            full_name: name.trim(),
            iin,
            phone,
            comment: comment.trim() || null,
          })
          onDone(draft)
        } catch (err) {
          toast.error(errorMessage(err))
        }
      }}
    >
      <button type="button" onClick={onBack} className="flex items-center gap-1 text-sm text-primary">
        <ChevronLeft className="size-4" /> {t('land.backToMap')}
      </button>
      <div>
        <h1 className="text-lg font-semibold">{t('land.formTitle')}</h1>
        <p className="text-sm text-muted-foreground">{kind ? t(`land.kind.${kind}`) : ''}</p>
      </div>
      <ol className="grid gap-2 rounded-xl border bg-card p-3">
        {parcels.map((p, i) => (
          <li key={p.id} className="flex items-start gap-2 text-sm">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#f97316] text-xs font-bold text-white">
              {i + 1}
            </span>
            <span>
              <span className="font-mono font-semibold">{p.cadastral_number}</span> ·{' '}
              {formatArea(p.area_ha, i18n.language)} {t('units.ha')}
              <span className="block text-xs text-muted-foreground">
                {i18n.language === 'kk' ? p.address_kk : p.address_ru}
              </span>
            </span>
          </li>
        ))}
        <li className="border-t pt-2 text-xs text-muted-foreground">
          {t('land.total', { count: parcels.length, area: formatArea(area, i18n.language) })}
          {parcels.length > 1 && ` · ${t(`land.priorityHint.${kind ?? 'IZHS_ALLOCATION'}`)}`}
        </li>
      </ol>

      <div className="grid gap-2">
        <Label htmlFor="land-name">{t('land.fullName')}</Label>
        <Input
          id="land-name"
          autoComplete="name"
          value={name}
          placeholder={t('land.fullNamePlaceholder')}
          onChange={(e) => setName(e.target.value)}
          aria-invalid={touched && !nameOk}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="land-iin">{t('land.iin')}</Label>
        <Input
          id="land-iin"
          inputMode="numeric"
          maxLength={12}
          value={iin}
          onChange={(e) => setIin(e.target.value.replace(/\D/g, ''))}
          aria-invalid={(touched || iin.length === 12) && !iinOk}
        />
        {(touched || iin.length === 12) && !iinOk && (
          <p className="text-xs text-destructive">{t('land.iinInvalid')}</p>
        )}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="land-phone">{t('land.phone')}</Label>
        <Input
          id="land-phone"
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          aria-invalid={touched && !phoneOk}
        />
        {touched && !phoneOk && <p className="text-xs text-destructive">{t('land.phoneInvalid')}</p>}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="land-comment">{t('land.comment')}</Label>
        <Textarea
          id="land-comment"
          maxLength={500}
          value={comment}
          placeholder={t('land.commentPlaceholder')}
          onChange={(e) => setComment(e.target.value)}
        />
      </div>
      <label className="flex items-start gap-3 text-sm">
        <Checkbox checked={consent} onCheckedChange={(v) => setConsent(v === true)} className="mt-0.5" />
        <span>{t('land.consent')}</span>
      </label>
      {touched && !consent && <p className="-mt-2 text-xs text-destructive">{t('land.consentRequired')}</p>}

      <div className="fixed inset-x-0 bottom-0 z-10 border-t bg-card/95 p-4 backdrop-blur">
        <Button type="submit" size="lg" className="w-full" disabled={create.isPending || !initData}>
          {create.isPending ? <Loader2 className="animate-spin" /> : <Send />} {t('land.submit')}
        </Button>
        <p className="mt-2 text-center text-xs text-muted-foreground">{t('land.submitHint')}</p>
      </div>
    </form>
  )
}

// ── My applications ─────────────────────────────────────────────────────────

function MyApplications({ initData }: { initData: string | null }) {
  const { t } = useTranslation()
  const query = useMyLandApplications(initData)
  if (!initData) return <OpenInTelegram />
  if (query.isLoading) return <Skeleton className="m-4 h-32" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  const items = query.data ?? []
  if (!items.length)
    return <p className="p-6 text-center text-sm text-muted-foreground">{t('land.mineEmpty')}</p>
  return (
    <ul className="grid gap-3 p-4">
      {items.map((a) => (
        <li key={a.tracking_number} className="rounded-xl border bg-card p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono font-semibold">{a.tracking_number}</span>
            <span className="text-xs font-medium">{t(`applicationStatus.${a.status}`)}</span>
          </div>
          <p className="text-xs text-muted-foreground">{t(`land.kind.${a.type}`)}</p>
          <ul className="mt-2 grid gap-1 text-sm">
            {a.parcels.map((p) => (
              <li key={p.id} className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{p.priority}.</span>
                <span className="font-mono">{p.cadastral_number}</span>
                {p.granted && <CheckCircle2 className="size-4 text-success" />}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  )
}

function OpenInTelegram() {
  const { t } = useTranslation()
  return (
    <div className="m-4 flex gap-3 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm">
      <MessageCircle className="size-5 shrink-0 text-primary" />
      <span>
        {t('land.openInTelegram')}{' '}
        <a className="font-semibold text-primary underline" href={`https://t.me/${BOT_USERNAME}`}>
          @{BOT_USERNAME}
        </a>
      </span>
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export function LandAppPage() {
  const { t, i18n } = useTranslation()
  const [params] = useSearchParams()
  const { tg, ready } = useTelegram()
  const fund = useLandFund()
  const mapRef = useRef<MapRef>(null)
  const [kind, setKind] = useState<Kind>('IZHS_ALLOCATION')
  const [selected, setSelected] = useState<string[]>([])
  const [step, setStep] = useState<'map' | 'form' | 'done' | 'mine'>('map')
  const [satellite, setSatellite] = useState(true)
  const [draft, setDraft] = useState<LandApplicationDraft | null>(null)

  // Language: ?lang from the bot, else the Telegram user's language.
  useEffect(() => {
    if (!ready) return
    const wanted =
      params.get('lang') ?? (tg?.initDataUnsafe.user?.language_code?.startsWith('kk') ? 'kk' : null)
    if (wanted === 'ru' || wanted === 'kk') void i18n.changeLanguage(wanted)
  }, [ready, tg, params, i18n])

  const features = useMemo(() => (fund.data?.features ?? []) as unknown as LandFeature[], [fund.data])
  const byId = useMemo(() => new Map(features.map((f) => [f.id, f.properties])), [features])
  const visible = useMemo(
    () => features.filter((f) => f.properties.application_type === kind),
    [features, kind],
  )
  const data = useMemo(
    () => ({
      type: 'FeatureCollection' as const,
      features: visible.map((f) => ({
        ...f,
        properties: { ...f.properties, priority: selected.indexOf(f.id) + 1 },
      })),
    }),
    [visible, selected],
  )
  const style = useMemo(() => baseStyle(satellite ? 'satellite' : 'scheme'), [satellite])
  const initialBounds = useMemo(() => boundsOf(visible), [visible])
  const chosen = selected.map((id) => byId.get(id)).filter((p): p is LandProps => Boolean(p))
  const counts = useMemo(() => {
    const offered = (k: Kind) =>
      features.filter(
        (f) => f.properties.application_type === k && f.properties.allocation_status === 'OFFERED',
      ).length
    return { IZHS_ALLOCATION: offered('IZHS_ALLOCATION'), AGRO_LEASE: offered('AGRO_LEASE') }
  }, [features])

  const switchKind = (next: Kind) => {
    if (next === kind) return
    setKind(next)
    setSelected([])
    const bounds = boundsOf(features.filter((f) => f.properties.application_type === next))
    if (bounds) mapRef.current?.fitBounds(bounds, { padding: 48, duration: 800 })
  }

  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const props = e.features?.[0]?.properties as LandProps | undefined
      if (!props) return
      if (props.allocation_status === 'RESERVED') {
        toast.info(t('land.reserved'))
        return
      }
      haptic(tg, 'light')
      setSelected((prev) => {
        if (prev.includes(props.id)) return prev.filter((id) => id !== props.id)
        if (prev.length >= MAX_PARCELS) {
          toast.info(t('land.max', { count: MAX_PARCELS }))
          return prev
        }
        return [...prev, props.id]
      })
    },
    [t, tg],
  )

  const raise = (id: string) =>
    setSelected((prev) => {
      const i = prev.indexOf(id)
      if (i <= 0) return prev
      const next = [...prev]
      ;[next[i - 1], next[i]] = [next[i]!, next[i - 1]!]
      return next
    })

  const header = (
    <header className="flex items-center gap-2 border-b bg-card px-3 py-2">
      <Logo className="size-7" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{t('land.title')}</span>
        <span className="block truncate text-[11px] text-muted-foreground">{t('land.subtitle')}</span>
      </span>
      <LanguageSwitch />
    </header>
  )

  if (step === 'done' && draft) {
    return (
      <div className="flex min-h-full flex-col bg-background">
        {header}
        <div className="grid flex-1 place-content-center justify-items-center gap-4 p-6 text-center">
          <CheckCircle2 className="size-14 text-success" />
          <h1 className="text-xl font-semibold">{t('land.doneTitle', { number: draft.tracking_number })}</h1>
          <p className="max-w-sm text-sm text-muted-foreground">{t('land.doneText')}</p>
          {tg ? (
            <Button size="lg" onClick={() => tg.close()}>
              <MessageCircle /> {t('land.toChat')}
            </Button>
          ) : (
            <OpenInTelegram />
          )}
        </div>
      </div>
    )
  }

  if (step === 'form') {
    return (
      <div className="min-h-full bg-background">
        {header}
        {!tg && ready && <OpenInTelegram />}
        <ApplicationForm
          parcels={chosen}
          initData={tg?.initData ?? null}
          onBack={() => setStep('map')}
          onDone={(d) => {
            haptic(tg, 'success')
            setDraft(d)
            setSelected([])
            setStep('done')
          }}
        />
      </div>
    )
  }

  return (
    <div className="flex h-dvh flex-col bg-background">
      {header}
      <nav className="flex gap-1 border-b bg-card px-3 py-2">
        {(['map', 'mine'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setStep(key)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium',
              step === key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
            )}
          >
            {key === 'map' ? <MapPinned className="size-4" /> : <FileText className="size-4" />}
            {t(`land.tabs.${key}`)}
          </button>
        ))}
      </nav>

      {step === 'mine' ? (
        <div className="flex-1 overflow-y-auto">
          <MyApplications initData={tg?.initData ?? null} />
        </div>
      ) : (
        <>
          <div className="relative min-h-0 flex-1">
            {fund.isLoading || !initialBounds ? (
              fund.isError ? (
                <ErrorState error={fund.error} onRetry={() => void fund.refetch()} />
              ) : (
                <Skeleton className="size-full rounded-none" />
              )
            ) : (
              <MapGL
                ref={mapRef}
                initialViewState={{ bounds: initialBounds, fitBoundsOptions: { padding: 48 } }}
                mapStyle={style}
                interactiveLayerIds={['land-fill']}
                onClick={onClick}
                cursor="pointer"
                attributionControl={{ compact: true }}
                style={{ width: '100%', height: '100%' }}
              >
                <Source id="land" type="geojson" data={data}>
                  <Layer
                    id="land-fill"
                    type="fill"
                    paint={{
                      'fill-color': [
                        'case',
                        ['>', ['get', 'priority'], 0],
                        SELECTED,
                        ['==', ['get', 'allocation_status'], 'RESERVED'],
                        '#94a3b8',
                        ALLOCATION_COLORS.OFFERED,
                      ],
                      'fill-opacity': ['case', ['>', ['get', 'priority'], 0], 0.55, 0.35],
                    }}
                  />
                  <Layer
                    id="land-line"
                    type="line"
                    paint={{
                      'line-color': ['case', ['>', ['get', 'priority'], 0], SELECTED, '#ffffff'],
                      'line-width': ['case', ['>', ['get', 'priority'], 0], 3, 1.5],
                    }}
                  />
                  <Layer
                    id="land-priority"
                    type="symbol"
                    filter={['>', ['get', 'priority'], 0]}
                    layout={{
                      'text-field': ['to-string', ['get', 'priority']],
                      'text-font': ['Noto Sans Bold'],
                      'text-size': 18,
                      'text-allow-overlap': true,
                    }}
                    paint={{ 'text-color': '#ffffff', 'text-halo-color': SELECTED, 'text-halo-width': 2 }}
                  />
                </Source>
              </MapGL>
            )}
            <div className="absolute top-3 left-3 flex gap-2">
              {(['IZHS_ALLOCATION', 'AGRO_LEASE'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => switchKind(k)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow',
                    kind === k ? 'bg-primary text-primary-foreground' : 'bg-card',
                  )}
                >
                  {k === 'IZHS_ALLOCATION' ? <House className="size-3.5" /> : <Sprout className="size-3.5" />}
                  {t(`land.chip.${k}`)} · {counts[k]}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setSatellite((v) => !v)}
              aria-label={t('land.basemap')}
              className="absolute top-3 right-3 grid size-9 place-items-center rounded-full bg-card shadow"
            >
              <Layers className="size-4" />
            </button>
          </div>

          <section className="max-h-[46vh] overflow-y-auto border-t bg-card p-4">
            {!tg && ready && (
              <div className="-mx-4 -mt-4 mb-3">
                <OpenInTelegram />
              </div>
            )}
            {chosen.length === 0 ? (
              <div className="grid gap-2 text-sm">
                <p className="font-medium">{t('land.pickHint')}</p>
                <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="size-3 rounded-sm" style={{ background: ALLOCATION_COLORS.OFFERED }} />
                    {t('land.legendFree')}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="size-3 rounded-sm bg-slate-400" />
                    {t('land.legendReserved')}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="size-3 rounded-sm" style={{ background: SELECTED }} />
                    {t('land.legendSelected')}
                  </span>
                </p>
              </div>
            ) : (
              <div className="grid gap-3">
                <ol className="grid gap-2">
                  {chosen.map((p, i) => (
                    <li key={p.id} className="flex items-center gap-2 rounded-lg border p-2 text-sm">
                      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#f97316] text-xs font-bold text-white">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-mono font-semibold">{p.cadastral_number}</span> ·{' '}
                        {formatArea(p.area_ha, i18n.language)} {t('units.ha')}
                        <span className="block truncate text-xs text-muted-foreground">
                          {i18n.language === 'kk' ? p.address_kk : p.address_ru}
                        </span>
                      </span>
                      {i > 0 && (
                        <button
                          type="button"
                          aria-label={t('land.raise')}
                          onClick={() => raise(p.id)}
                          className="grid size-8 place-items-center rounded-md hover:bg-muted"
                        >
                          <ArrowUp className="size-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        aria-label={t('common.delete')}
                        onClick={() => setSelected((prev) => prev.filter((id) => id !== p.id))}
                        className="grid size-8 place-items-center rounded-md hover:bg-muted"
                      >
                        <X className="size-4" />
                      </button>
                    </li>
                  ))}
                </ol>
                {chosen.length > 1 && (
                  <p className="text-xs text-muted-foreground">{t(`land.priorityHint.${kind}`)}</p>
                )}
                <Button size="lg" onClick={() => setStep('form')}>
                  {t('land.next', { count: chosen.length })}
                </Button>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
