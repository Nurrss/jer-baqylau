import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatArea(ha: number, locale: string): string {
  const digits = ha < 1 ? 3 : ha < 10 ? 2 : 1
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(ha)
}

export function formatCoords(lat: number, lon: number): string {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
