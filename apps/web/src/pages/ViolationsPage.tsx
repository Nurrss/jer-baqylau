import { ArrowDownUp, Download, FileJson, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { downloadFile } from '@/api/client'
import { useViolationParcels } from '@/api/queries'
import { VIOLATION_TYPES, type ParcelProperties, type ParcelStatus, type ViolationType } from '@/api/types'
import { EmptyState, ErrorState } from '@/components/common/States'
import { useErrorMessage } from '@/lib/useErrorMessage'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Button } from '@/components/ui/button'
import { Switch, Tabs, TabsList, TabsTrigger } from '@/components/ui/misc'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { DeadlineChip } from '@/features/parcel/ParcelPanel'
import { useDateFns } from '@/lib/dates'
import { formatArea } from '@/lib/utils'

const SCOPES: Record<string, ParcelStatus[]> = {
  active: ['VIOLATION', 'IN_REMEDIATION'],
  violation: ['VIOLATION'],
  remediation: ['IN_REMEDIATION'],
  closed: ['RESOLVED', 'RETURNED_TO_STATE'],
}

type SortKey = 'deadline' | 'area' | 'cadastral'

function compare(a: ParcelProperties, b: ParcelProperties, key: SortKey): number {
  if (key === 'area') return b.area_ha - a.area_ha
  if (key === 'cadastral') return a.cadastral_number.localeCompare(b.cadastral_number)
  const da = a.deadline_at ? Date.parse(a.deadline_at) : Number.POSITIVE_INFINITY
  const db = b.deadline_at ? Date.parse(b.deadline_at) : Number.POSITIVE_INFINITY
  return da - db
}

function SortButton({
  k,
  sort,
  onSort,
  children,
}: {
  k: SortKey
  sort: SortKey
  onSort: (k: SortKey) => void
  children: string
}) {
  return (
    <button
      type="button"
      onClick={() => onSort(k)}
      className={`inline-flex items-center gap-1 ${sort === k ? 'text-foreground' : ''}`}
    >
      {children}
      <ArrowDownUp className="size-3 opacity-60" />
    </button>
  )
}

export function ViolationsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const errorMessage = useErrorMessage()
  const { date } = useDateFns()
  const [scope, setScope] = useState<keyof typeof SCOPES>('active')
  const [type, setType] = useState<ViolationType | 'all'>('all')
  const [overdueOnly, setOverdueOnly] = useState(false)
  const [sort, setSort] = useState<SortKey>('deadline')
  const query = useViolationParcels(SCOPES[scope] ?? [])

  const rows = useMemo(() => {
    const items = (query.data?.features ?? []).map((f) => f.properties)
    return items
      .filter((p) => type === 'all' || p.violation_type === type)
      .filter((p) => !overdueOnly || p.is_overdue)
      .sort((a, b) => compare(a, b, sort))
  }, [query.data, type, overdueOnly, sort])

  const exportAs = async (format: 'csv' | 'geojson') => {
    try {
      await downloadFile(`/api/v1/export/parcels.${format}`, `parcels.${format}`)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="mx-auto max-w-7xl p-4 md:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">{t('violations.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('violations.subtitle')}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => void exportAs('csv')}>
              <Download /> CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => void exportAs('geojson')}>
              <FileJson /> GeoJSON
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Tabs value={scope} onValueChange={(v) => setScope(v as keyof typeof SCOPES)}>
            <TabsList>
              {Object.keys(SCOPES).map((key) => (
                <TabsTrigger key={key} value={key}>
                  {t(`violations.scope.${key}`)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Select value={type} onValueChange={(v) => setType(v as ViolationType | 'all')}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('violations.allTypes')}</SelectItem>
              {VIOLATION_TYPES.map((vt) => (
                <SelectItem key={vt} value={vt}>
                  {t(`violationType.${vt}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={overdueOnly} onCheckedChange={setOverdueOnly} /> {t('map.overdueOnly')}
          </label>
        </div>

        <div className="mt-4 overflow-x-auto rounded-xl border bg-card">
          {query.isLoading ? (
            <div className="grid gap-2 p-4">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState icon={<ShieldAlert className="size-6" />} title={t('violations.empty')} />
          ) : (
            <table className="w-full min-w-[860px] text-sm">
              <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-3 font-semibold">
                    <SortButton k="cadastral" sort={sort} onSort={setSort}>
                      {t('parcel.cadastralNumber')}
                    </SortButton>
                  </th>
                  <th className="px-4 py-3 font-semibold">{t('parcel.status')}</th>
                  <th className="px-4 py-3 font-semibold">{t('parcel.violationType')}</th>
                  <th className="px-4 py-3 font-semibold">
                    <SortButton k="deadline" sort={sort} onSort={setSort}>
                      {t('parcel.deadline')}
                    </SortButton>
                  </th>
                  <th className="px-4 py-3 text-right font-semibold">
                    <SortButton k="area" sort={sort} onSort={setSort}>
                      {t('parcel.area')}
                    </SortButton>
                  </th>
                  <th className="px-4 py-3 font-semibold">{t('parcel.address')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                    onClick={() => navigate(`/map?parcel=${p.id}`)}
                  >
                    <td className="px-4 py-3 font-mono font-medium">{p.cadastral_number}</td>
                    <td className="px-4 py-3">
                      <StatusBadge kind="parcel" status={p.status} />
                    </td>
                    <td className="px-4 py-3">
                      {p.violation_type ? t(`violationType.${p.violation_type}`) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="tabular-nums">{date(p.deadline_at)}</span>
                        {p.deadline_at && (
                          <DeadlineChip
                            deadline={p.deadline_at}
                            active={p.status === 'VIOLATION' || p.status === 'IN_REMEDIATION'}
                          />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatArea(p.area_ha, i18n.language)} {t('units.ha')}
                    </td>
                    <td className="max-w-72 truncate px-4 py-3 text-muted-foreground">
                      {i18n.language === 'kk' ? p.address_kk : p.address_ru}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
