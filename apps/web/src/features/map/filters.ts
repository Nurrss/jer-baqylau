import type { ExpressionSpecification, FilterSpecification } from 'maplibre-gl'
import type { MapFilters } from '@/store/ui'

/** MapLibre filter expression for the parcel layers (filtering is client-side: counts stay visible). */
export function buildParcelFilter(filters: MapFilters): FilterSpecification {
  const clauses: ExpressionSpecification[] = []
  if (filters.statuses.length) clauses.push(['in', ['get', 'status'], ['literal', filters.statuses]])
  if (filters.violationTypes.length)
    clauses.push(['in', ['coalesce', ['get', 'violation_type'], ''], ['literal', filters.violationTypes]])
  if (filters.purposes.length) clauses.push(['in', ['get', 'purpose'], ['literal', filters.purposes]])
  if (filters.overdueOnly) clauses.push(['==', ['get', 'is_overdue'], true])
  return (clauses.length ? ['all', ...clauses] : ['all']) as FilterSpecification
}
