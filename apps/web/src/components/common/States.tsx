import { AlertTriangle, Inbox, RotateCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function EmptyState({
  title,
  description,
  icon,
  className,
  action,
}: {
  title: string
  description?: string
  icon?: ReactNode
  className?: string
  action?: ReactNode
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-6 py-12 text-center', className)}>
      <div className="mb-1 rounded-full bg-muted p-3 text-muted-foreground">
        {icon ?? <Inbox className="size-6" />}
      </div>
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown
  onRetry?: () => void
  className?: string
}) {
  const { t } = useTranslation()
  const message = useErrorMessage()(error)
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 px-6 py-10 text-center', className)}>
      <div className="rounded-full bg-destructive/10 p-3 text-destructive">
        <AlertTriangle className="size-6" />
      </div>
      <div>
        <p className="font-medium">{t('errors.title')}</p>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw /> {t('common.retry')}
        </Button>
      )}
    </div>
  )
}
