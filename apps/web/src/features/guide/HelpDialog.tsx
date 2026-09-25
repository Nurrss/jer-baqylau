import { ArrowRight, GraduationCap, Keyboard, Map as MapIcon, Megaphone, PlayCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { PARCEL_STATUSES, SIGNAL_STATUSES } from '@/api/types'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PARCEL_STATUS_COLORS } from '@/lib/status'
import { cn } from '@/lib/utils'
import { useGuideStore } from '@/store/guide'

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[11px] font-semibold text-foreground">
      {children}
    </kbd>
  )
}

/** Violation lifecycle as a small flow diagram (the same rules as the backend state machine). */
function LifecycleDiagram() {
  const { t } = useTranslation()
  const node = (status: (typeof PARCEL_STATUSES)[number]) => (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium whitespace-nowrap',
        status === 'IN_REMEDIATION' && 'border-dashed',
      )}
      style={{
        borderColor: PARCEL_STATUS_COLORS[status],
        backgroundColor: `${PARCEL_STATUS_COLORS[status]}14`,
      }}
    >
      <span className="size-2 rounded-full" style={{ backgroundColor: PARCEL_STATUS_COLORS[status] }} />
      {t(`parcelStatus.${status}`)}
    </span>
  )
  const arrow = <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
  return (
    <div className="grid gap-2 rounded-xl border bg-muted/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        {node('OK')}
        {arrow}
        {node('UNDER_CHECK')}
        {arrow}
        {node('VIOLATION')}
        {arrow}
        {node('IN_REMEDIATION')}
        {arrow}
        <span className="flex flex-col gap-1.5">
          {node('RESOLVED')}
          {node('RETURNED_TO_STATE')}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{t('help.lifecycleNote')}</p>
    </div>
  )
}

export function HelpDialog() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = useGuideStore((s) => s.helpOpen)
  const setOpen = useGuideStore((s) => s.setHelpOpen)
  const start = useGuideStore((s) => s.start)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent wide className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{t('help.title')}</DialogTitle>
          <DialogDescription>{t('help.subtitle')}</DialogDescription>
        </DialogHeader>

        <section className="grid gap-2 sm:grid-cols-3">
          <button
            type="button"
            onClick={() => {
              navigate('/')
              start('main')
            }}
            className="flex items-start gap-3 rounded-xl border p-3 text-left hover:border-primary hover:bg-primary/5"
          >
            <GraduationCap className="mt-0.5 size-5 text-primary" />
            <span>
              <span className="block text-sm font-semibold">{t('help.tourMain')}</span>
              <span className="block text-xs text-muted-foreground">{t('help.tourMainHint')}</span>
            </span>
          </button>
          <button
            type="button"
            onClick={() => {
              navigate('/map')
              start('map')
            }}
            className="flex items-start gap-3 rounded-xl border p-3 text-left hover:border-primary hover:bg-primary/5"
          >
            <MapIcon className="mt-0.5 size-5 text-primary" />
            <span>
              <span className="block text-sm font-semibold">{t('help.tourMap')}</span>
              <span className="block text-xs text-muted-foreground">{t('help.tourMapHint')}</span>
            </span>
          </button>
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              navigate('/signals')
            }}
            className="flex items-start gap-3 rounded-xl border p-3 text-left hover:border-primary hover:bg-primary/5"
          >
            <PlayCircle className="mt-0.5 size-5 text-primary" />
            <span>
              <span className="block text-sm font-semibold">{t('help.startWork')}</span>
              <span className="block text-xs text-muted-foreground">{t('help.startWorkHint')}</span>
            </span>
          </button>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">{t('help.lifecycleTitle')}</h3>
          <LifecycleDiagram />
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold">{t('help.parcelStatuses')}</h3>
            <ul className="grid gap-2">
              {PARCEL_STATUSES.map((status) => (
                <li key={status} className="grid gap-0.5">
                  <StatusBadge kind="parcel" status={status} className="w-fit" />
                  <span className="text-xs text-muted-foreground">{t(`help.parcel.${status}`)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid content-start gap-4">
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Megaphone className="size-4" /> {t('help.signalStatuses')}
              </h3>
              <ul className="grid gap-2">
                {SIGNAL_STATUSES.map((status) => (
                  <li key={status} className="grid gap-0.5">
                    <StatusBadge kind="signal" status={status} className="w-fit" />
                    <span className="text-xs text-muted-foreground">{t(`help.signal.${status}`)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Keyboard className="size-4" /> {t('help.shortcuts')}
              </h3>
              <ul className="grid gap-1.5 text-sm">
                <li className="flex items-center justify-between gap-2">
                  {t('help.shortcutSearch')}
                  <span className="flex gap-1">
                    <Kbd>Ctrl</Kbd>
                    <Kbd>K</Kbd>
                  </span>
                </li>
                <li className="flex items-center justify-between gap-2">
                  {t('help.shortcutHelp')}
                  <Kbd>?</Kbd>
                </li>
                <li className="flex items-center justify-between gap-2">
                  {t('help.shortcutClose')}
                  <Kbd>Esc</Kbd>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <div className="flex justify-end">
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t('common.close')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
