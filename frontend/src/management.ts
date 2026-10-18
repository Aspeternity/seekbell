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
