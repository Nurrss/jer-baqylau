import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSignal } from '@/api/queries'
import { ErrorState } from '@/components/common/States'
import { StatusBadge } from '@/components/common/StatusBadge'
import { CopyButton } from '@/components/common/CopyButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { SignalDetailView } from './SignalDetailView'

export function SignalPanel({
  signalId,
  onClose,
  onOpenParcel,
}: {
  signalId: string
  onClose: () => void
  onOpenParcel: (parcelId: string) => void
}) {
  const { t } = useTranslation()
  const query = useSignal(signalId)
  const signal = query.data

  return (
    <aside
      className="absolute top-0 right-0 bottom-0 z-20 flex w-full max-w-[440px] animate-slide-in flex-col border-l bg-card shadow-2xl"
      aria-label={t('signals.card')}
    >
      <header className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{t('signals.card')}</p>
          {signal ? (
            <>
              <div className="flex items-center gap-1">
                <h2 className="font-mono text-lg font-semibold">{signal.tracking_code}</h2>
                <CopyButton value={signal.tracking_code} />
              </div>
              <StatusBadge kind="signal" status={signal.status} className="mt-1" />
            </>
          ) : (
            <Skeleton className="mt-1 h-7 w-40" />
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t('common.close')}>
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {query.isLoading && (
          <div className="grid gap-3 p-5">
            <Skeleton className="h-10" />
            <Skeleton className="h-40" />
            <Skeleton className="h-24" />
          </div>
        )}
        {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {signal && <SignalDetailView signal={signal} onOpenParcel={onOpenParcel} />}
      </div>
    </aside>
  )
}
