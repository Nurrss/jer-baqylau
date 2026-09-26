import { Check, Copy, Loader2, Send } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useRequestInspection } from '@/api/queries'
import type { Inspection } from '@/api/types'
import { QrCode } from '@/components/common/QrCode'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDateFns } from '@/lib/dates'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { copyToClipboard } from '@/lib/utils'

const DUE_OPTIONS = [24, 48, 72, 168]

export function InspectionLink({ inspection }: { inspection: Inspection }) {
  const { t } = useTranslation()
  const { dateTime } = useDateFns()
  const [copied, setCopied] = useState(false)
  if (!inspection.link) return null
  return (
    <div className="grid justify-items-center gap-3 rounded-xl border bg-muted/40 p-4 text-center">
      <QrCode value={inspection.link} />
      <p className="text-xs text-muted-foreground">{t('inspections.linkHint', { date: dateTime(inspection.due_at) })}</p>
      <div className="flex w-full items-center gap-2 rounded-lg border bg-card px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-left font-mono text-xs">{inspection.link}</span>
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            if (await copyToClipboard(inspection.link!)) {
              setCopied(true)
              window.setTimeout(() => setCopied(false), 1500)
            }
          }}
        >
          {copied ? <Check /> : <Copy />} {copied ? t('common.copied') : t('common.copy')}
        </Button>
      </div>
    </div>
  )
}

export function RequestInspectionDialog({
  parcelId,
  cadastral,
  onClose,
}: {
  parcelId: string
  cadastral: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const mutation = useRequestInspection(parcelId)
  const [due, setDue] = useState('48')
  const [note, setNote] = useState(t('inspections.defaultNote'))
  const [error, setError] = useState<string | null>(null)
  const created = mutation.data

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.requestTitle')}</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{cadastral}</span> · {t('inspections.requestSubtitle')}
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <>
            <p className="text-sm">{t('inspections.created', { code: created.code })}</p>
            <InspectionLink inspection={created} />
            <DialogFooter>
              <Button onClick={onClose}>{t('common.close')}</Button>
            </DialogFooter>
          </>
        ) : (
          <form
            className="grid gap-4"
            onSubmit={async (e) => {
              e.preventDefault()
              setError(null)
              try {
                await mutation.mutateAsync({ due_hours: Number(due), note: note.trim() || null })
              } catch (err) {
                setError(errorMessage(err))
              }
            }}
          >
            <div className="grid gap-2">
              <Label>{t('inspections.due')}</Label>
              <Select value={due} onValueChange={setDue}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DUE_OPTIONS.map((h) => (
                    <SelectItem key={h} value={String(h)}>
                      {t('inspections.dueHours', { count: h })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="inspection-note">{t('inspections.note')}</Label>
              <Textarea id="inspection-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
            </div>
            <p className="rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">{t('inspections.antifraudHint')}</p>
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? <Loader2 className="animate-spin" /> : <Send />}
                {t('inspections.create')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
