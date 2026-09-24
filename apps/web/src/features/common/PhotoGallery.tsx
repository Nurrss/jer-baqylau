import { ChevronLeft, ChevronRight, ImagePlus, Loader2, MapPin, UploadCloud } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { Photo } from '@/api/types'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { useDateFns } from '@/lib/dates'
import { cn, formatCoords } from '@/lib/utils'

const ACCEPT = { 'image/jpeg': [], 'image/png': [], 'image/webp': [] }
const MAX_FILES = 10
const MAX_SIZE = 15 * 1024 * 1024

export function PhotoGallery({ photos }: { photos: Photo[] }) {
  const { t } = useTranslation()
  const { dateTime } = useDateFns()
  const [index, setIndex] = useState<number | null>(null)
  const current = index !== null ? photos[index] : undefined

  useEffect(() => {
    if (index === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') setIndex((i) => (i === null ? i : (i + 1) % photos.length))
      if (e.key === 'ArrowLeft') setIndex((i) => (i === null ? i : (i - 1 + photos.length) % photos.length))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, photos.length])

  if (!photos.length) return <p className="text-sm text-muted-foreground">{t('photos.empty')}</p>

  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        {photos.map((photo, i) => (
          <button
            key={photo.id}
            type="button"
            onClick={() => setIndex(i)}
            className="group relative aspect-[4/3] overflow-hidden rounded-lg border bg-muted"
            aria-label={t('photos.open')}
          >
            <img
              src={photo.thumb_url}
              alt=""
              loading="lazy"
              className="size-full object-cover transition-transform group-hover:scale-105"
            />
            <span
              className={cn(
                'absolute bottom-1 left-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-white',
                photo.source === 'CITIZEN' ? 'bg-signal/85' : 'bg-primary/85',
              )}
            >
              {t(`photos.source.${photo.source}`)}
            </span>
          </button>
        ))}
      </div>

      <Dialog open={index !== null} onOpenChange={(open) => !open && setIndex(null)}>
        <DialogContent wide className="gap-3 p-3 sm:p-4">
          <DialogTitle className="sr-only">{t('photos.title')}</DialogTitle>
          {current && (
            <>
              <div className="relative flex items-center justify-center overflow-hidden rounded-lg bg-black">
                <img src={current.url} alt="" className="max-h-[70vh] w-auto object-contain" />
                {photos.length > 1 && (
                  <>
                    <button
                      type="button"
                      className="absolute left-2 rounded-full bg-black/50 p-2 text-white hover:bg-black/70"
                      onClick={() => setIndex((i) => ((i ?? 0) - 1 + photos.length) % photos.length)}
                      aria-label={t('common.previous')}
                    >
                      <ChevronLeft className="size-5" />
                    </button>
                    <button
                      type="button"
                      className="absolute right-2 rounded-full bg-black/50 p-2 text-white hover:bg-black/70"
                      onClick={() => setIndex((i) => ((i ?? 0) + 1) % photos.length)}
                      aria-label={t('common.next')}
                    >
                      <ChevronRight className="size-5" />
                    </button>
                  </>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-muted-foreground">
                <Badge variant={current.source === 'CITIZEN' ? 'secondary' : 'default'}>
                  {t(`photos.source.${current.source}`)}
                </Badge>
                <span>
                  {t('photos.taken')}: {dateTime(current.taken_at ?? current.created_at)}
                </span>
                {current.lat !== null && current.lon !== null && (
                  <span className="flex items-center gap-1">
                    <MapPin className="size-3" /> {formatCoords(current.lat, current.lon)}
                  </span>
                )}
                <span className="ml-auto">
                  {(index ?? 0) + 1} / {photos.length}
                </span>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

export function PhotoUploader({
  upload,
}: {
  upload: (files: File[], onProgress: (fraction: number) => void) => Promise<unknown>
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const [progress, setProgress] = useState<number | null>(null)
  const [previews, setPreviews] = useState<string[]>([])

  const onDrop = useCallback(
    async (accepted: File[], rejected: { file: File }[]) => {
      if (rejected.length) toast.error(t('photos.rejected', { count: rejected.length }))
      if (!accepted.length) return
      const urls = accepted.map((file) => URL.createObjectURL(file))
      setPreviews(urls)
      setProgress(0)
      try {
        await upload(accepted, setProgress)
        toast.success(t('photos.uploaded', { count: accepted.length }))
      } catch (error) {
        toast.error(errorMessage(error))
      } finally {
        urls.forEach((url) => URL.revokeObjectURL(url))
        setPreviews([])
        setProgress(null)
      }
    },
    [errorMessage, t, upload],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (a, r) => void onDrop(a, r),
    accept: ACCEPT,
    maxFiles: MAX_FILES,
    maxSize: MAX_SIZE,
    disabled: progress !== null,
  })

  return (
    <div
      {...getRootProps()}
      className={cn(
        'flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-4 text-center text-sm transition-colors',
        isDragActive
          ? 'border-primary bg-primary/5'
          : 'border-input hover:border-primary/60 hover:bg-muted/50',
        progress !== null && 'cursor-progress',
      )}
    >
      <input {...getInputProps()} />
      {progress === null ? (
        <>
          {isDragActive ? (
            <UploadCloud className="size-5 text-primary" />
          ) : (
            <ImagePlus className="size-5 text-muted-foreground" />
          )}
          <span className="font-medium">{t('photos.drop')}</span>
          <span className="text-xs text-muted-foreground">{t('photos.dropHint')}</span>
        </>
      ) : (
        <div className="w-full">
          <div className="mb-2 flex justify-center gap-1.5">
            {previews.map((src) => (
              <img key={src} src={src} alt="" className="size-10 rounded object-cover" />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Loader2 className="size-4 animate-spin text-primary" />
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
            <span className="w-9 text-right text-xs tabular-nums">{Math.round(progress * 100)}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
