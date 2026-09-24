import { useTranslation } from 'react-i18next'
import type { ApplicationStatus, ParcelStatus, SignalStatus } from '@/api/types'
import { cn } from '@/lib/utils'
import { APPLICATION_STATUS_COLORS, PARCEL_STATUS_COLORS, SIGNAL_STATUS_COLORS } from '@/lib/status'

type Props =
  | { kind: 'parcel'; status: ParcelStatus; className?: string }
  | { kind: 'signal'; status: SignalStatus; className?: string }
  | { kind: 'application'; status: ApplicationStatus; className?: string }

export function StatusBadge(props: Props) {
  const { t } = useTranslation()
  const color =
    props.kind === 'parcel'
      ? PARCEL_STATUS_COLORS[props.status]
      : props.kind === 'signal'
        ? SIGNAL_STATUS_COLORS[props.status]
        : APPLICATION_STATUS_COLORS[props.status]
  const label = t(`${props.kind}Status.${props.status}`)
  const dashed = props.kind === 'parcel' && props.status === 'IN_REMEDIATION'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        dashed && 'border-dashed',
        props.className,
      )}
      style={{ color, borderColor: `${color}66`, backgroundColor: `${color}14` }}
    >
      <span className="size-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
