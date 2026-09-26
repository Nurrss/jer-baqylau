import { Check, Circle, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ResolutionEvidence } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'

/** What proves the violation is gone. "Resolved" needs at least one item (server enforces it too). */
export function EvidenceList({ evidence, loading }: { evidence: ResolutionEvidence | undefined; loading: boolean }) {
  const { t } = useTranslation()
  const { dateTime } = useDateFns()
  if (loading || !evidence) return <Skeleton className="h-24" />
  return (
    <div
      className={cn(
        'grid gap-2 rounded-lg border p-3',
        evidence.sufficient ? 'border-success/40 bg-success/5' : 'border-warning/50 bg-warning/5',
      )}
    >
      <p className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className={cn('size-4', evidence.sufficient ? 'text-success' : 'text-warning')} />
        {t(evidence.sufficient ? 'evidence.sufficient' : 'evidence.required')}
      </p>
      <ul className="grid gap-1.5">
        {evidence.items.map((item) => (
          <li key={item.kind} className="flex gap-2 text-sm">
            {item.ok ? (
              <Check className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            )}
            <span className={cn(!item.ok && 'text-muted-foreground')}>
              {t(`evidence.kind.${item.kind}`)}
              {item.ok && (item.detail || item.at) && (
                <span className="block text-xs text-muted-foreground">
                  {[item.detail, item.at && dateTime(item.at)].filter(Boolean).join(' · ')}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {evidence.since && (
        <p className="text-xs text-muted-foreground">{t('evidence.since', { date: dateTime(evidence.since) })}</p>
      )}
    </div>
  )
}
