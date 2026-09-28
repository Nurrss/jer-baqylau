import { iinIsValid, normalizePhone } from './person'

test('IIN check digit matches the backend rule', () => {
  expect(iinIsValid('900101300017')).toBe(true)
  expect(iinIsValid('900101300014')).toBe(false)
  expect(iinIsValid('901301300017')).toBe(false) // month 13
  expect(iinIsValid('12345')).toBe(false)
})

test('phones are normalized to +77XXXXXXXXX', () => {
  expect(normalizePhone('8 (701) 234-56-78')).toBe('+77012345678')
  expect(normalizePhone('+7 701 234 56 78')).toBe('+77012345678')
  expect(normalizePhone('701 234 56 78')).toBe('+77012345678')
  expect(normalizePhone('+1 202 555 0100')).toBeNull()
})
