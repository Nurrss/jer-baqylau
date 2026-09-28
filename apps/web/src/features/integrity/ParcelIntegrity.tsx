import { Check, CircleAlert, ClipboardCheck, Info, Landmark, Send } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useCrosscheck, useInspections } from '@/api/queries'
import type { ParcelDetail } from '@/api/types'
import { ErrorState } from '@/components/common/States'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { VerdictBadge } from '@/features/integrity/CheckList'
import { RequestInspectionDialog } from '@/features/integrity/RequestInspectionDialog'
import { Section } from '@/features/common/Section'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'

/** Parcel vs other state registers: cadastre (ГБД ЗКС) and declared sowing (subsidies) vs satellite. */
export function CrossCheckSection({ parcelId }: { parcelId: string }) {
  const { t } = useTranslation()
  const query = useCrosscheck(parcelId, true)
  const data = query.data
  return (
    <Section
      title={t('crosscheck.title')}
      icon={<Landmark className="size-3.5" />}
      aside={
        data?.items.some((i) => i.is_demo) ? <Badge variant="warning">{t('map.demoBadge')}</Badge> : undefined
      }
    >
      {query.isLoading ? (
        <Skeleton className="h-16" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} className="py-4" />
      ) : !data?.items.length ? (
        <p className="text-sm text-muted-foreground">{t('crosscheck.empty')}</p>
      ) : (
        <ul className="grid gap-2">
          {data.items.map((item) => (
            <li
              key={item.code}
              className={cn(
                'flex gap-2.5 rounded-lg border p-2.5 text-sm',
                item.status === 'mismatch' && 'border-destructive/40 bg-destructive/5',
              )}
            >
              {item.status === 'ok' ? (
                <Check className="mt-0.5 size-4 shrink-0 text-success" />
              ) : item.status === 'mismatch' ? (
                <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
              ) : (
                <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              )}
              <span className="grid gap-0.5">
                <span className="text-[11px] font-medium text-muted-foreground uppercase">
                  {t(`crosscheck.source.${item.source}`)}
                </span>
                <span>
                  {t(`crosscheck.code.${item.code}`, {
                    ...item.params,
                    crop: item.params.crop ? t(`crops.${String(item.params.crop)}`) : '',
                    basis: item.params.basis ? t(`crosscheck.basis.${String(item.params.basis)}`) : '',
                  })}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

/** Remote photo reports for this parcel + "request a report" action. */
export function ParcelInspections({ parcel }: { parcel: ParcelDetail }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { relative } = useDateFns()
  const query = useInspections([], parcel.id)
  const [open, setOpen] = useState(false)
  const items = query.data?.items ?? []
  const hasOpen = items.some((i) => i.status === 'REQUESTED' || i.status === 'SUBMITTED')
  const inFund = parcel.allocation_status === 'OFFERED' || parcel.allocation_status === 'RESERVED'
  const canRequest = parcel.status !== 'RETURNED_TO_STATE' && !inFund && !hasOpen
  return (
    <Section title={t('inspections.parcelTitle')} icon={<ClipboardCheck className="size-3.5" />}>
      <div className="grid gap-2">
        {query.isLoading ? (
          <Skeleton className="h-12" />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('inspections.parcelEmpty')}</p>
        ) : (
          <ul className="grid gap-1.5">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/inspections?id=${item.id}`)}
                  className="flex w-full items-center gap-2 rounded-lg border p-2 text-left text-sm hover:bg-muted"
                >
                  <span className="flex-1">
                    <span className="block font-mono text-xs font-semibold">{item.code}</span>
                    <span className="block text-xs text-muted-foreground">
                      {t(`inspectionStatus.${item.status}`)} ·{' '}
                      {relative(item.submitted_at ?? item.created_at)}
                    </span>
                  </span>
                  <VerdictBadge verdict={item.verdict} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {canRequest ? (
          <Button size="sm" variant="outline" className="justify-self-start" onClick={() => setOpen(true)}>
            <Send /> {t('inspections.request')}
          </Button>
        ) : (
          hasOpen && <p className="text-xs text-muted-foreground">{t('inspections.alreadyOpen')}</p>
        )}
        <p className="text-xs text-muted-foreground">{t('inspections.requestHint')}</p>
      </div>
      {open && (
        <RequestInspectionDialog
          parcelId={parcel.id}
          cadastral={parcel.cadastral_number}
          ownerTelegram={parcel.owner_telegram}
          onClose={() => setOpen(false)}
        />
      )}
    </Section>
  )
}
