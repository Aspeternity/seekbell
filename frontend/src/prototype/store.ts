import { reactive, ref, watch } from 'vue'
import { initialTasks, targets as seedTargets, historySamples, evaluate } from './model'
import type { Task, Sample, Truth } from './model'
import { createWebsite, websiteDefinition } from './websites'
import type { InstalledWebsite } from './websites'

export type Channel = 'telegram' | 'bark' | 'smtp' | 'webhook'
export type DeliveryStatus = 'success' | 'retrying' | 'failed' | 'unknown' | 'cancelled'
export interface Target {
  id: string
  name: string
  channel: Channel
  type: string
  icon: string
  color: string
  enabled: boolean
  configured: boolean
  summary: boolean
  summaryLimit: number
  group: string
  security: 'tls' | 'starttls' | 'plain'
  port: number
  responseMode: 'json_ok' | 'status'
  lastTest: string
}
export interface Post extends Sample {
  websiteId: string
  id: string
  time: string
  taskIds: string[]
  taskNames: string[]
  status: Truth
  reasons: string[]
  originalUrl: string | null
}
export interface Delivery {
  id: string
  postId: string | null
  title: string
  targetId: string
  targetName: string
  channel: Channel
  status: DeliveryStatus
  time: string
  attempts: number
  manual: boolean
  test: boolean
  reason: string
}
export interface DemoState {
  version: 3
  tasks: Task[]
  targets: Target[]
  posts: Post[]
  deliveries: Delivery[]
  websites: InstalledWebsite[]
  settings: { timezone: string; retention: number; alertTargets: string[]; recoveryAlerts: boolean }
}
export const channelMeta = {
  telegram: {
    type: 'Telegram Bot',
    icon: 'send',
    color: 'blue',
    description: '把新消息送到你的 Telegram 对话',
  },
  bark: { type: 'Bark', icon: 'phone', color: 'purple', description: '让 iPhone 第一时间告诉你' },
  smtp: { type: 'SMTP', icon: 'mail', color: 'orange', description: '通过你自己的邮件服务发送' },
  webhook: {
    type: 'Webhook',
    icon: 'code',
    color: 'green',
    description: '连接你的自动化与自托管服务',
  },
} as const
export const deliveryLabels: Record<DeliveryStatus, string> = {
  success: '成功',
  retrying: '等待重试',
  failed: '失败',
  unknown: '结果未知',
  cancelled: '已取消',
}
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))
export function newTarget(channel: Channel = 'telegram'): Target {
  return {
    id: '',
    name: '',
    channel,
    ...channelMeta[channel],
    enabled: true,
    configured: false,
    summary: false,
    summaryLimit: 300,
    group: 'SeekBell',
    security: 'tls',
    port: 465,
    responseMode: 'json_ok',
    lastTest: '',
  }
}
export function initialState(example = false): DemoState {
  const targetList = seedTargets.map((t) => ({
    ...newTarget(t.id as Channel),
    ...t,
    configured: true,
  }))
  const posts: Post[] = historySamples.map((sample, i) => {
    const matched = initialTasks.filter((t) => evaluate(t, sample).status === 'yes')
    return {
      ...clone(sample),
      websiteId: 'nodeseek',
      id: 'post-' + (i + 1),
      time: '2026-10-19T' + ['06:28:00', '05:45:00', '04:20:00', '06:12:00', '02:30:00'][i] + 'Z',
      taskIds: matched.map((t) => t.id),
      taskNames: matched.map((t) => t.name),
      status: matched.length ? 'yes' : i === 4 ? 'unknown' : 'no',
      reasons: matched.length
        ? ['满足任务关键词与范围，未发现排除词。']
        : i === 4
          ? ['摘要字段缺失，示例任务无法确定结果。']
          : ['标题包含排除词「求购」。'],
      originalUrl: null,
    }
  })
  posts.push({
    id: 'post-6',
    websiteId: 'nodeseek',
    title: '三条线路的晚高峰体验与测评记录',
    summary: '合成测试内容：记录不同线路的体验。',
    author: 'network_lab',
    category: '测评',
    time: '2026-10-19T05:54:00Z',
    status: 'yes',
    taskIds: ['network'],
    taskNames: ['网络与线路观察'],
    reasons: ['标题包含「线路」与「测评」，满足任意词条件。'],
    originalUrl: null,
  })
  const deliveries: Delivery[] = [
    {
      id: 'd-1',
      postId: 'post-1',
      title: posts[0]!.title,
      targetId: 'telegram',
      targetName: targetList[0]!.name,
      channel: 'telegram',
      status: 'success',
      time: '2026-10-19T06:28:02Z',
      attempts: 1,
      manual: false,
      test: false,
      reason: '模拟服务确认接收。',
    },
    {
      id: 'd-2',
      postId: 'post-1',
      title: posts[0]!.title,
      targetId: 'bark',
      targetName: targetList[1]!.name,
      channel: 'bark',
      status: 'success',
      time: '2026-10-19T06:28:03Z',
      attempts: 1,
      manual: false,
      test: false,
      reason: '模拟服务确认接收。',
    },
    {
      id: 'd-3',
      postId: 'post-6',
      title: posts[5]!.title,
      targetId: 'bark',
      targetName: targetList[1]!.name,
      channel: 'bark',
      status: 'retrying',
      time: '2026-10-19T05:54:02Z',
      attempts: 2,
      manual: false,
      test: false,
      reason: '模拟 503 服务不可用，等待有限重试。',
    },
    {
      id: 'd-4',
      postId: 'post-4',
      title: posts[3]!.title,
      targetId: 'webhook',
      targetName: targetList[3]!.name,
      channel: 'webhook',
      status: 'unknown',
      time: '2026-10-19T06:12:02Z',
      attempts: 1,
      manual: false,
      test: false,
      reason: '模拟响应超时，接收端可能已经收到。',
    },
    {
      id: 'd-5',
      postId: 'post-2',
      title: posts[1]!.title,
      targetId: 'smtp',
      targetName: targetList[2]!.name,
      channel: 'smtp',
      status: 'failed',
      time: '2026-10-19T05:45:02Z',
      attempts: 1,
      manual: false,
      test: false,
      reason: '模拟 SMTP 认证失败，请检查目标配置。',
    },
  ]
  return {
    version: 3,
    tasks: example ? clone(initialTasks) : [],
    targets: example ? targetList : [],
    posts: example ? posts : [],
    deliveries: example ? deliveries : [],
    websites: example
      ? [
          {
            ...createWebsite('nodeseek'),
            enabled: true,
            health: 'healthy',
            lastSuccess: '2026-10-19T06:29:56Z',
          },
        ]
      : [],
    settings: {
      timezone: 'Asia/Shanghai',
      retention: 30,
      alertTargets: example ? ['telegram'] : [],
      recoveryAlerts: true,
    },
  }
}
const isString = (v: unknown): v is string => typeof v === 'string' && v.length <= 5000
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.length <= 64 && v.every(isString)
export function isTask(v: unknown): v is Task {
  if (!v || typeof v !== 'object') return false
  const t = v as Task
  return (
    isString(t.id) &&
    isString(t.websiteId) &&
    isString(t.name) &&
    isString(t.description) &&
    typeof t.enabled === 'boolean' &&
    ['title', 'summary', 'title_summary'].includes(t.scope) &&
    Array.isArray(t.groups) &&
    t.groups.length <= 16 &&
    t.groups.every((g) => g && strings(g.all) && strings(g.any)) &&
    [t.exclude, t.categories, t.authorsInclude, t.authorsExclude, t.targets].every(strings) &&
    typeof t.caseSensitive === 'boolean' &&
    typeof t.wholeWord === 'boolean' &&
    Number.isFinite(t.hits) &&
    isString(t.lastHit) &&
    isString(t.icon) &&
    isString(t.color)
  )
}
export function isTarget(v: unknown): v is Target {
  if (!v || typeof v !== 'object') return false
  const t = v as Target
  return (
    isString(t.id) &&
    isString(t.name) &&
    Object.hasOwn(channelMeta, t.channel) &&
    typeof t.enabled === 'boolean' &&
    typeof t.configured === 'boolean' &&
    typeof t.summary === 'boolean' &&
    Number.isInteger(t.summaryLimit) &&
    t.summaryLimit >= 0 &&
    t.summaryLimit <= 1000 &&
    isString(t.group) &&
    ['tls', 'starttls', 'plain'].includes(t.security) &&
    Number.isInteger(t.port) &&
    t.port > 0 &&
    t.port <= 65535 &&
    ['json_ok', 'status'].includes(t.responseMode) &&
    isString(t.lastTest)
  )
}
const storageKey = 'seekbell-demo-v3'
const storageWarning = ref('')
// Version 2 represented one implicit NodeSeek source; preserve existing work on upgrade.
export function parseState(value: unknown): DemoState | null {
  if (!value || typeof value !== 'object') return null
  let data = value
  if ('version' in data && data.version === 2) {
    const old = data as Record<string, unknown>
    if (
      !old.source ||
      typeof old.source !== 'object' ||
      !Array.isArray(old.tasks) ||
      !Array.isArray(old.posts)
    )
      return null
    data = {
      ...old,
      version: 3,
      websites: [{ ...old.source, id: 'nodeseek', adapterId: 'nodeseek' }],
      tasks: old.tasks.map((t) => ({ ...t, websiteId: 'nodeseek' })),
      posts: old.posts.map((p) => ({ ...p, websiteId: 'nodeseek' })),
    }
  }
  return validState(data) ? cleanState(data) : null
}
function loadState(): DemoState {
  try {
    const raw = localStorage.getItem(storageKey) ?? localStorage.getItem('seekbell-demo-v2')
    if (raw) {
      const data = parseState(JSON.parse(raw))
      if (data) return data
      storageWarning.value = '演示存储格式不完整，已恢复默认空工作空间。'
    } else {
      const legacy: unknown = JSON.parse(localStorage.getItem('seekbell-ui-prototype-v1') || 'null')
      if (Array.isArray(legacy)) {
        const tasks = legacy.map((t) => ({ ...t, websiteId: 'nodeseek' }))
        if (tasks.every(isTask)) return { ...initialState(true), tasks }
      }
    }
  } catch {
    storageWarning.value = '无法读取浏览器存储，已加载空工作空间。'
  }
  return initialState()
}
function isWebsite(value: unknown): value is InstalledWebsite {
  if (!value || typeof value !== 'object') return false
  const w = value as InstalledWebsite
  return (
    isString(w.id) &&
    w.id === w.adapterId &&
    !!websiteDefinition(w.adapterId) &&
    typeof w.enabled === 'boolean' &&
    Number.isInteger(w.interval) &&
    w.interval >= 10 &&
    w.interval <= 3600 &&
    ['pending', 'healthy', 'error'].includes(w.health) &&
    [w.lastSuccess, w.lastTest].every(
      (v) => isString(v) && (v === '' || Number.isFinite(Date.parse(v))),
    )
  )
}
export function validState(data: unknown): data is DemoState {
  if (!data || typeof data !== 'object') return false
  const d = data as DemoState
  return (
    d.version === 3 &&
    Array.isArray(d.tasks) &&
    d.tasks.length <= 200 &&
    d.tasks.every(isTask) &&
    Array.isArray(d.targets) &&
    d.targets.length <= 100 &&
    d.targets.every(isTarget) &&
    new Set(d.tasks.map((t) => t.id)).size === d.tasks.length &&
    new Set(d.targets.map((t) => t.id)).size === d.targets.length &&
    d.tasks.every((t) => t.targets.every((id) => d.targets.some((target) => target.id === id))) &&
    Array.isArray(d.websites) &&
    d.websites.length <= 100 &&
    d.websites.every(isWebsite) &&
    new Set(d.websites.map((w) => w.id)).size === d.websites.length &&
    d.tasks.every((t) => d.websites.some((w) => w.id === t.websiteId)) &&
    !!d.settings &&
    ['Asia/Shanghai', 'UTC', 'Asia/Tokyo', 'America/Los_Angeles'].includes(d.settings.timezone) &&
    Number.isInteger(d.settings.retention) &&
    d.settings.retention >= 1 &&
    d.settings.retention <= 365 &&
    strings(d.settings.alertTargets) &&
    d.settings.alertTargets.every((id) => d.targets.some((t) => t.id === id)) &&
    typeof d.settings.recoveryAlerts === 'boolean' &&
    Array.isArray(d.posts) &&
    d.posts.length <= 1000 &&
    d.posts.every(
      (p) =>
        p &&
        isString(p.id) &&
        isString(p.websiteId) &&
        isString(p.title) &&
        (p.summary === null || isString(p.summary)) &&
        (p.author === null || isString(p.author)) &&
        (p.category === null || isString(p.category)) &&
        isString(p.time) &&
        Number.isFinite(Date.parse(p.time)) &&
        ['yes', 'no', 'unknown'].includes(p.status) &&
        strings(p.taskIds) &&
        strings(p.taskNames) &&
        strings(p.reasons) &&
        p.originalUrl === null,
    ) &&
    Array.isArray(d.deliveries) &&
    d.deliveries.length <= 2000 &&
    d.deliveries.every(
      (r) =>
        r &&
        isString(r.id) &&
        (r.postId === null || isString(r.postId)) &&
        isString(r.title) &&
        isString(r.targetId) &&
        isString(r.targetName) &&
        Object.hasOwn(channelMeta, r.channel) &&
        Object.hasOwn(deliveryLabels, r.status) &&
        isString(r.time) &&
        Number.isFinite(Date.parse(r.time)) &&
        Number.isInteger(r.attempts) &&
        r.attempts >= 1 &&
        typeof r.manual === 'boolean' &&
        typeof r.test === 'boolean' &&
        isString(r.reason),
    )
  )
}
// Whitelist fields when importing; never carry unknown credential fields into storage.
export function cleanState(d: DemoState): DemoState {
  return {
    version: 3,
    tasks: d.tasks.map((t) => ({
      id: t.id,
      websiteId: t.websiteId,
      name: t.name,
      description: t.description,
      enabled: t.enabled,
      scope: t.scope,
      groups: t.groups.map((g) => ({ all: [...g.all], any: [...g.any] })),
      exclude: [...t.exclude],
      categories: [...t.categories],
      authorsInclude: [...t.authorsInclude],
      authorsExclude: [...t.authorsExclude],
      caseSensitive: t.caseSensitive,
      wholeWord: t.wholeWord,
      targets: [...t.targets],
      hits: t.hits,
      lastHit: t.lastHit,
      icon: t.icon,
      color: t.color,
    })),
    targets: d.targets.map((t) => ({
      id: t.id,
      name: t.name,
      channel: t.channel,
      ...channelMeta[t.channel],
      enabled: t.enabled,
      configured: t.configured,
      summary: t.summary,
      summaryLimit: t.summaryLimit,
      group: t.group,
      security: t.security,
      port: t.port,
      responseMode: t.responseMode,
      lastTest: t.lastTest,
    })),
    websites: d.websites.map((w) => ({
      id: w.id,
      adapterId: w.adapterId,
      enabled: w.enabled,
      interval: w.interval,
      health: w.health,
      lastSuccess: w.lastSuccess,
      lastTest: w.lastTest,
    })),
    settings: {
      timezone: d.settings.timezone,
      retention: d.settings.retention,
      alertTargets: [...d.settings.alertTargets],
      recoveryAlerts: d.settings.recoveryAlerts,
    },
    posts: d.posts.map((p) => ({
      id: p.id,
      websiteId: p.websiteId,
      title: p.title,
      summary: p.summary,
      author: p.author,
      category: p.category,
      time: p.time,
      taskIds: [...p.taskIds],
      taskNames: [...p.taskNames],
      status: p.status,
      reasons: [...p.reasons],
      originalUrl: null,
    })),
    deliveries: d.deliveries.map((r) => ({
      id: r.id,
      postId: r.postId,
      title: r.title,
      targetId: r.targetId,
      targetName: r.targetName,
      channel: r.channel,
      status: r.status,
      time: r.time,
      attempts: r.attempts,
      manual: r.manual,
      test: r.test,
      reason: r.reason,
    })),
  }
}
export const state = reactive<DemoState>(loadState())
export function websiteName(id: string) {
  return (
    websiteDefinition(state.websites.find((w) => w.id === id)?.adapterId || id)?.name || '未知网站'
  )
}
export function loadExampleWorkspace() {
  confirmAction(
    '载入示例工作台？',
    '用一组 NodeSeek 合成数据替换当前工作空间，便于体验全部页面。不会连接网站或发送通知。管理员账号保持不变。',
    () => {
      Object.assign(state, initialState(true))
      notify('示例工作台已载入。所有数据均为模拟。')
    },
    '确认载入',
  )
}
export function addWebsite(adapterId: string) {
  if (state.websites.some((w) => w.adapterId === adapterId)) return null
  const website = createWebsite(adapterId)
  state.websites.push(website)
  notify(websiteName(website.id) + ' 已添加，可按需启用并创建任务。')
  return website
}
export function removeWebsite(id: string) {
  if (state.tasks.some((t) => t.websiteId === id)) {
    notify('请先移除该网站关联的监控任务。')
    return false
  }
  state.websites = state.websites.filter((w) => w.id !== id)
  state.deliveries
    .filter(
      (r) =>
        r.status === 'retrying' && state.posts.some((p) => p.id === r.postId && p.websiteId === id),
    )
    .forEach((r) => {
      r.status = 'cancelled'
      r.reason = '网站已移除，待重试记录已取消。'
    })
  notify('网站已移除，已有内容与投递历史保留。')
  return true
}

