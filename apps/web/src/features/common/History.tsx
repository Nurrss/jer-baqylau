import { Bot, UserRound, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Transition } from '@/api/types'
import { useDateFns } from '@/lib/dates'

type Kind = 'parcel' | 'signal' | 'application'

function actorLabel(actor: string, t: (key: string) => string): { label: string; icon: typeof Bot } {
  if (actor === 'system' || actor.startsWith('service:')) return { label: t('history.system'), icon: Bot }
  if (actor.startsWith('citizen')) return { label: t('history.citizen'), icon: Users }
  return { label: actor.replace(/^inspector:/, ''), icon: UserRound }
}

export function HistoryTimeline({ items, kind }: { items: Transition[]; kind: Kind }) {
  const { t, i18n } = useTranslation()
  const { dateTime } = useDateFns()
  if (!items.length) return <p className="text-sm text-muted-foreground">{t('history.empty')}</p>

  return (
    <ol className="relative grid gap-4 border-l pl-5">
      {items.map((item) => {
        const actor = actorLabel(item.actor, t)
        const Icon = actor.icon
        const meta = item.meta as Record<string, string | undefined>
        let comment = item.comment
        if (meta.auto === 'signal') comment = t('history.autoSignal', { code: meta.signal_code })
        else if (meta.auto === 'signals_rejected')
          comment = t('history.autoRejected', { code: meta.signal_code })
        else if (kind === 'application' && i18n.language === 'kk' && meta.comment_kk)
          comment = meta.comment_kk
        return (
          <li key={item.id} className="relative">
            <span className="absolute top-1 -left-[25px] size-2.5 rounded-full border-2 border-card bg-primary ring-2 ring-primary/20" />
            <p className="text-sm font-medium">
              {item.from_status ? (
                <>
                  {t(`${kind}Status.${item.from_status}`)} → {t(`${kind}Status.${item.to_status}`)}
                </>
              ) : (
                t('history.created', { status: t(`${kind}Status.${item.to_status}`) })
              )}
            </p>
            {comment && <p className="mt-0.5 text-sm whitespace-pre-line text-muted-foreground">{comment}</p>}
            {meta.violation_type && item.to_status === 'VIOLATION' && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {t('parcel.violationType')}: {t(`violationType.${meta.violation_type}`)}
              </p>
            )}
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Icon className="size-3" /> {actor.label} · {dateTime(item.created_at)}
            </p>
          </li>
        )
      })}
    </ol>
  )
}
