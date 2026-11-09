import { formatTime, state } from './store'

export type Tone = 'none' | 'ok' | 'wait' | 'warn' | 'fail'
export type Handling = 'auto_retry' | 'action' | 'verifying'

export interface StatusNode {
  state: string
  tone: Tone
  label: string
  detail: string | null
  at: number | null
}
export interface Guide {
  stage: string
  summary: string
  causes: string[]
  steps: string[]
  handling: string
  verify: 'rss_test' | 'target_test' | 'restart' | null
  known: boolean
}
export interface Problem {
  key: string
  kind: 'source' | 'delivery' | 'runtime' | 'stall'
  event_id: string | null
  label: string
  code: string | null
  stage: string
  summary: string
  since: number | null
  status: Handling
  hint: string | null
  next_attempt_at: number | null
  failures: number | null
  guide: Guide
}
export interface SourceRow {
  website_id: string
  source_id: string
  name: string
  enabled: boolean
  schedule: StatusNode
  fetch: StatusNode
  parse: StatusNode
  latest: StatusNode
  last_success_at: number | null
  next_attempt_at: number | null
  gap_at: number | null
}
export interface TargetRow {
  id: string
  name: string
  kind: string
  status: 'enabled' | 'paused' | 'unconfigured'
  queue: { pending: number; retry: number; earliest_at: number | null }
  sending: number
  expired_leases: number
  uncertain: number
  last: { result: string; code: string | null; at: number } | null
}
export interface HotlistSite {
  website_id: string
  name: string
  lists: (StatusNode & { period: string; period_label: string })[]
}
export interface ServiceRow {
  id: string
  name: string
  state: 'running' | 'stalled' | 'failed' | 'stopped_with' | 'unknown'
  last_loop_at: number | null
  stopped_with?: string | null
}
export interface OperationsStatus {
  checked_at: number
  runtime: { active: boolean; status: string; code: string | null }
  problems: Problem[]
  sources: SourceRow[]
  targets: TargetRow[]
  hotlists: HotlistSite[]
  services: ServiceRow[]
  alerts: { enabled: boolean; ready_targets: number }
}
export interface ProblemRow {
  id: string
  kind: 'source' | 'delivery' | 'runtime'
  label: string
  code: string | null
  summary: string
  status: 'ongoing' | 'recovered' | 'paused'
  started_at: number
  ended_at: number | null
  alerts: Record<string, number>
}
export interface ProblemPage {
  total: number
  page: number
  page_size: number
  items: ProblemRow[]
}
export interface ProblemDetail {
  id: string
  kind: 'source' | 'delivery' | 'runtime'
  label: string
  status: 'ongoing' | 'recovered' | 'paused'
  handling: Handling | null
  hint: string | null
  next_attempt_at: number | null
  first_code: string | null
  code: string | null
  started_at: number
  ended_at: number | null
  failures: number | null
  guide: Guide
  recent: { at: number; tone: Tone; label: string; text: string }[]
  alerts: {
    phase: 'fault' | 'recovery'
    target_name: string
    kind: string | null
    result: string
    error_code: string | null
    finished_at: number | null
  }[]
  verify: { kind: string; website_id?: string; target_id?: string } | null
  crash: {
    exception: string | null
    location: { file: string; function: string; line: number } | null
    version?: string
  } | null
}

export const handlingLabels: Record<Handling, string> = {
  auto_retry: '自动重试中',
  action: '需要处理',
  verifying: '等待验证',
}
export const handlingBadges: Record<Handling, string> = {
  auto_retry: 'amber',
  action: 'rose',
  verifying: 'neutral',
}
export const stageLabels: Record<string, string> = {
  fetch: '抓取',
  parse: '解析',
  send: '发送',
  config: '配置',
  service: '后台',
  unknown: '未知阶段',
}
export const attemptLabels: Record<string, string> = {
  success: '成功',
  transient_error: '暂时失败',
  permanent_error: '失败',
  unknown: '结果不确定',
  in_progress: '发送中',
}

export const stamp = (at: number | null | undefined) =>
  at ? formatTime(new Date(at * 1000).toISOString()) : '—'

export function clock(at: number) {
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: state.settings.timezone,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date(at * 1000))
  } catch {
    return new Date(at * 1000).toISOString().slice(11, 19) + ' UTC'
  }
}

export function elapsed(seconds: number) {
  if (seconds < 60) return '不到 1 分钟'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes + ' 分钟'
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return hours + ' 小时' + (minutes % 60 ? ' ' + (minutes % 60) + ' 分钟' : '')
  return Math.floor(hours / 24) + ' 天' + (hours % 24 ? ' ' + (hours % 24) + ' 小时' : '')
}

export function problemReason(problem: { stage: string; summary: string; code: string | null }) {
  const code = problem.code ? '（' + problem.code + '）' : ''
  return (stageLabels[problem.stage] || problem.stage) + '：' + problem.summary + code
}

export function alertSummary(results: Record<string, number>) {
  const count = (...keys: string[]) => keys.reduce((sum, key) => sum + (results[key] || 0), 0)
  if (!Object.keys(results).length) return '未发送'
  if (count('permanent_error', 'transient_error'))
    return '发送失败 ' + count('permanent_error', 'transient_error')
  if (count('unknown')) return '结果不确定'
  if (count('pending')) return '等待发送'
  if (count('success')) return '已发送 ' + count('success')
  return '已取消'
}
