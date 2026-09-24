import { EMPTY_FILTERS } from '@/store/ui'
import { buildParcelFilter } from './filters'

test('no filters → match everything', () => {
  expect(buildParcelFilter(EMPTY_FILTERS)).toEqual(['all'])
})

test('combines status, type, purpose and overdue clauses', () => {
  const filter = buildParcelFilter({
    statuses: ['VIOLATION'],
    violationTypes: ['DUMP'],
    purposes: ['IZHS'],
    overdueOnly: true,
  })
  expect(filter).toEqual([
    'all',
    ['in', ['get', 'status'], ['literal', ['VIOLATION']]],
    ['in', ['coalesce', ['get', 'violation_type'], ''], ['literal', ['DUMP']]],
    ['in', ['get', 'purpose'], ['literal', ['IZHS']]],
    ['==', ['get', 'is_overdue'], true],
  ])
})
