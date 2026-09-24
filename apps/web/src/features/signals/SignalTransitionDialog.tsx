import { Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useSignalTransition } from '@/api/queries'
import { VIOLATION_TYPES, type SignalDetail, type SignalStatus, type ViolationType } from '@/api/types'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { fromDateInput, toDateInput } from '@/lib/dates'

const CATEGORY_TO_VIOLATION: Record<SignalDetail['category'], ViolationType> = {
  DUMP: 'DUMP',
  ABANDONED: 'UNUSED',
  SELF_SEIZURE: 'SELF_SEIZURE',
  OTHER: 'MISUSE',
}

export function SignalTransitionDialog({
  signal,
  target,
  onClose,
}: {
  signal: SignalDetail
  target: SignalStatus
  onClose: () => void
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const mutation = useSignalTransition(signal.id)
  const [comment, setComment] = useState(target === 'IN_REVIEW' ? t('signals.defaultInReviewComment') : '')
  const [violationType, setViolationType] = useState<ViolationType>(CATEGORY_TO_VIOLATION[signal.category])
  const [deadline, setDeadline] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 30)
    return toDateInput(d.toISOString())
  })
  const [error, setError] = useState<string | null>(null)
  const confirmsParcel = target === 'CONFIRMED' && Boolean(signal.parcel_id)
  const valid = comment.trim().length >= 3

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    setError(null)
    try {
      await mutation.mutateAsync({
        to: target,
        comment: comment.trim(),
        violation_type: confirmsParcel ? violationType : null,
        deadline_at: confirmsParcel && deadline ? fromDateInput(deadline) : null,
      })
      toast.success(
        signal.has_reporter
          ? t('signals.doneNotified', { status: t(`signalStatus.${target}`) })
          : t('transition.done', { status: t(`signalStatus.${target}`) }),
      )
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{t(`transition.action.SIGNAL.${target}`)}</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{signal.tracking_code}</span>
              {signal.reports_count > 1 &&
                ` · ${t('signals.cascadeHint', { count: signal.reports_count - 1 })}`}
            </DialogDescription>
          </DialogHeader>

          {confirmsParcel && (
            <div className="grid gap-3 rounded-lg border bg-muted/40 p-3">
              <p className="text-sm">
                {t('signals.confirmParcelHint', { cadastral: signal.parcel_cadastral_number })}
              </p>
              <div className="grid gap-2">
                <Label>{t('parcel.violationType')}</Label>
                <Select value={violationType} onValueChange={(v) => setViolationType(v as ViolationType)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VIOLATION_TYPES.map((vt) => (
                      <SelectItem key={vt} value={vt}>
                        {t(`violationType.${vt}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="signal-deadline">{t('parcel.deadline')}</Label>
                <Input
                  id="signal-deadline"
                  type="date"
                  min={toDateInput(new Date().toISOString())}
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </div>
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="signal-comment">
              {target === 'REJECTED' ? t('signals.rejectReason') : t('transition.comment')} *
            </Label>
            <Textarea
              id="signal-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t(`transition.placeholder.SIGNAL_${target}`)}
              maxLength={2000}
              autoFocus
            />
            {signal.has_reporter && (
              <p className="text-xs text-muted-foreground">{t('signals.citizenWillSee')}</p>
            )}
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={!valid || mutation.isPending}
              variant={
                target === 'CONFIRMED' ? 'destructive' : target === 'REJECTED' ? 'secondary' : 'default'
              }
            >
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {t('common.confirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
