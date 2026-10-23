import { onBeforeUnmount, shallowRef, ref, watch } from 'vue'
import { request } from './store'
import {
  cachedRead,
  readCacheRevision,
  readSessionRevision,
  readIsFresh,
  rememberRead,
  fetchRead,
} from './readCache'
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export type PostStatus = 'match' | 'no_match' | 'insufficient_data' | 'not_evaluated' | 'unrecorded'
export interface PostRecord {
  id: string
  website_id: string
  external_post_id: string
  title: string
  summary: string | null
  author: string | null
  category: string | null
  category_label: string | null
  first_seen_at: number
  published_at: number | null
  original_url: string | null
  status: PostStatus
  baseline: boolean | null
  hits: { task_id: string; version: number; name: string; deleted: boolean }[]
}
export interface Reason {
  code: string
  truth: 'true' | 'false' | 'unknown'
  term: string | null
  group: number | null
}
export interface Evaluation {
  task_id: string
  version: number
  name: string
  deleted: boolean
  at: number
  result: { status: PostStatus; reasons: Reason[] }
}
export interface EvaluationPage extends Page<Evaluation> {
  matched_total: number
  other_total: number
}
export interface PostPage extends Page<PostRecord> {
  summary: Partial<Record<PostStatus, number>>
}
export type DeliveryStatus = 'pending' | 'retry' | 'leased' | 'sent' | 'failed' | 'cancelled'
export interface DeliveryRecord {
  id: string
  post_id: string | null
  website_id: string
  title: string
  target_id: string
  target_name: string
  kind: string
  target_revision: number | null
  status: DeliveryStatus
  uncertain: boolean
  attempt_count: number
  created_at: number
  available_at: number
  last_result: string | null
  error_code: string | null
  cancel_requested: boolean
}
export interface Attempt {
  sequence: number
  started_at: number
  finished_at: number | null
  result: string
  error_code: string | null
  late_result: string | null
  late_finished_at: number | null
}
export interface DeliveryDetail extends DeliveryRecord {
  post: {
    title: string | null
    summary: string | null
    author: string | null
    category: string | null
    published_at: string | null
    first_seen_at: number | null
    original_url: string | null
  }
  tasks: Page<{ id: string; name: string; version: number; deleted: boolean }>
  attempts: Page<Attempt>
  receipt_at: number | null
}
export interface TestRecord {
  id: string
  target_id: string
  target_name: string
  kind: string
  result: string
  error_code: string | null
  started_at: number
  finished_at: number | null
}
export interface ManualRecord extends TestRecord {
  source_event_id: string
  source_exists: boolean
  title: string
  target_revision: number
  post_id: string | null
  post: DeliveryDetail['post']
  tasks: Page<{ name: string; version: number }>
}
export interface Options {
  tasks: { id: string; name: string; deleted: boolean }[]
  categories: string[]
  category_options: { website_id: string; value: string; label: string }[]
  targets: { id: string; name: string }[]
  websites: { id: string; name: string }[]
  truncated: boolean
}
export const postLabels: Record<PostStatus, string> = {
  match: '命中',
  no_match: '不命中',
  insufficient_data: '信息不足',
  not_evaluated: '未执行匹配',
  unrecorded: '历史结果未记录',
}
export const deliveryLabels: Record<DeliveryStatus, string> = {
  pending: '等待发送',
  retry: '等待重试',
  leased: '发送中',
  sent: '成功',
  failed: '失败',
  cancelled: '已取消',
}
export const resultLabels: Record<string, string> = {
  success: '渠道已接受',
  transient_error: '临时错误',
  permanent_error: '明确拒绝',
  unknown: '结果未知',
  in_progress: '尝试尚未结束',
}
export const kindLabels: Record<string, string> = {
  telegram: 'Telegram Bot',
  bark: 'Bark',
  smtp: 'SMTP',
  webhook: 'Webhook',
  mock: '离线模拟',
  unknown: '历史渠道未记录',
}
export function resultClass(value: string) {
  return ['match', 'sent', 'success'].includes(value)
    ? 'yes'
    : ['no_match', 'failed', 'permanent_error'].includes(value)
      ? 'no'
      : ['not_evaluated', 'unrecorded', 'cancelled'].includes(value)
        ? 'neutral'
        : 'unknown'
}
export function reasonText(reason: Reason) {
  const known: Record<string, string> = {
    missing_summary: '摘要缺失',
    missing_author: '作者缺失',
    missing_category: '版块缺失',
    author_include:
      reason.truth === 'true'
        ? '作者在包含名单内'
        : reason.truth === 'false'
          ? '作者不在包含名单内'
          : '无法确定作者是否在包含名单内',
    author_exclude:
      reason.truth === 'true'
        ? '作者在排除名单内'
        : reason.truth === 'false'
          ? '作者不在排除名单内'
          : '无法确定作者是否在排除名单内',
    category:
      reason.truth === 'true'
        ? '版块符合范围'
        : reason.truth === 'false'
          ? '版块不在范围内'
          : '无法确定版块',
  }
  if (known[reason.code]) return known[reason.code]
  const prefix =
    reason.code === 'exclude'
      ? '排除词'
      : reason.code === 'all_of'
        ? '全部包含词'
        : reason.code === 'any_of'
          ? '至少包含词'
          : '判定'
  return (
    (reason.group ? '条件组 ' + reason.group + ' · ' : '') +
    prefix +
    (reason.term ? '「' + reason.term + '」' : '') +
    '：' +
    { true: '已出现', false: '未出现', unknown: '无法确定' }[reason.truth]
  )
}
export function historyGet<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined> = {},
) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== '') query.set(key, String(value))
  return request<T>('manage/history/' + path + (query.size ? '?' + query.toString() : ''))
}
interface RemoteOptions {
  cacheKey?: () => string | undefined
  debounce?: () => unknown
  keepPrevious?: boolean
  scope?: () => string | undefined
  prepared?: boolean
}
export function useRemote<T>(
  loader: () => Promise<T>,
  inputs: () => unknown,
  options: RemoteOptions = {},
) {
  const data = shallowRef<T>(),
    loading = ref(false),
    error = ref(''),
    stale = ref(false)
  let dataScope: string | undefined
  let dataIdentity: string | undefined
  let dataRevision = readCacheRevision.value,
    dataSession = readSessionRevision.value
  let generation = 0,
    timer: ReturnType<typeof setTimeout> | undefined
  function reload(delay = 0, prepared = false) {
    clearTimeout(timer)
    const current = ++generation
    const revision = readCacheRevision.value,
      session = readSessionRevision.value
    const key = options.cacheKey?.(),
      identity = key ?? JSON.stringify(inputs())
    loading.value = true
    error.value = ''
    const scope = options.scope?.()
    const cached = key ? cachedRead<T>(key) : undefined
    if (cached !== undefined) {
      data.value = cached
      dataIdentity = identity
      dataScope = scope
      dataRevision = readIsFresh(key!) ? revision : -1
      dataSession = session
    } else if (
      dataSession !== session ||
      (dataIdentity !== identity &&
        (!options.keepPrevious || (options.scope && dataScope !== scope)))
    ) {
      data.value = undefined
      dataIdentity = undefined
    }
    stale.value =
      data.value !== undefined && (dataIdentity !== identity || dataRevision !== revision)
    if (prepared && cached !== undefined && !stale.value) {
      loading.value = false
      return
    }
    const run = async () => {
      try {
        const value = await fetchRead(key, loader)
        if (
          current === generation &&
          session === readSessionRevision.value &&
          revision === readCacheRevision.value
        ) {
          data.value = value
          dataIdentity = identity
          dataScope = scope
          dataRevision = revision
          dataSession = session
          stale.value = false
          if (key) rememberRead(key, value, revision)
        }
      } catch (e) {
        if (current === generation)
          error.value = e instanceof Error ? e.message : '加载失败，请重试。'
      } finally {
        if (current === generation) loading.value = false
      }
    }
    if (delay) timer = setTimeout(run, delay)
    else void run()
  }
  let initial = true
  let previousDebounce = options.debounce?.()
  watch(
    () => [inputs(), readCacheRevision.value],
    () => {
      const next = options.debounce?.()
      const delay = options.debounce && next !== previousDebounce ? 180 : 0
      previousDebounce = next
      reload(delay, initial && options.prepared)
      initial = false
    },
    { immediate: true, deep: true },
  )
  onBeforeUnmount(() => {
    ++generation
    clearTimeout(timer)
  })
  return { data, loading, error, stale, reload: () => reload() }
}
