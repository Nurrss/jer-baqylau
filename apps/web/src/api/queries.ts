import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap, uploadWithProgress } from './client'
import type {
  ApplicationStatus,
  ApplicationTransitionRequest,
  ParcelDetail,
  ParcelStatus,
  ParcelTransitionRequest,
  ParcelUpdateRequest,
  SignalStatus,
  SignalTransitionRequest,
  InspectionStatus,
  LandApplicationCreate,
} from './types'

export const qk = {
  parcels: ['parcels'] as const,
  parcel: (id: string) => ['parcel', id] as const,
  cadastre: (id: string) => ['parcel', id, 'cadastre'] as const,
  search: (q: string) => ['parcel-search', q] as const,
  signals: (statuses: SignalStatus[]) => ['signals', statuses] as const,
  signal: (id: string) => ['signal', id] as const,
  applications: (statuses: ApplicationStatus[], q: string) => ['applications', statuses, q] as const,
  application: (id: string) => ['application', id] as const,
  violations: (statuses: ParcelStatus[]) => ['violations', statuses] as const,
  dashboard: ['dashboard'] as const,
  ndvi: ['ndvi'] as const,
}

// ── Parcels ─────────────────────────────────────────────────────────────────

export function useParcels() {
  return useQuery({
    queryKey: qk.parcels,
    queryFn: async () => unwrap(await api.GET('/api/v1/parcels')),
    staleTime: 30_000,
  })
}

export function useViolationParcels(statuses: ParcelStatus[]) {
  return useQuery({
    queryKey: qk.violations(statuses),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/parcels', { params: { query: { status: statuses } } })),
  })
}

export function useParcel(id: string | null) {
  return useQuery({
    queryKey: qk.parcel(id ?? ''),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/parcels/{parcel_id}', { params: { path: { parcel_id: id! } } })),
    enabled: Boolean(id),
  })
}

export function useCadastre(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: qk.cadastre(id ?? ''),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/parcels/{parcel_id}/cadastre', { params: { path: { parcel_id: id! } } })),
    enabled: Boolean(id) && enabled,
    staleTime: 5 * 60_000,
  })
}