export const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
export function notify(message: string) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 6000)
}
watch(
  state,
  () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(cleanState(state)))
    } catch {
      notify('浏览器无法保存演示数据；修改仅保留在当前页面。')
    }
  },
  { deep: true, flush: 'sync' },
)
if (storageWarning.value) notify(storageWarning.value)
export function formatTime(value: string) {
  return value
    ? new Intl.DateTimeFormat('zh-CN', {
        timeZone: state.settings.timezone,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(value))
    : '尚未测试'
}
export function setTaskEnabled(task: Task, value: boolean) {
  task.enabled = value
  notify(value ? '任务已恢复；不补发暂停期间的帖子。' : '任务已暂停；历史命中仍保留。')
}
export function saveTask(task: Task) {
  if (!state.websites.some((w) => w.id === task.websiteId)) {
    notify('请先添加并选择监控网站。')
    return
  }
  const copy = clone(task)
  copy.name = copy.name.trim()
  copy.groups = copy.groups.filter((g) => g.all.length || g.any.length)
  if (!copy.id) {
    copy.id = 'task-' + crypto.randomUUID()
    state.tasks.push(copy)
  } else {
    const i = state.tasks.findIndex((t) => t.id === copy.id)
    if (i >= 0) state.tasks[i] = copy
  }
  notify('任务已保存到此浏览器。原型不会采集或发送通知。')
}
export function cancelTargetRetries(id: string) {
  state.deliveries
    .filter((r) => r.targetId === id && r.status === 'retrying')
    .forEach((r) => {
      r.status = 'cancelled'
      r.reason = '目标已暂停或删除，尚未发送的模拟重试已取消。'
    })
}
export function setTargetEnabled(target: Target, value: boolean) {
  target.enabled = value
  if (!value) cancelTargetRetries(target.id)
  notify(
    value ? '目标已恢复，不自动发送暂停期间积压的通知。' : '目标已暂停，对应待重试记录已取消。',
  )
}
export function saveTarget(target: Target) {
  const copy = clone(target)
  copy.name = copy.name.trim()
  if (!copy.id) {
    copy.id = 'target-' + crypto.randomUUID()
    state.targets.push(copy)
  } else {
    const i = state.targets.findIndex((t) => t.id === copy.id)
    if (i >= 0) state.targets[i] = copy
  }
  if (!copy.enabled) cancelTargetRetries(copy.id)
  notify('通知目标已保存；输入的地址与凭据不会保存在原型中。')
}
export function testTarget(target: Target, status: DeliveryStatus) {
  const record: Delivery = {
    id: crypto.randomUUID(),
    postId: null,
    title: 'SeekBell 目标测试',
    targetId: target.id,
    targetName: target.name,
    channel: target.channel,
    status,
    time: new Date().toISOString(),
    attempts: 1,
    manual: false,
    test: true,
    reason:
      status === 'success'
        ? target.channel === 'smtp'
          ? '模拟 SMTP 服务器接受；不保证进入收件箱。'
          : '模拟接收成功；没有发出网络请求。'
        : status === 'unknown'
          ? '模拟超时：无法确认是否接收，不自动重试。'
          : '模拟服务拒绝；测试记录独立，不自动重试。',
  }
  state.deliveries.unshift(record)
  target.lastTest = record.time
  notify('模拟测试完成：' + deliveryLabels[status])
}
export function resend(record: Delivery) {
  const target = state.targets.find((t) => t.id === record.targetId)
  if (!target?.enabled) {
    notify('请先启用对应通知目标。')
    return
  }
  state.deliveries.unshift({
    ...clone(record),
    id: crypto.randomUUID(),
    time: new Date().toISOString(),
    status: 'success',
    attempts: 1,
    manual: true,
    test: false,
    reason: '手动重发演示完成；只处理此目标，保留原始投递记录。',
  })
  notify('已生成独立的手动重发记录；未发送真实消息。')
}
export function downloadConfig() {
  const data = cleanState(state)
  const blob = new Blob(
    [
      JSON.stringify(
        { kind: 'seekbell-demo-backup', exportedAt: new Date().toISOString(), data },
        null,
        2,
      ),
    ],
    { type: 'application/json' },
  )
  const url = URL.createObjectURL(blob),
    a = document.createElement('a')
  a.href = url
  a.download = 'seekbell-demo-backup.json'
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  notify('已导出演示备份，不含账号密码、服务地址或通知凭据。')
}
export function restoreState(data: DemoState) {
  Object.assign(state, cleanState(data))
  notify('演示数据已恢复，仅影响当前浏览器。')
}
export function resetState() {
  Object.assign(state, initialState())
  notify('演示数据已重置。')
}

interface DemoAccount {
  username: string
  created: boolean
  salt: string
  digest: string
}
function loadAccount(): DemoAccount {
  try {
    const a = JSON.parse(localStorage.getItem('seekbell-demo-account-v2') || 'null')
    if (
      a &&
      isString(a.username) &&
      typeof a.created === 'boolean' &&
      isString(a.salt) &&
      isString(a.digest)
    )
      return a
  } catch {
    /* Demo fallback */
  }
  return { username: 'admin', created: false, salt: '', digest: '' }
}
export const account = reactive<DemoAccount>(loadAccount())
function initialSession() {
  try {
    return sessionStorage.getItem('seekbell-demo-signed-in') !== 'false'
  } catch {
    return true
  }
}
export const signedIn = ref(initialSession())
export function setSession(value: boolean) {
  signedIn.value = value
  try {
    sessionStorage.setItem('seekbell-demo-signed-in', String(value))
  } catch {
    /* Browser-only fallback */
  }
}
async function digest(password: string, salt: string) {
  const result = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(salt + password))
  return [...new Uint8Array(result)].map((b) => b.toString(16).padStart(2, '0')).join('')
}
export async function verifyPassword(password: string) {
  return account.created
    ? (await digest(password, account.salt)) === account.digest
    : password === 'SeekBell2026!'
}
export async function updateAccount(username: string, password?: string) {
  account.username = username
  if (password) {
    account.salt = crypto.randomUUID()
    account.digest = await digest(password, account.salt)
    account.created = true
  }
  try {
    localStorage.setItem('seekbell-demo-account-v2', JSON.stringify(account))
  } catch {
    notify('浏览器无法持久化演示账号。')
  }
}
export function resetAccount() {
  Object.assign(account, { username: 'admin', created: false, salt: '', digest: '' })
  try {
    localStorage.removeItem('seekbell-demo-account-v2')
  } catch {
    /* Demo fallback */
  }
  setSession(false)
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
