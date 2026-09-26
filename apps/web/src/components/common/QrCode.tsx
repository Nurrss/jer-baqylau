import QRCode from 'qrcode'
import { useEffect, useState } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function QrCode({ value, size = 168, className }: { value: string; size?: number; className?: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void QRCode.toDataURL(value, { width: size * 2, margin: 1, errorCorrectionLevel: 'M' }).then((url) => {
      if (alive) setSrc(url)
    })
    return () => {
      alive = false
    }
  }, [value, size])
  if (!src) return <Skeleton className={cn('rounded-lg', className)} style={{ width: size, height: size }} />
  return (
    <img src={src} alt="QR" width={size} height={size} className={cn('rounded-lg border bg-white p-1', className)} />
  )
}