export function useParcelSearch(q: string) {
  const term = q.trim()
  return useQuery({
    queryKey: qk.search(term),
    queryFn: async () => unwrap(await api.GET('/api/v1/parcels/search', { params: { query: { q: term } } })),
    enabled: term.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

function useParcelMutationSuccess() {
  const qc = useQueryClient()
  return (detail: ParcelDetail) => {
    qc.setQueryData(qk.parcel(detail.id), detail)
    void qc.invalidateQueries({ queryKey: qk.parcels })
    void qc.invalidateQueries({ queryKey: ['violations'] })
    void qc.invalidateQueries({ queryKey: ['signals'] })
    void qc.invalidateQueries({ queryKey: qk.dashboard })
  }
}

export function useParcelTransition(id: string) {
  const onSuccess = useParcelMutationSuccess()
  return useMutation({
    mutationFn: async (body: ParcelTransitionRequest) =>
      unwrap(
        await api.POST('/api/v1/parcels/{parcel_id}/transitions', {
          params: { path: { parcel_id: id } },
          body,
        }),
      ),
    onSuccess,
  })
}

export function useParcelUpdate(id: string) {
  const onSuccess = useParcelMutationSuccess()
  return useMutation({
    mutationFn: async (body: ParcelUpdateRequest) =>
      unwrap(await api.PATCH('/api/v1/parcels/{parcel_id}', { params: { path: { parcel_id: id } }, body })),
    onSuccess,
  })
}

export function usePhotoUpload(id: string) {
  const onSuccess = useParcelMutationSuccess()
  return useMutation({
    mutationFn: ({ files, onProgress }: { files: File[]; onProgress: (f: number) => void }) =>
      uploadWithProgress<ParcelDetail>(`/api/v1/parcels/${id}/photos`, files, onProgress),
    onSuccess,
  })
}

// ── Signals ─────────────────────────────────────────────────────────────────

export function useSignals(statuses: SignalStatus[] = []) {
  return useQuery({
    queryKey: qk.signals(statuses),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/signals', { params: { query: { status: statuses, limit: 200 } } })),
    staleTime: 15_000,
  })
}

export function useSignal(id: string | null) {
  return useQuery({
    queryKey: qk.signal(id ?? ''),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/signals/{signal_id}', { params: { path: { signal_id: id! } } })),
    enabled: Boolean(id),
  })
}

export function useSignalTransition(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SignalTransitionRequest) =>
      unwrap(
        await api.POST('/api/v1/signals/{signal_id}/transitions', {
          params: { path: { signal_id: id } },
          body,
        }),
      ),
    onSuccess: (detail) => {
      qc.setQueryData(qk.signal(detail.id), detail)
      void qc.invalidateQueries({ queryKey: ['signals'] })
      void qc.invalidateQueries({ queryKey: qk.parcels })
      void qc.invalidateQueries({ queryKey: ['parcel'] })
      void qc.invalidateQueries({ queryKey: ['violations'] })
      void qc.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}

// ── Applications ────────────────────────────────────────────────────────────

export function useApplications(statuses: ApplicationStatus[], q: string) {
  return useQuery({
    queryKey: qk.applications(statuses, q),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/applications', { params: { query: { status: statuses, q: q || undefined } } }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useApplicationTransition(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ApplicationTransitionRequest) =>
      unwrap(
        await api.POST('/api/v1/applications/{application_id}/transitions', {
          params: { path: { application_id: id } },
          body,
        }),
      ),
    onSuccess: (application) => {
      qc.setQueryData(qk.application(application.id), application)
      void qc.invalidateQueries({ queryKey: ['applications'] })
    },
  })
}

// ── Dashboard / satellite ───────────────────────────────────────────────────

export function useDashboard() {
  return useQuery({
    queryKey: qk.dashboard,
    queryFn: async () => unwrap(await api.GET('/api/v1/stats/dashboard')),
    staleTime: 30_000,
  })
}

export function useNdvi(enabled: boolean) {
  return useQuery({
    queryKey: qk.ndvi,
    queryFn: async () => unwrap(await api.GET('/api/v1/satellite/ndvi')),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useSatelliteScan() {
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/v1/satellite/scan')),
  })
}

// ── Integrity: inspections, risk, evidence, cross-checks, audit ─────────────

export const qkx = {
  inspections: (statuses: string[], parcelId?: string) => ['inspections', statuses, parcelId ?? ''] as const,
  inspection: (id: string) => ['inspection', id] as const,
  risk: ['risk'] as const,
  evidence: (parcelId: string) => ['evidence', parcelId] as const,
  crosscheck: (parcelId: string) => ['crosscheck', parcelId] as const,
  satellite: (parcelId: string) => ['parcel-satellite', parcelId] as const,
  audit: ['audit-verify'] as const,
}

export function useInspections(statuses: InspectionStatus[] = [], parcelId?: string) {
  return useQuery({
    queryKey: qkx.inspections(statuses, parcelId),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/inspection-requests', {
          params: { query: { status: statuses, parcel_id: parcelId ?? null, limit: 200 } },
        }),
      ),
  })
}

export function useInspection(id: string | null) {
  return useQuery({
    queryKey: qkx.inspection(id ?? ''),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/inspection-requests/{request_id}', { params: { path: { request_id: id! } } }),
      ),
    enabled: Boolean(id),
  })
}

function useInvalidateInspections() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['inspections'] })
    void qc.invalidateQueries({ queryKey: ['inspection'] })
    void qc.invalidateQueries({ queryKey: qkx.risk })
    void qc.invalidateQueries({ queryKey: ['evidence'] })
  }
}

