import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Tooltip } from '@/components/ui/misc'
import { copyToClipboard } from '@/lib/utils'

export function CopyButton({ value }: { value: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <Tooltip content={copied ? t('common.copied') : t('common.copy')}>
      <button
        type="button"
        aria-label={t('common.copy')}
        className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        onClick={async () => {
          if (await copyToClipboard(value)) {
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1500)
          }
        }}
      >
        {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      </button>
    </Tooltip>
  )
}
