/** Client-side mirror of apps/api/app/domain/person.py: instant feedback in the Mini App form. */

const W1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
const W2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]

export function iinIsValid(iin: string): boolean {
  if (!/^\d{12}$/.test(iin)) return false
  const d = [...iin].map(Number)
  const century = ({ 1: 1800, 2: 1800, 3: 1900, 4: 1900, 5: 2000, 6: 2000 } as Record<number, number>)[d[6]!]
  if (!century) return false
  const year = century + Number(iin.slice(0, 2))
  const month = Number(iin.slice(2, 4))
  const day = Number(iin.slice(4, 6))
  const date = new Date(Date.UTC(year, month - 1, day))
  if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return false
  let check = W1.reduce((sum, w, i) => sum + w * d[i]!, 0) % 11
  if (check === 10) {
    check = W2.reduce((sum, w, i) => sum + w * d[i]!, 0) % 11
    if (check === 10) return false
  }
  return check === d[11]
}

/** '+7 7XX XXX XX XX' → '+77XXXXXXXXX', or null if it is not a Kazakhstan mobile number. */
export function normalizePhone(phone: string): string | null {
  let digits = phone.replace(/\D/g, '')
  if (digits.length === 11 && (digits[0] === '7' || digits[0] === '8')) digits = '7' + digits.slice(1)
  else if (digits.length === 10) digits = '7' + digits
  return /^77\d{9}$/.test(digits) ? `+${digits}` : null
}
