import type { components } from './schema'

type S = components['schemas']

export type ParcelStatus = S['ParcelStatus']
export type ViolationType = S['ViolationType']
export type ParcelPurpose = S['ParcelPurpose']
export type OwnerType = S['OwnerType']
export type SignalStatus = S['SignalStatus']
export type SignalCategory = S['SignalCategory']
export type ApplicationStatus = S['ApplicationStatus']
export type AllocationStatus = S['AllocationStatus']
export type LandFund = S['LandFund']
export type LandApplicationCreate = S['LandApplicationCreate']
export type LandApplicationDraft = S['LandApplicationDraft']
export type MiniAppApplication = S['MiniAppApplication']
export type ApplicationParcel = S['ApplicationParcelOut']
export type ApplicationType = S['ApplicationType']

export type ParcelFeatureCollection = S['ParcelFeatureCollection']
export type ParcelFeature = S['ParcelFeature']
export type ParcelProperties = S['ParcelProperties']
export type ParcelDetail = S['ParcelDetail']
export type ParcelSearchResult = S['ParcelSearchResult']
export type ParcelTransitionRequest = S['ParcelTransitionRequest']
export type ParcelUpdateRequest = S['ParcelUpdateRequest']
export type CadastreRecord = S['CadastreRecord']
export type Photo = S['PhotoOut']
export type Transition = S['TransitionOut']

export type SignalSummary = S['SignalSummary']
export type SignalDetail = S['SignalDetail']
export type SignalList = S['SignalList']
export type SignalTransitionRequest = S['SignalTransitionRequest']

export type Application = S['ApplicationOut']
export type ApplicationList = S['ApplicationList']
export type ApplicationTransitionRequest = S['ApplicationTransitionRequest']

export type DashboardStats = S['DashboardStats']
export type NdviLayer = S['NdviLayer']
export type EventOut = S['EventOut']
export type EventList = S['EventList']
export type Inspector = S['InspectorOut']
export type TokenResponse = S['TokenResponse']
export type AuthConfig = S['AuthConfig']

export const PARCEL_STATUSES: ParcelStatus[] = [
  'OK',
  'UNDER_CHECK',
  'VIOLATION',
  'IN_REMEDIATION',
  'RESOLVED',
  'RETURNED_TO_STATE',
]
export const VIOLATION_TYPES: ViolationType[] = ['UNUSED', 'SELF_SEIZURE', 'DUMP', 'MISUSE']
export const PURPOSES: ParcelPurpose[] = ['IZHS', 'AGRICULTURE', 'COMMERCIAL', 'INDUSTRIAL', 'LPH']
export const SIGNAL_STATUSES: SignalStatus[] = ['NEW', 'IN_REVIEW', 'CONFIRMED', 'REJECTED']
export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'UNDER_REVIEW',
  'INSPECTION_SCHEDULED',
  'APPROVED',
  'REJECTED',
]

export type InspectionStatus = S['InspectionStatus']
export type InspectionVerdict = S['InspectionVerdict']
export type DeclaredUse = S['DeclaredUse']
export type Inspection = S['InspectionOut']
export type InspectionCheck = S['CheckOut']
export type RiskItem = S['RiskItem']
export type ResolutionEvidence = S['ResolutionEvidence']
export type CrossCheck = S['CrossCheck']
export type ParcelSatellite = S['ParcelSatellite']
export type InspectionPublic = S['InspectionPublic']
export type ActPublic = S['ActPublic']
export const DECLARED_USES: DeclaredUse[] = ['CULTIVATED', 'BUILDING', 'CLEANED', 'FALLOW', 'OTHER']
