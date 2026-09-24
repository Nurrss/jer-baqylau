import { differenceInCalendarDays, format, formatDistanceToNow, parseISO } from 'date-fns'
import { kk, ru } from 'date-fns/locale'
import { useTranslation } from 'react-i18next'

export function useDateFns() {
  const { i18n } = useTranslation()
  const locale = i18n.language === 'kk' ? kk : ru
  return {
    locale,
    date: (iso: string | null | undefined) => (iso ? format(parseISO(iso), 'dd.MM.yyyy', { locale }) : '—'),
    dateTime: (iso: string | null | undefined) =>
      iso ? format(parseISO(iso), 'dd.MM.yyyy HH:mm', { locale }) : '—',
    relative: (iso: string) => formatDistanceToNow(parseISO(iso), { addSuffix: true, locale }),
  }
}

/** Calendar days until the deadline (negative when overdue). */
export function daysUntil(iso: string, now: Date = new Date()): number {
  return differenceInCalendarDays(parseISO(iso), now)
}

/** yyyy-MM-dd for <input type="date"> */
export function toDateInput(iso: string | null | undefined): string {
  return iso ? format(parseISO(iso), 'yyyy-MM-dd') : ''
}

/** End of the chosen local day as ISO (deadlines are "until end of day"). */
export function fromDateInput(value: string): string {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y!, (m ?? 1) - 1, d ?? 1, 18, 0, 0).toISOString()
}
