export interface OverviewData {
  range: '24h' | '7d'
  start: number
  end: number
  runtime_active: boolean
  today: { start: number; end: number; timezone: string }
  runtime: { active: boolean; status: string; code: string | null }
  configuration: { websites: number; tasks: number; enabled_tasks: number; targets: number }
  window: {
    posts: number
    matches: number
    insufficient_data: number
    delivered: number
    source_failures: number
  }
  current: { queue: Record<string, number>; uncertain: number; attention: number }
  buckets: { start: number; end: number; matches: number }[]
  tasks: { id: string; matches: number; last_match_at: number | null }[]
  sources: {
    website_id: string
    name: string
    source_id: string
    enabled: boolean
    interval_seconds: number
    today_posts: number
    recent_runs: { id: number; at: number; status: 'success' | 'failure' | 'unknown' }[]
    last_attempt_at: number | null
    next_attempt_at: number
    last_success_at: number | null
    failures: number
    error_code: string | null
    possible_gap: boolean
    last_gap_at: number | null
  }[]
  recent_matches: {
    post_id: string | null
    title: string | null
    task_name: string
    task_version: number
    task_deleted: boolean
    at: number
  }[]
}
