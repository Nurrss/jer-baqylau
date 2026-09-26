import { useMutation } from '@tanstack/react-query'
import { Camera, CheckCircle2, Clock, Loader2, LocateFixed, MapPin, Send, ShieldCheck, Trash2, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { API_URL, toApiError } from '@/api/client'
import { usePublicInspection } from '@/api/queries'
import { DECLARED_USES, type DeclaredUse } from '@/api/types'
import { ErrorState } from '@/components/common/States'
import { PublicLayout } from '@/components/layout/PublicLayout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useDateFns } from '@/lib/dates'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { cn } from '@/lib/utils'

const MAX_PHOTOS = 5
const GOOD_ACCURACY_M = 50

interface Shot {
  blob: Blob
  url: string
  capturedAt: string
}

interface Fix {
  lat: number
  lon: number
  accuracy: number
}

/** Live position with high accuracy; the owner sees how precise the fix is before sending. */
function usePosition() {
  const [fix, setFix] = useState<Fix | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!('geolocation' in navigator)) {
      queueMicrotask(() => setError('UNSUPPORTED'))
      return
    }
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        setError(null)
        setFix({ lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy })
      },
      (err) => setError(err.code === err.PERMISSION_DENIED ? 'DENIED' : 'UNAVAILABLE'),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 30_000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [])
  return { fix, error }
}

/**
 * Camera-only capture: photos come straight from the live stream, never from the gallery,
 * and each gets the capture time. This is what makes "old photo" fraud hard.
 */
function CameraCapture({ disabled, onShot }: { disabled: boolean; onShot: (shot: Shot) => void }) {
  const { t } = useTranslation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [state, setState] = useState<'starting' | 'ready' | 'denied'>('starting')

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } }, audio: false })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((track) => track.stop())
          return
        }
        stream = s
        if (videoRef.current) videoRef.current.srcObject = s
        setState('ready')
      })
      .catch(() => setState('denied'))
    if (!navigator.mediaDevices) queueMicrotask(() => setState('denied'))
    return () => {
      cancelled = true
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  const capture = useCallback(() => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d')?.drawImage(video, 0, 0)
    const capturedAt = new Date().toISOString()
    canvas.toBlob(
      (blob) => {
        if (blob) onShot({ blob, url: URL.createObjectURL(blob), capturedAt })
      },
      'image/jpeg',
      0.9,
    )
  }, [onShot])

  if (state === 'denied') {
    return (
      <div className="flex gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
        <TriangleAlert className="size-4 shrink-0" /> {t('inspect.cameraDenied')}
      </div>
    )
  }
  return (
    <div className="grid gap-2">
      <div className="relative aspect-[4/3] overflow-hidden rounded-lg bg-black">
        <video ref={videoRef} autoPlay playsInline muted className="size-full object-cover" />
        {state === 'starting' && (
          <div className="absolute inset-0 grid place-items-center text-white">
            <Loader2 className="size-6 animate-spin" />
          </div>
        )}
      </div>
      <Button type="button" size="lg" onClick={capture} disabled={disabled || state !== 'ready'}>
        <Camera /> {t('inspect.capture')}
      </Button>
    </div>
  )
}

function Done({ code }: { code: string }) {
  const { t } = useTranslation()
  return (
    <Card className="grid justify-items-center gap-3 p-8 text-center">
      <CheckCircle2 className="size-12 text-success" />
      <h1 className="text-lg font-semibold">{t('inspect.doneTitle')}</h1>
      <p className="text-sm text-muted-foreground">{t('inspect.doneText', { code })}</p>
    </Card>
  )
}

