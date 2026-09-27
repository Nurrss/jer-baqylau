import { CheckCircle2, FileCheck2, FileX2, Loader2, ShieldAlert, ShieldCheck, Upload } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { usePublicAct } from '@/api/queries'
import { StatusBadge } from '@/components/common/StatusBadge'
import { ErrorState } from '@/components/common/States'
import { PublicLayout } from '@/components/layout/PublicLayout'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { ParcelStatus } from '@/api/types'
import { useDateFns } from '@/lib/dates'
import { cn } from '@/lib/utils'

async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Hash the file locally: the PDF never leaves the device. */
function FileCheck({ expected }: { expected: string }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<{ name: string; match: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <div className="grid gap-2">
      <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed p-5 text-sm hover:bg-muted">
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
        {t('verify.pickFile')}
        <input
          type="file"
          accept="application/pdf"
          className="sr-only"
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return
            setBusy(true)
            try {
              setResult({ name: file.name, match: (await sha256Hex(file)) === expected })
            } finally {
              setBusy(false)
            }
          }}
        />
      </label>
      {result && (
        <div
          className={cn(
            'flex gap-2 rounded-lg p-3 text-sm',
            result.match ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive',
          )}
        >
          {result.match ? <FileCheck2 className="size-4 shrink-0" /> : <FileX2 className="size-4 shrink-0" />}
          <span>
            <span className="font-medium">{result.name}</span> —{' '}
            {t(result.match ? 'verify.fileMatch' : 'verify.fileMismatch')}
          </span>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{t('verify.fileHint')}</p>
    </div>
  )
}

export function VerifyPage() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const { dateTime } = useDateFns()
  const query = usePublicAct(id)

  if (query.isLoading) {
    return (
      <PublicLayout>
        <Skeleton className="h-24" />
        <Skeleton className="h-48" />
      </PublicLayout>
    )
  }
  if (query.isError || !query.data) {
    return (
      <PublicLayout>
        <Card>
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        </Card>
      </PublicLayout>
    )
  }
  const act = query.data
  const chain = act.chain_at_issue
  return (
    <PublicLayout>
      <Card className="grid gap-2 p-5">
        <div className="flex items-center gap-2 text-success">
          <CheckCircle2 className="size-5" />
          <span className="font-semibold">{t('verify.found')}</span>
        </div>
        <h1 className="font-mono text-xl font-semibold">{act.number}</h1>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">{t('verify.issuedAt')}</dt>
          <dd>{dateTime(act.issued_at)}</dd>
          <dt className="text-muted-foreground">{t('verify.parcel')}</dt>
          <dd className="font-mono">{act.cadastral_number}</dd>
          <dt className="text-muted-foreground">{t('verify.statusAtIssue')}</dt>
          <dd>
            <StatusBadge kind="parcel" status={act.parcel_status as ParcelStatus} />
          </dd>
          <dt className="text-muted-foreground">{t('verify.issuedBy')}</dt>
          <dd>{act.issued_by}</dd>
          <dt className="text-muted-foreground">{t('verify.photos')}</dt>
          <dd>{act.photo_count}</dd>
        </dl>
      </Card>

      <Card className="grid gap-2 p-5">
        <div
          className={cn(
            'flex items-center gap-2 font-semibold',
            chain.intact ? 'text-success' : 'text-destructive',
          )}
        >
          {chain.intact ? <ShieldCheck className="size-5" /> : <ShieldAlert className="size-5" />}
          {t(chain.intact ? 'verify.chainIntact' : 'verify.chainBroken')}
        </div>
        <p className="text-sm text-muted-foreground">{t('verify.chainHint', { count: chain.length })}</p>
        <p className="font-mono text-[11px] break-all text-muted-foreground">{chain.head}</p>
      </Card>

      <Card className="grid gap-3 p-5">
        <h2 className="font-semibold">{t('verify.fileTitle')}</h2>
        <FileCheck expected={act.pdf_sha256} />
        <p className="font-mono text-[11px] break-all text-muted-foreground">SHA-256: {act.pdf_sha256}</p>
      </Card>
    </PublicLayout>
  )
}
