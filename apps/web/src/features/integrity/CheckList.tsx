import { CheckCircle2, CircleMinus, TriangleAlert, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { InspectionCheck, InspectionVerdict } from '@/api/types'
import { cn } from '@/lib/utils'

const ICONS = {
  pass: <CheckCircle2 className="size-4 text-success" />,
  warn: <TriangleAlert className="size-4 text-warning" />,
  fail: <XCircle className="size-4 text-destructive" />,
  skip: <CircleMinus className="size-4 text-muted-foreground" />,
}

function checkText(t: (key: string, opts?: Record<string, unknown>) => string, check: InspectionCheck): string {
  const variant = check.code === 'SATELLITE' && check.params.reason === 'owner_admits_non_use' ? 'warn_admits' : check.status
  return t(`checks.${check.code}.${variant}`, check.params)
}

export function CheckList({ checks }: { checks: InspectionCheck[] }) {
  const { t } = useTranslation()
  return (
    <ul className="grid gap-2">
      {checks.map((check) => (
        <li key={check.code} className="flex items-start gap-2.5 text-sm">
          <span className="mt-0.5 shrink-0">{ICONS[check.status]}</span>
          <span className={cn(check.status === 'skip' && 'text-muted-foreground')}>
            <span className="block text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              {t(`checks.${check.code}.title`)}
            </span>
            {checkText(t, check)}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function VerdictBadge({ verdict }: { verdict: InspectionVerdict | null | undefined }) {
  const { t } = useTranslation()
  if (!verdict) return null
  const style = {
    PASS: 'bg-success/10 text-success border-success/30',
    SUSPICIOUS: 'bg-accent/15 text-warning border-accent/40',
    FAIL: 'bg-destructive/10 text-destructive border-destructive/30',
  }[verdict]
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold', style)}>
      {verdict === 'PASS' ? ICONS.pass : verdict === 'FAIL' ? ICONS.fail : ICONS.warn}
      {t(`verdict.${verdict}`)}
    </span>
  )
}
