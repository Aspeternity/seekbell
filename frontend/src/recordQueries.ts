import { historyGet } from './history'
import type { DeliveryRecord, ManualRecord, Options, Page, TestRecord } from './history'
import { dateRangeParams, type HistoryDateRange } from './dateRange'
import { cachedRead, fetchRead, readIsFresh } from './readCache'

export const recordTabs = ['deliveries', 'manual', 'tests'] as const
export const recordOptionsKey = 'content:options'
export const loadRecordOptions = () => historyGet<Options>('options')
export interface RecordFilters {
  q: string
  status: string
  target: string
  dateRange: HistoryDateRange
  uncertain: string
  page: number
  timezone: string
}
export const defaultRecordFilters = (timezone: string): RecordFilters => ({
  q: '',
  status: 'all',
  target: '',
  dateRange: null,
  uncertain: 'all',
  page: 1,
  timezone,
})
export function recordListKey(tab: string, f: RecordFilters) {
  return JSON.stringify([
    'records',
    tab,
    f.q,
    f.status,
    f.target,
    f.dateRange,
    f.uncertain,
    f.page,
    f.timezone,
  ])
}
export function loadRecordList(tab: string, f: RecordFilters) {
  return historyGet<Page<DeliveryRecord> | Page<TestRecord> | Page<ManualRecord>>(tab, {
    q: f.q,
    status: f.status,
    target_id: f.target,
    ...dateRangeParams(f.dateRange),
    timezone: f.timezone,
    page: f.page,
    uncertain: tab === 'deliveries' && f.uncertain !== 'all' ? f.uncertain === 'true' : undefined,
  })
}
export function recordsPrepared(tab: string, timezone: string) {
  return [recordOptionsKey, recordListKey(tab, defaultRecordFilters(timezone))].every(
    (key) => readIsFresh(key) && cachedRead(key) !== undefined,
  )
}
export function prepareRecords(tab: string, timezone: string) {
  const filters = defaultRecordFilters(timezone)
  return Promise.all([
    readIsFresh(recordOptionsKey) && cachedRead(recordOptionsKey) !== undefined
      ? Promise.resolve(cachedRead(recordOptionsKey))
      : fetchRead(recordOptionsKey, loadRecordOptions),
    fetchRead(recordListKey(tab, filters), () => loadRecordList(tab, filters)),
  ])
}
