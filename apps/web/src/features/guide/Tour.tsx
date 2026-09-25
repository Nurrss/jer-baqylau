import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useGuideStore } from '@/store/guide'
import { TOURS, type TourStep } from './tours'

const CARD_WIDTH = 340
const GAP = 14
const PAD = 6

function findTarget(target?: string): HTMLElement | null {
  if (!target) return null
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`)
  if (!el) return null
  const rect = el.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0 ? el : null
}

function cardPosition(rect: DOMRect | null, placement: TourStep['placement'], height: number) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (!rect) return { left: (vw - CARD_WIDTH) / 2, top: Math.max(24, (vh - height) / 2) }
  let left = rect.left
  let top = rect.bottom + GAP
  switch (placement) {
    case 'right':
      left = rect.right + GAP
      top = rect.top
      break
    case 'left':
      left = rect.left - CARD_WIDTH - GAP
      top = rect.top
      break
    case 'top':
      top = rect.top - height - GAP
      break
    default:
      left = rect.left + rect.width / 2 - CARD_WIDTH / 2
  }
  return {
    left: Math.min(Math.max(12, left), vw - CARD_WIDTH - 12),
    top: Math.min(Math.max(12, top), vh - height - 12),
  }
}

export function Tour() {
  const active = useGuideStore((s) => s.active)
  // Keyed by tour id: every tour starts from its first step with fresh state.
  return active ? <TourRunner key={active} steps={TOURS[active]} /> : null
}

function TourRunner({ steps }: { steps: TourStep[] }) {
  const { t } = useTranslation()
  const finish = useGuideStore((s) => s.finish)
  const [index, setIndex] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [cardHeight, setCardHeight] = useState(180)
  const step = steps[index]

  // Follow the highlighted element (it may scroll, resize or animate in).
  useLayoutEffect(() => {
    if (!step) return
    findTarget(step.target)?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    let frame = 0
    let last = ''
    const loop = () => {
      const el = findTarget(step.target)
      const next = el ? el.getBoundingClientRect() : null
      const signature = next ? `${next.left}|${next.top}|${next.width}|${next.height}` : 'none'
      if (signature !== last) {
        last = signature
        setRect(next)
      }
      frame = requestAnimationFrame(loop)
    }
    frame = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(frame)
  }, [step])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') finish()
      if (e.key === 'ArrowRight') setIndex((i) => Math.min(i + 1, steps.length - 1))
      if (e.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [finish, steps.length])

  if (!step) return null
  const last = index === steps.length - 1
  const position = cardPosition(rect, step.placement, cardHeight)

  return createPortal(
    <div
      className="fixed inset-0 z-[100]"
      role="dialog"
      aria-modal="true"
      aria-label={t(`tour.${step.key}.title`)}
    >
      {rect ? (
        <div
          className="pointer-events-none absolute rounded-xl ring-2 ring-accent transition-all duration-300"
          style={{
            left: rect.left - PAD,
            top: rect.top - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: '0 0 0 9999px rgb(8 17 28 / 0.62)',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-[rgb(8_17_28/0.62)]" />
      )}
      <div
        ref={(el) => {
          if (el && Math.abs(el.offsetHeight - cardHeight) > 2) setCardHeight(el.offsetHeight)
        }}
        className="absolute animate-slide-in rounded-xl border bg-card p-5 text-card-foreground shadow-2xl"
        style={{ width: CARD_WIDTH, left: position.left, top: position.top }}
      >
        <div className="mb-2 flex items-start justify-between gap-3">
          <p className="text-xs font-semibold tracking-wide text-primary uppercase">
            {t('tour.stepOf', { n: index + 1, total: steps.length })}
          </p>
          <button
            type="button"
            onClick={finish}
            className="rounded p-0.5 text-muted-foreground hover:bg-muted"
            aria-label={t('tour.skip')}
          >
            <X className="size-4" />
          </button>
        </div>
        <h3 className="text-base font-semibold">{t(`tour.${step.key}.title`)}</h3>
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{t(`tour.${step.key}.body`)}</p>
        <div className="mt-4 flex items-center gap-1.5">
          {steps.map((s, i) => (
            <span
              key={s.key}
              className={cn(
                'h-1.5 rounded-full transition-all',
                i === index ? 'w-5 bg-primary' : 'w-1.5 bg-border',
              )}
            />
          ))}
          <div className="ml-auto flex gap-2">
            {index > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setIndex(index - 1)}>
                <ArrowLeft />
              </Button>
            )}
            <Button size="sm" onClick={() => (last ? finish() : setIndex(index + 1))}>
              {last ? t('tour.finish') : t('tour.next')}
              {!last && <ArrowRight />}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
