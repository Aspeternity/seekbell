import { request } from './api'

export type Channel = 'telegram' | 'bark' | 'smtp' | 'webhook'
export interface FieldSchema {
  type?: string
  anyOf?: FieldSchema[]
  enum?: string[]
  default?: unknown
  writeOnly?: boolean
  minimum?: number
  maximum?: number
  maxLength?: number
}
export interface ChannelSchema {
  properties: Record<string, FieldSchema>
  required?: string[]
}
export type Schemas = Record<Channel, ChannelSchema>
export interface Target {
  id: string
  name: string
  kind: Channel
  enabled: boolean
  revision: number
  config: Record<string, unknown>
  configured_secrets: string[]
  duplicate_ids?: string[]
}
export interface Rule {
  scope: 'title' | 'summary' | 'title_summary'
  groups: { all_of: string[]; any_of: string[] }[]
  exclude: string[]
  authors_include: string[]
  authors_exclude: string[]
  categories: string[]
  case_sensitive: boolean
  mode: 'contains' | 'english_word'
}
export interface MonitorTask {
  id: string
  name: string
  enabled: boolean
  website_id: 'nodeseek'
  version: number
  rule: Rule
  target_ids: string[]
  explanation: string
}
export interface MatchResult {
  status: 'match' | 'no_match' | 'insufficient_data'
  reasons: { code: string; truth: string; group: number | null; term: string | null }[]
  warnings: string[]
}
export interface Preview {
  rule: Rule
  explanation: string
  result: MatchResult | null
  warnings: string[]
}
export interface HistoryPreview {
  total: number
  sample_count: number
  oldest_at: number | null
  newest_at: number | null
  explanation: string
  items: {
    external_post_id: string
    title: string
    first_seen_at: number
    url: string | null
    result: MatchResult
  }[]
}
export const channelNames: Record<Channel, string> = {
  telegram: 'Telegram Bot',
  bark: 'Bark',
  smtp: '邮件 SMTP',
  webhook: 'Webhook',
}
export const fieldLabels: Record<string, string> = {
  base_url: '服务地址',
  bot_token: 'Bot 令牌',
  chat_id: '聊天 ID',
  message_thread_id: '话题 ID',
  device_key: '设备密钥',
  group: '分组名称',
  url: 'Webhook 地址',
  headers: '自定义请求头（JSON）',
  response_mode: '成功响应方式',
  host: '邮件服务器',
  port: '端口',
  security: '连接安全',
  allow_insecure: '允许明文 SMTP',
  username: 'SMTP 用户名',
  password: 'SMTP 密码',
  from_address: '发件地址',
  to_address: '收件地址',
  include_summary: '包含摘要',
  summary_limit: '摘要字符上限',
}
export const matchLabels = {
  match: '命中',
  no_match: '不命中',
  insufficient_data: '信息不足',
}
export function reasonText(result: MatchResult): string {
  const codes: Record<string, string> = {
    all_of: '全部包含',
    any_of: '至少包含一个',
    exclude: '排除词',
    author_include: '包含作者',
    author_exclude: '排除作者',
    category: '版块',
    missing_summary: '摘要缺失',
    missing_author: '作者缺失',
    missing_category: '版块缺失',
  }
  const truths: Record<string, string> = { true: '成立', false: '不成立', unknown: '未知' }
  return (
    result.reasons
      .map(
        (r) =>
          `${r.group ? `组 ${r.group} · ` : ''}${codes[r.code] ?? r.code}${r.term ? `「${r.term}」` : ''}：${truths[r.truth] ?? r.truth}`,
      )
      .join('；') || '没有限制条件，匹配全部新帖。'
  )
}
export function freshRule(): Rule {
  return {
    scope: 'title',
    groups: [],
    exclude: [],
    authors_include: [],
    authors_exclude: [],
    categories: [],
    case_sensitive: false,
    mode: 'contains',
  }
}
export function message(cause: unknown): string {
  return cause instanceof Error ? cause.message : '操作失败，请稍后重试。'
}
export function getTargets(): Promise<Target[]> {
  return request('/api/manage/targets')
}
export function getTarget(id: string): Promise<Target> {
  return request('/api/manage/targets/' + id)
}
export function getTask(id: string): Promise<MonitorTask> {
  return request('/api/manage/tasks/' + id)
}

export function getSchemas(): Promise<Schemas> {
  return request('/api/manage/channels')
}
export function getTasks(): Promise<MonitorTask[]> {
  return request('/api/manage/tasks')
}

