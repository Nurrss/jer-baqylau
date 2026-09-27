import { Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useEvidence, useParcelTransition } from '@/api/queries'
import { VIOLATION_TYPES, type ParcelDetail, type ParcelStatus, type ViolationType } from '@/api/types'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { StatusBadge } from '@/components/common/StatusBadge'
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
import { EvidenceList } from '@/features/integrity/EvidenceList'
import { fromDateInput, toDateInput } from '@/lib/dates'

const DEFAULT_DEADLINE_DAYS = 30

function defaultDeadline(): string {
  const date = new Date()
  date.setDate(date.getDate() + DEFAULT_DEADLINE_DAYS)
  return toDateInput(date.toISOString())
}

export function ParcelTransitionDialog({
  parcel,
  target,
  onClose,
}: {
  parcel: ParcelDetail
  target: ParcelStatus | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const mutation = useParcelTransition(parcel.id)
  const [comment, setComment] = useState('')
  const [violationType, setViolationType] = useState<ViolationType | ''>(parcel.violation_type ?? '')
  const [deadline, setDeadline] = useState(() => {
    // A new violation, or an overdue one getting a precept, starts from a fresh 30-day term.
    const current =
      parcel.deadline_at && Date.parse(parcel.deadline_at) > Date.now() ? parcel.deadline_at : null
    return target === 'VIOLATION' || !current ? defaultDeadline() : toDateInput(current)
  })
  const [error, setError] = useState<string | null>(null)

  const needsType = target === 'VIOLATION'
  const showDeadline = target === 'VIOLATION' || target === 'IN_REMEDIATION'
  const today = toDateInput(new Date().toISOString())
  const needsEvidence = target === 'RESOLVED'
  const evidence = useEvidence(parcel.id, needsEvidence)
  const evidenceOk = !needsEvidence || evidence.data?.sufficient === true
  const valid =
    comment.trim().length >= 3 &&
    (!needsType || violationType !== '') &&
    (!needsType || deadline) &&
    evidenceOk

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!target || !valid) return
    setError(null)
    try {
      await mutation.mutateAsync({
        to: target,
        comment: comment.trim(),
        violation_type: violationType || null,
        deadline_at:
          showDeadline && deadline && deadline !== toDateInput(parcel.deadline_at)
            ? fromDateInput(deadline)
            : null,
      })
      toast.success(t('transition.done', { status: t(`parcelStatus.${target}`) }))
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {target && (
          <form onSubmit={submit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{t(`transition.action.PARCEL.${target}`)}</DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-2">
                <span className="font-mono">{parcel.cadastral_number}</span>
                <StatusBadge kind="parcel" status={parcel.status} /> →
                <StatusBadge kind="parcel" status={target} />
              </DialogDescription>
            </DialogHeader>

            {needsType && (
              <div className="grid gap-2">
                <Label>{t('parcel.violationType')} *</Label>
                <Select value={violationType} onValueChange={(v) => setViolationType(v as ViolationType)}>
                  <SelectTrigger>
                    <SelectValue placeholder={t('transition.chooseType')} />
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
            )}

            {showDeadline && (
              <div className="grid gap-2">
                <Label htmlFor="deadline">
                  {t('parcel.deadline')} {needsType && '*'}
                </Label>
                <Input
                  id="deadline"
                  type="date"
                  min={today}
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </div>
            )}

            {needsEvidence && <EvidenceList evidence={evidence.data} loading={evidence.isLoading} />}

            <div className="grid gap-2">
              <Label htmlFor="comment">{t('transition.comment')} *</Label>
              <Textarea
                id="comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t(`transition.placeholder.${target}`)}
                maxLength={2000}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">{t('transition.commentHint')}</p>
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
                variant={target === 'VIOLATION' || target === 'RETURNED_TO_STATE' ? 'destructive' : 'default'}
              >
                {mutation.isPending && <Loader2 className="animate-spin" />}
                {t('common.confirm')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