export function useRequestInspection(parcelId: string) {
  const invalidate = useInvalidateInspections()
  return useMutation({
    mutationFn: async (body: { due_hours: number; note: string | null }) =>
      unwrap(
        await api.POST('/api/v1/parcels/{parcel_id}/inspection-requests', {
          params: { path: { parcel_id: parcelId } },
          body,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useReviewInspection(id: string) {
  const invalidate = useInvalidateInspections()
  return useMutation({
    mutationFn: async (body: { decision: 'ACCEPTED' | 'REJECTED'; comment: string }) =>
      unwrap(
        await api.POST('/api/v1/inspection-requests/{request_id}/review', {
          params: { path: { request_id: id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useRisk(limit = 30) {
  return useQuery({
    queryKey: [...qkx.risk, limit],
    queryFn: async () => unwrap(await api.GET('/api/v1/risk', { params: { query: { limit } } })),
    staleTime: 30_000,
  })
}

export function useCreatePlan() {
  const invalidate = useInvalidateInspections()
  return useMutation({
    mutationFn: async (body: { size: number; random_share: number }) =>
      unwrap(await api.POST('/api/v1/inspection-plan', { body })),
    onSuccess: invalidate,
  })
}

export function useEvidence(parcelId: string, enabled = true) {
  return useQuery({
    queryKey: qkx.evidence(parcelId),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/parcels/{parcel_id}/evidence', { params: { path: { parcel_id: parcelId } } }),
      ),
    enabled,
  })
}

export function useCrosscheck(parcelId: string, enabled: boolean) {
  return useQuery({
    queryKey: qkx.crosscheck(parcelId),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/parcels/{parcel_id}/crosscheck', {
          params: { path: { parcel_id: parcelId } },
        }),
      ),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useParcelSatellite(parcelId: string, enabled: boolean) {
  return useQuery({
    queryKey: qkx.satellite(parcelId),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/parcels/{parcel_id}/satellite', { params: { path: { parcel_id: parcelId } } }),
      ),
    enabled,
    // While the history is being built in the background, poll (realtime also notifies).
    refetchInterval: (query) => (query.state.data?.status === 'loading' ? 5000 : false),
  })
}

export function useAuditVerify() {
  return useQuery({
    queryKey: qkx.audit,
    queryFn: async () => unwrap(await api.GET('/api/v1/audit/verify')),
    staleTime: 60_000,
  })
}

// ── Public (no login) ───────────────────────────────────────────────────────

export function usePublicInspection(token: string) {
  return useQuery({
    queryKey: ['public-inspection', token],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/public/inspections/{token}', { params: { path: { token } } })),
    retry: false,
  })
}

export function usePublicAct(actId: string) {
  return useQuery({
    queryKey: ['public-act', actId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/public/acts/{act_id}', { params: { path: { act_id: actId } } })),
    retry: false,
  })
}

// ── State land fund (Mini App + panel) ──────────────────────────────────────

export function useLandFund() {
  return useQuery({
    queryKey: ['land-fund'],
    queryFn: async () => unwrap(await api.GET('/api/v1/land/fund')),
    staleTime: 15_000,
  })
}

export function useCreateLandApplication(initData: string, lang: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: LandApplicationCreate) =>
      unwrap(
        await api.POST('/api/v1/miniapp/applications', {
          body,
          params: {
            header: { 'X-Telegram-Init-Data': initData },
            query: { lang: lang === 'kk' ? 'kk' : 'ru' },
          },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['land-fund'] })
      void qc.invalidateQueries({ queryKey: ['my-land-applications'] })
    },
  })
}

export function useMyLandApplications(initData: string | null) {
  return useQuery({
    queryKey: ['my-land-applications'],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/miniapp/applications', {
          params: { header: { 'X-Telegram-Init-Data': initData! } },
        }),
      ),
    enabled: Boolean(initData),
  })
}

export function useOfferParcel(parcelId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (offered: boolean) =>
      unwrap(
        offered
          ? await api.POST('/api/v1/parcels/{parcel_id}/offer', { params: { path: { parcel_id: parcelId } } })
          : await api.DELETE('/api/v1/parcels/{parcel_id}/offer', {
              params: { path: { parcel_id: parcelId } },
            }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.parcel(parcelId) })
      void qc.invalidateQueries({ queryKey: qk.parcels })
      void qc.invalidateQueries({ queryKey: ['land-fund'] })
    },
  })
}
