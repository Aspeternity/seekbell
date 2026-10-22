import { reactive, ref } from 'vue'
import { clearReadCache } from './readCache'
import { clearNotificationCounts, invalidateNotificationCounts } from './notificationCounts'
import type {
  TelegramPreviewMessage,
  NotificationPreviewOptions,
} from '../prototype/notificationPreview'
import type { Task, Sample } from '../prototype/model'
import { emptyTask } from '../prototype/model'
import { createWebsite, websiteDefinition } from '../prototype/websites'
import type { InstalledWebsite } from '../prototype/websites'
import type { ConnectionCheck, DemoState, Target } from '../prototype/shared'
import { channelMeta, clone, newTarget } from '../prototype/shared'
export * from '../prototype/shared'
export const isLive = true
const empty = (): DemoState => ({
  version: 3,
  tasks: [],
  targets: [],
  websites: [],
  posts: [],
  deliveries: [],
  settings: {
    workspaceName: '个人工作空间',
    workspaceDescription: 'Administrator',
    timezone: 'Asia/Shanghai',
    retention: 30,
    alertTargets: [],
    recoveryAlerts: false,
  },
})
export const state = reactive<DemoState>(empty())
export const account = reactive({ username: '', created: false })
export const runtime = reactive<{ active: boolean; status: string; code: string | null }>({
  active: false,
  status: 'starting',
  code: null,
})
export const signedIn = ref(false)
export const toast = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
export function notify(message: string) {
  toast.value = message
  clearTimeout(timer)
  timer = setTimeout(() => (toast.value = ''), 6000)
}
let csrf = ''
export async function request<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await sendRequest(
    path,
    method,
    body === undefined ? undefined : JSON.stringify(body),
    'application/json',
  )
  return response.json()
}
export async function sendRequest(
  path: string,
  method: string,
  body?: BodyInit,
  contentType = 'application/octet-stream',
): Promise<Response> {
  const response = await fetch('/api/' + path, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': contentType }),
      ...(method === 'GET' ? {} : { 'X-CSRF-Token': csrf }),
    },
    ...(body === undefined ? {} : { body }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: '服务响应无效，请稍后重试。' }))
    if (
      response.status === 401 &&
      (path.startsWith('manage/') || path === 'auth/administrator' || path === 'auth/logout')
    ) {
      clearReadCache()
      clearNotificationCounts()
      signedIn.value = false
      Object.assign(state, empty())
      window.dispatchEvent(new Event('seekbell-session-expired'))
    }
    throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请检查配置后重试。')
  }
  if (method !== 'GET' && path !== 'auth/logout') {
    clearReadCache()
    invalidateNotificationCounts()
  }
  return response
}
function applyAuth(info: any) {
  account.created = info.initialized
  account.username = info.username || ''
  signedIn.value = info.authenticated
  csrf = info.csrf
}
export async function initialize() {
  applyAuth(await request('auth/status'))
  if (signedIn.value) await refresh()
}
export async function authenticate(setup: boolean, username: string, password: string) {
  applyAuth(await request('auth/status'))
  if (signedIn.value) {
    await refresh()
    return
  }
  const info = await request(setup ? 'auth/setup' : 'auth/login', 'POST', {
    username,
    password,
    ...(setup ? { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } : {}),
  })
  applyAuth(info)
  await refresh()
}
export async function saveAdministrator(
  username: string,
  currentPassword: string,
  newPassword: string,
) {
  const info = await request('auth/administrator', 'PUT', {
    username,
    current_password: currentPassword,
    ...(newPassword ? { new_password: newPassword } : {}),
  })
  applyAuth(info)
}
export async function setSession(value: boolean) {
  if (value) return
  if (signedIn.value) await request('auth/logout', 'POST')
  clearReadCache()
  clearNotificationCounts()
  signedIn.value = false
  Object.assign(state, empty())
  applyAuth(await request('auth/status'))
}
export function websiteName(id: string) {
  return websiteDefinition(id)?.name || '未知网站'
}
function rule(task: Task) {
  return {
    scope: task.scope,
    groups: task.groups.map((g) => ({ all_of: g.all, any_of: g.any })),
    exclude: task.exclude,
    categories: task.categories,
    authors_include: task.authorsInclude,
    authors_exclude: task.authorsExclude,
    case_sensitive: task.caseSensitive,
    mode: task.wholeWord ? 'english_word' : 'contains',
  }
}
function taskBody(task: Task) {
  return {
    name: task.name,
    description: task.description,
    website_id: task.websiteId,
    enabled: task.enabled,
    rule: rule(task),
    target_ids: task.targets,
  }
}
export async function refreshRuntime() {
  Object.assign(runtime, await request('manage/runtime'))
}
export async function refresh() {
  const data = await request('manage/workspace')
  state.websites = data.websites.map((w: any) => ({
    ...createWebsite(w.adapterId),
    ...w,
    lastSuccess: w.lastSuccess ? new Date(w.lastSuccess * 1000).toISOString() : '',
  }))
  state.tasks = data.tasks.map((t: any) => ({
    ...emptyTask(),
    id: t.id,
    websiteId: t.website_id,
    name: t.name,
    description: t.description,
    enabled: t.enabled,
    scope: t.rule.scope,
    groups: t.rule.groups.map((g: any) => ({ all: g.all_of, any: g.any_of })),
    exclude: t.rule.exclude,
    categories: t.rule.categories,
    authorsInclude: t.rule.authors_include,
    authorsExclude: t.rule.authors_exclude,
    caseSensitive: t.rule.case_sensitive,
    wholeWord: t.rule.mode === 'english_word',
    targets: t.target_ids,
  }))
  state.targets = data.targets.map((t: any) => ({
    ...newTarget(t.kind),
    ...channelMeta[t.kind as keyof typeof channelMeta],
    id: t.id,
    name: t.name,
    channel: t.kind,
    enabled: t.enabled,
    configured: true,
    summary: t.config.include_summary,
    summaryLimit: t.config.summary_limit,
    group: t.config.group || 'SeekBell',
    security: t.config.security || 'tls',
    port: t.config.port || 465,
    responseMode: t.config.response_mode || 'json_ok',
  }))
  Object.assign(state.settings, data.settings)
  Object.assign(runtime, data.runtime)
}
export async function addWebsite(id: string) {
  await request('manage/websites', 'POST', { adapter_id: id })
  await refresh()
  notify('网站已保存到服务端。')
  return state.websites.find((w) => w.id === id)
}
export async function saveWebsite(
  website: InstalledWebsite,
  interval: number,
  enabled = website.enabled,
) {
  await request('manage/websites/' + website.id, 'PUT', { interval, enabled })
  await refresh()
  notify(
    runtime.active
      ? '网站配置已保存，后台将按启停状态采集。'
      : '配置已保存；后台未运行，请检查概览。',
  )
}
export async function removeWebsite(id: string) {
  await request('manage/websites/' + id, 'DELETE')
  await refresh()
  notify('网站已移除，历史身份与记录保留。')
  return true
}
export async function saveTask(task: Task) {
  const result = await request(
    'manage/tasks' + (task.id ? '/' + task.id : ''),
    task.id ? 'PUT' : 'POST',
    taskBody(task),
  )
  await refresh()
  notify('任务已保存，将对之后首次发现的帖子生效。')
  return result
}
export async function setTaskEnabled(task: Task, value: boolean) {
  if (value && !task.targets.length) {
    notify('请先为任务选择通知目标。')
    return
  }
  try {
    await saveTask({ ...clone(task), enabled: value })
  } catch (error) {
    notify((error as Error).message)
  }
}
export async function removeTask(task: Task) {
  await request('manage/tasks/' + task.id, 'DELETE')
  await refresh()
  notify('任务已删除，历史保留。')
}
export async function saveTarget(target: Target, config: Record<string, unknown> = {}) {
  await request('manage/targets' + (target.id ? '/' + target.id : ''), target.id ? 'PUT' : 'POST', {
    name: target.name,
    kind: target.channel,
    enabled: target.enabled,
    config,
  })
  await refresh()
  notify('通知配置已加密保存；没有发送消息。')
}
export async function setTargetEnabled(target: Target, value: boolean) {
  try {
    await saveTarget({ ...clone(target), enabled: value })
  } catch (error) {
    notify((error as Error).message)
  }
}
export async function getTargetDeletePreview(id: string) {
  return request<import('../prototype/targetDeletion').TargetDeletePreview>(
    'manage/targets/' + id + '/delete-preview',
  )
}
export async function removeTarget(target: Target, confirmation: string) {
  await request('manage/targets/' + target.id, 'DELETE', { confirmation })
  await refresh()
  notify('目标已删除，历史记录保留。')
}
export async function getWebsiteTest(id: string) {
  return request<ConnectionCheck | null>('manage/websites/' + id + '/connection-test')
}
export async function testWebsite(id: string) {
  return request<ConnectionCheck>('manage/websites/' + id + '/connection-test', 'POST', {})
}
export async function trialHistory(task: Task, limit: number) {
  const data = await request('manage/rules/history', 'POST', {
    website_id: task.websiteId,
    rule: rule(task),
    limit,
  })
  return {
    available: data.available as number,
    sampleCount: data.sample_count as number,
    fromAt: data.from_at ? new Date(data.from_at * 1000).toISOString() : '',
    toAt: data.to_at ? new Date(data.to_at * 1000).toISOString() : '',
    items: data.items.map((item: any) => ({
      sample: item.sample as Sample,
      result: matchResult(item.result),
    })),
  }
}
function matchResult(data: any) {
  return {
    status: ({ match: 'yes', no_match: 'no', insufficient_data: 'unknown' } as const)[
      data.status as 'match' | 'no_match' | 'insufficient_data'
    ],
    reasons: [
      ...data.reasons.map((reason: any) => {
        const truth: Record<string, string> = { true: '满足', false: '不满足', unknown: '字段缺失' }
        return (
          [reason.group ? '条件组 ' + reason.group : '', reason.code, reason.term]
            .filter(Boolean)
            .join('：') +
          '（' +
          (truth[reason.truth] || reason.truth) +
          '）'
        )
      }),
      ...(data.warnings?.includes('all_new_posts') ? ['未设置筛选条件，匹配全部帖子。'] : []),
    ] as string[],
  }
}
export async function savePreferences(settings: DemoState['settings']) {
  await request('manage/workspace', 'PUT', {
    name: settings.workspaceName,
    description: settings.workspaceDescription,
  })
  await refresh()
}
export async function evaluateTask(task: Task, sample: Sample) {
  const data = await request('manage/rules/evaluate', 'POST', { rule: rule(task), post: sample })
  return matchResult(data)
}
export function formatTime(value: string) {
  if (!value) return '尚未记录'
  const format = (timeZone: string) =>
    new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(value))
  try {
    return format(state.settings.timezone)
  } catch {
    return format('UTC') + ' UTC'
  }
}
export const confirmation = ref<{
  title: string
  body: string
  label: string
  cancelLabel: string
  run: () => void
} | null>(null)
export function confirmAction(
  title: string,
  body: string,
  run: () => void,
  label = '确认',
  cancelLabel = '取消',
) {
  confirmation.value = { title, body, run, label, cancelLabel }
}
const unavailable = () => {
  notify('此功能将在后续阶段接入。')
}
export const loadExampleWorkspace = unavailable,
  testTarget = unavailable,
  resend = unavailable,
  cancelTargetRetries = unavailable,
  downloadConfig = unavailable,
  restoreState = unavailable,
  resetState = unavailable,
  resetAccount = unavailable,
  updateAccount = unavailable
export const parseState = () => null,
  verifyPassword = async () => false

export async function getTaskStatistics() {
  const data = await request<import('./overview').OverviewData>('manage/overview?range=24h')
  return data.tasks.map((row) => ({
    id: row.id,
    hits: row.matches,
    lastHit:
      row.last_match_at === null
        ? '尚未记录'
        : formatTime(new Date(row.last_match_at * 1000).toISOString()),
  }))
}

export function loadTelegramPreview(options: NotificationPreviewOptions) {
  const params = new URLSearchParams({
    include_summary: String(options.include_summary),
    summary_limit: String(options.summary_limit),
  })
  return request<TelegramPreviewMessage>('manage/notification-preview/telegram?' + params)
}