export function InspectPage() {
  const { token = '' } = useParams()
  const { t, i18n } = useTranslation()
  const { dateTime } = useDateFns()
  const errorMessage = useErrorMessage()
  const query = usePublicInspection(token)
  const { fix, error: geoError } = usePosition()
  const [shots, setShots] = useState<Shot[]>([])
  const [declared, setDeclared] = useState<DeclaredUse | null>(null)
  const [comment, setComment] = useState('')

  const submit = useMutation({
    mutationFn: async () => {
      if (!fix || !declared) throw new Error('incomplete')
      const form = new FormData()
      shots.forEach((shot, i) => {
        form.append('files', shot.blob, `photo-${i + 1}.jpg`)
        form.append('captured_at', shot.capturedAt)
      })
      form.append('lat', String(fix.lat))
      form.append('lon', String(fix.lon))
      form.append('accuracy', String(fix.accuracy))
      form.append('declared_use', declared)
      if (comment.trim()) form.append('comment', comment.trim())
      const response = await fetch(`${API_URL}/api/v1/public/inspections/${encodeURIComponent(token)}`, {
        method: 'POST',
        body: form,
      })
      if (!response.ok) throw await toApiError(response)
      return (await response.json()) as { code: string }
    },
  })

  const addShot = useCallback((shot: Shot) => setShots((prev) => [...prev, shot].slice(0, MAX_PHOTOS)), [])

  if (query.isLoading) {
    return (
      <PublicLayout>
        <Skeleton className="h-32" />
        <Skeleton className="h-72" />
      </PublicLayout>
    )
  }
  if (query.isError || !query.data) {
    return (
      <PublicLayout>
        <Card>
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      </PublicLayout>
    )
  }
  const item = query.data
  if (submit.isSuccess) {
    return (
      <PublicLayout>
        <Done code={submit.data.code} />
      </PublicLayout>
    )
  }
  if (item.status !== 'REQUESTED') {
    return (
      <PublicLayout>
        <Card className="grid gap-2 p-6 text-center">
          <p className="font-medium">{t(`inspect.closed.${item.status}`)}</p>
          <p className="font-mono text-sm text-muted-foreground">{item.code}</p>
        </Card>
      </PublicLayout>
    )
  }

  const accuracyOk = fix != null && fix.accuracy <= GOOD_ACCURACY_M
  const ready = shots.length > 0 && fix != null && declared != null && !submit.isPending
  const address = i18n.language === 'kk' ? item.address_kk : item.address_ru

  return (
    <PublicLayout>
      <Card className="grid gap-2 p-4">
        <p className="text-xs text-muted-foreground">{t('inspect.requestFrom')}</p>
        <h1 className="text-lg font-semibold">{t('inspect.title')}</h1>
        <p className="text-sm">
          <span className="font-mono font-semibold">{item.cadastral_number}</span> · {address}
        </p>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Clock className="size-4" /> {t('inspect.dueUntil', { date: dateTime(item.due_at) })}
        </p>
        {item.note && <p className="rounded-lg bg-muted/60 p-3 text-sm">«{item.note}»</p>}
      </Card>

      <Card className="grid gap-3 p-4">
        <h2 className="font-semibold">{t('inspect.step1')}</h2>
        <div
          className={cn(
            'flex items-center gap-2 rounded-lg p-3 text-sm',
            geoError ? 'bg-destructive/10 text-destructive' : accuracyOk ? 'bg-success/10 text-success' : 'bg-muted',
          )}
        >
          {geoError ? (
            <TriangleAlert className="size-4 shrink-0" />
          ) : fix ? (
            <LocateFixed className="size-4 shrink-0" />
          ) : (
            <Loader2 className="size-4 shrink-0 animate-spin" />
          )}
          <span>
            {geoError
              ? t(`inspect.geo.${geoError}`)
              : fix
                ? t(accuracyOk ? 'inspect.geo.good' : 'inspect.geo.weak', { accuracy: Math.round(fix.accuracy) })
                : t('inspect.geo.waiting')}
          </span>
        </div>
        <p className="flex gap-2 text-xs text-muted-foreground">
          <MapPin className="size-4 shrink-0" /> {t('inspect.stayOnParcel')}
        </p>
      </Card>

      <Card className="grid gap-3 p-4">
        <h2 className="font-semibold">
          {t('inspect.step2')}{' '}
          <span className="text-sm font-normal text-muted-foreground">
            {shots.length}/{MAX_PHOTOS}
          </span>
        </h2>
        <CameraCapture disabled={shots.length >= MAX_PHOTOS} onShot={addShot} />
        {shots.length > 0 && (
          <div className="grid grid-cols-5 gap-2">
            {shots.map((shot, i) => (
              <div key={shot.url} className="relative">
                <img src={shot.url} alt="" className="aspect-square w-full rounded-md object-cover" />
                <button
                  type="button"
                  aria-label={t('common.delete')}
                  onClick={() => {
                    URL.revokeObjectURL(shot.url)
                    setShots((prev) => prev.filter((_, j) => j !== i))
                  }}
                  className="absolute -top-1.5 -right-1.5 grid size-6 place-items-center rounded-full bg-card shadow"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="grid gap-3 p-4">
        <h2 className="font-semibold">{t('inspect.step3')}</h2>
        <div className="grid gap-2" role="radiogroup" aria-label={t('inspect.step3')}>
          {DECLARED_USES.map((use) => (
            <button
              key={use}
              type="button"
              role="radio"
              aria-checked={declared === use}
              onClick={() => setDeclared(use)}
              className={cn(
                'rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                declared === use ? 'border-primary bg-primary/10 font-medium ring-2 ring-primary/40' : 'hover:bg-muted',
              )}
            >
              <span className="flex items-center gap-2">
                <span className="flex-1">{t(`declaredUse.${use}`)}</span>
                {declared === use && <CheckCircle2 className="size-4 shrink-0 text-primary" />}
              </span>
            </button>
          ))}
        </div>
        <div className="grid gap-2">
          <Label htmlFor="owner-comment">{t('inspect.comment')}</Label>
          <Textarea id="owner-comment" value={comment} maxLength={1000} onChange={(e) => setComment(e.target.value)} />
        </div>
      </Card>

      {submit.isError && (
        <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(submit.error)}</p>
      )}
      <Button size="lg" disabled={!ready} onClick={() => submit.mutate()}>
        {submit.isPending ? <Loader2 className="animate-spin" /> : <Send />} {t('inspect.send')}
      </Button>
      <p className="flex gap-2 pb-6 text-xs text-muted-foreground">
        <ShieldCheck className="size-4 shrink-0" /> {t('inspect.privacy')}
      </p>
    </PublicLayout>
  )
}
