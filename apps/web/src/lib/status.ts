import type { AllocationStatus, ApplicationStatus, ParcelStatus, SignalStatus } from '@/api/types'

/** Map colors for parcel statuses (also used by legend and badges). */
export const PARCEL_STATUS_COLORS: Record<ParcelStatus, string> = {
  OK: '#16a34a',
  UNDER_CHECK: '#eab308',
  VIOLATION: '#dc2626',
  IN_REMEDIATION: '#dc2626',
  RESOLVED: '#059669',
  RETURNED_TO_STATE: '#5b7089',
}

export const SIGNAL_STATUS_COLORS: Record<SignalStatus, string> = {
  NEW: '#7c3aed',
  IN_REVIEW: '#2563eb',
  CONFIRMED: '#dc2626',
  REJECTED: '#64748b',
}

export const APPLICATION_STATUS_COLORS: Record<ApplicationStatus, string> = {
  DRAFT: '#94a3b8',
  CANCELLED: '#94a3b8',
  UNDER_REVIEW: '#eab308',
  INSPECTION_SCHEDULED: '#2563eb',
  APPROVED: '#16a34a',
  REJECTED: '#dc2626',
}

/** State land fund on the map: free land and land under an application. */
export const ALLOCATION_COLORS: Record<Exclude<AllocationStatus, 'NONE' | 'ALLOCATED'>, string> = {
  OFFERED: '#0891b2',
  RESERVED: '#6366f1',
}

/** Lifecycle stepper for a violation case. */
export const LIFECYCLE_STEPS = ['VIOLATION', 'IN_REMEDIATION', 'FINAL'] as const
export type LifecycleStep = (typeof LIFECYCLE_STEPS)[number]

export function lifecycleIndex(status: ParcelStatus): number {
  switch (status) {
    case 'VIOLATION':
      return 0
    case 'IN_REMEDIATION':
      return 1
    case 'RESOLVED':
    case 'RETURNED_TO_STATE':
      return 2
    default:
      return -1
  }
}

/** NDVI color ramp (bare soil → dense vegetation). */
export const NDVI_STOPS: [number, string][] = [
  [0, '#a8501c'],
  [0.15, '#d99a3e'],
  [0.3, '#e9d56b'],
  [0.45, '#a6d96a'],
  [0.6, '#4daf4a'],
  [0.8, '#1a7a32'],
]
