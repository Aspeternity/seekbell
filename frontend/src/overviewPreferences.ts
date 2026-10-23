export type OverviewModuleId = 'tasks' | 'matches' | 'hotlist'
export interface OverviewModule {
  id: OverviewModuleId
  visible: boolean
}
export const moduleNames: Record<OverviewModuleId, string> = {
  tasks: '监控任务',
  matches: '最近命中',
  hotlist: '社区热榜',
}
export const defaultOverviewModules = (): OverviewModule[] => [
  { id: 'tasks', visible: true },
  { id: 'matches', visible: true },
  { id: 'hotlist', visible: true },
]
export interface HotlistSource {
  website_id: string
  name: string
  provider_id: string
  provider: string
  provider_url: string
  default_period: string
  periods: { id: string; label: string }[]
}
export interface OverviewPreferences {
  modules: OverviewModule[]
  revision: number
  selection: { website_id: string | null; periods: Record<string, string>; revision: number }
  sources: HotlistSource[]
}
export interface HotlistData extends HotlistSource {
  period: string
  status: 'ready' | 'stale' | 'unavailable'
  refreshing?: boolean
  error_code: string | null
  source_updated_at: number | null
  fetched_at: number | null
  next_attempt_at: number
  items: {
    id: string
    rank: number
    title: string
    url: string
    author: string | null
    category: string | null
    comments: number | null
    views: number | null
  }[]
}