export function write<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body: unknown,
  csrf: string,
): Promise<T> {
  return request('/api/manage' + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

export interface SchedulerState {
  enabled: boolean
  healthy: boolean
  stopping: boolean
  components: Record<string, string>
}
export interface SiteState {
  website_id: string
  name: string
  enabled: boolean
  revision: number
  interval_seconds: number
  url: string
  configuration_valid: boolean
  capabilities: string[]
  initialized: boolean
  needs_baseline: boolean
  last_attempt_at: number | null
  last_success_at: number | null
  last_error_code: string | null
  failures: number
  next_attempt_at: number
  window_count: number
  possible_gap: boolean
  last_gap_at: number | null
  scheduler: SchedulerState
}
export interface Overview {
  site: Omit<SiteState, 'scheduler'>
  scheduler: SchedulerState
  counts: {
    tasks: number
    enabled_tasks: number
    targets: number
    posts: number
    hits: number
    deliveries: Record<string, number>
    uncertain: number
  }
}
export interface ProbeResult {
  status: 'success' | 'failure' | 'backoff'
  code: string | null
  at: number
  next_attempt_at?: number
  raw_count?: number
  valid_count?: number
  diagnostics?: string[]
}
export interface ContentItem {
  external_post_id: string
  title: string
  summary: string | null
  author: string | null
  category: string | null
  url: string | null
  display_truncated: boolean
  first_seen_at: number
  published_at: number | null
  hits: {
    task_id: string
    name: string
    version: number
    deleted: boolean
    matched_at: number
    reason: MatchResult
  }[]
}
export interface ContentPage {
  total: number
  offset: number
  limit: number
  items: ContentItem[]
}
export interface HistoricalTask {
  id: string
  name: string
  deleted: boolean
}
export function getSite(): Promise<SiteState> {
  return request('/api/manage/site')
}
export function getOverview(): Promise<Overview> {
  return request('/api/manage/overview')
}
export function getContent(params: URLSearchParams): Promise<ContentPage> {
  return request('/api/manage/content?' + params.toString())
}
export function getHistoricalTasks(): Promise<HistoricalTask[]> {
  return request('/api/manage/content/options')
}
export function localDate(value: number | null | undefined): string {
  return value == null || value === 0 ? '尚无记录' : new Date(value * 1000).toLocaleString()
}
export function sourceError(code: string | null): string {
  if (!code) return '无'
  if (/^http_[0-9]+$/.test(code)) return 'HTTP ' + code.slice(5)
  const labels: Record<string, string> = {
    timeout: '请求超时',
    transport_error: '连接失败',
    invalid_or_unsafe_xml: 'XML 无效或不安全',
    unexpected_content_type: '响应不是 RSS/XML',
    unsupported_content_encoding: '响应编码不受支持',
    response_too_large: '响应超过大小限制',
    unsupported_source: '来源配置不匹配',
    not_rss: '响应不是 RSS',
    feed_parse_error: 'RSS 解析失败',
    no_valid_entries: '没有合法条目',
  }
  return labels[code] ?? code
}

export type DeliveryKind = 'automatic' | 'manual' | 'test'
export interface ExplicitResult {
  id: string
  result: string
  code: string | null
  started_at: number
  finished_at: number | null
}
export interface DeliveryRecord {
  id: string
  kind: DeliveryKind
  target_id: string
  target_name: string
  channel: Channel
  target_revision: number
  status: string
  result: string | null
  code: string | null
  uncertain: boolean
  started_at: number
  finished_at: number | null
  attempt_count: number
  next_attempt_at: number | null
  lease_until: number | null
  original_event_id: string | null
  title: string
  url: string | null
}
export interface DeliveryDetail extends DeliveryRecord {
  current_target: Pick<Target, 'id' | 'name' | 'kind' | 'revision' | 'enabled'>
  matched_tasks: { id: string; version: number; name: string }[]
  attempts: {
    sequence: number
    started_at: number
    finished_at: number | null
    result: string
    code: string | null
    late_result: string | null
    late_finished_at: number | null
  }[]
}
export interface DeliveryPage {
  items: DeliveryRecord[]
  total: number
  offset: number
  limit: number
}
export function getDeliveries(params: URLSearchParams): Promise<DeliveryPage> {
  return request('/api/manage/deliveries?' + params.toString())
}
export function getDelivery(id: string, kind: DeliveryKind): Promise<DeliveryDetail> {
  return request('/api/manage/deliveries/' + id + '?kind=' + kind)
}
export function deliveryStatus(value: string | null): string {
  const labels: Record<string, string> = {
    pending: '等待发送',
    retry: '等待自动重试',
    leased: '发送在途',
    sent: '渠道接受',
    failed: '最终失败',
    cancelled: '已取消',
    in_progress: '进行中',
    success: '渠道接受',
    transient_error: '临时失败',
    permanent_error: '永久失败',
    unknown: '结果未知',
  }
  return value ? (labels[value] ?? value) : '尚无结果'
}
export function explicitResultText(value: ExplicitResult): string {
  return (
    deliveryStatus(value.result) +
    (value.code ? '（' + value.code + '）' : '') +
    (value.result === 'unknown'
      ? '。请检查记录和接收端，再次发送可能重复。'
      : '。成功仅代表渠道接受，不代表已阅读。')
  )
}
export function newRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 15) | 64
  bytes[8] = (bytes[8]! & 63) | 128
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-')
}
