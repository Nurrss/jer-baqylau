import { Landmark, Loader2, MessageCircle, Undo2, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useOfferParcel } from '@/api/queries'
import type { ParcelDetail } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Section } from '@/features/common/Section'
import { ALLOCATION_COLORS } from '@/lib/status'
import { useErrorMessage } from '@/lib/useErrorMessage'

const OFFERABLE = new Set(['IZHS', 'LPH', 'AGRICULTURE'])

/** Place of the parcel in the state land fund: offer it to citizens (Mini App) or see who got it. */
export function LandFundSection({ parcel }: { parcel: ParcelDetail }) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const offer = useOfferParcel(parcel.id)
  const allocation = parcel.allocation_status
  const canOffer = allocation === 'NONE' && parcel.owner_type === 'STATE' && OFFERABLE.has(parcel.purpose)
  if (allocation === 'NONE' && !canOffer && !parcel.owner_telegram) return null

  const run = async (offered: boolean) => {
    try {
      await offer.mutateAsync(offered)
      toast.success(t(offered ? 'allocation.offeredToast' : 'allocation.withdrawnToast'))
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <Section title={t('allocation.title')} icon={<Landmark className="size-3.5" />}>
      <div className="grid gap-2 text-sm">
        {allocation !== 'NONE' && (
          <p className="flex items-center gap-2">
            <span
              className="size-3 rounded-sm"
              style={{
                background:
                  allocation === 'ALLOCATED'
                    ? '#16a34a'
                    : ALLOCATION_COLORS[allocation as 'OFFERED' | 'RESERVED'],
              }}
            />
            <span className="font-medium">{t(`allocation.${allocation}`)}</span>
          </p>
        )}
        {allocation !== 'NONE' && (
          <p className="text-xs text-muted-foreground">{t(`allocation.hint.${allocation}`)}</p>
        )}
        {parcel.owner_telegram && (
          <Badge variant="success" className="justify-self-start">
            <MessageCircle className="size-3" /> {t('allocation.ownerTelegram')}
          </Badge>
        )}
        {canOffer && (
          <>
            <p className="text-xs text-muted-foreground">{t('allocation.offerHint')}</p>
            <Button
              size="sm"
              className="justify-self-start"
              disabled={offer.isPending}
              onClick={() => run(true)}
            >
              {offer.isPending ? <Loader2 className="animate-spin" /> : <Users />} {t('allocation.offer')}
            </Button>
          </>
        )}
        {allocation === 'OFFERED' && (
          <Button
            size="sm"
            variant="outline"
            className="justify-self-start"
            disabled={offer.isPending}
            onClick={() => run(false)}
          >
            {offer.isPending ? <Loader2 className="animate-spin" /> : <Undo2 />} {t('allocation.withdraw')}
          </Button>
        )}
      </div>
    </Section>
  )
}
