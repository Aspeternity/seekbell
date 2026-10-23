export type HistoryDateRange = readonly [string, string] | null

export function dateRangeParams(range: HistoryDateRange) {
  return { date_from: range?.[0], date_to: range?.[1] }
}
