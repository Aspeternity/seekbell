export interface HotlistConfiguration {
  provider: string
  provider_url: string
  mode: 'recommended' | 'custom'
  periods: {
    id: string
    label: string
    interval_seconds: number
    recommended_seconds: number
    minimum_seconds: number
  }[]
}
export interface HotlistDraft {
  mode: 'recommended' | 'custom'
  minutes: Record<string, number>
}
export interface HotlistSettingsInput {
  mode: 'recommended' | 'custom'
  intervals: Record<string, number>
}
export function hotlistDraft(config: HotlistConfiguration | null | undefined): HotlistDraft | null {
  return config
    ? {
        mode: config.mode,
        minutes: Object.fromEntries(config.periods.map((p) => [p.id, p.interval_seconds / 60])),
      }
    : null
}
export function hotlistError(config: HotlistConfiguration, draft: HotlistDraft): string {
  if (draft.mode === 'recommended') return ''
  for (const period of config.periods) {
    const value = draft.minutes[period.id]
    if (!Number.isInteger(value) || value < period.minimum_seconds / 60 || value > 1440)
      return (
        period.label + '榜刷新间隔应为 ' + period.minimum_seconds / 60 + '–1440 之间的整数分钟。'
      )
  }
  return ''
}
export function hotlistInput(draft: HotlistDraft): HotlistSettingsInput {
  return {
    mode: draft.mode,
    intervals:
      draft.mode === 'custom'
        ? Object.fromEntries(Object.entries(draft.minutes).map(([key, value]) => [key, value * 60]))
        : {},
  }
}
