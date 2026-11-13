<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AppSelect from '../components/AppSelect.vue'
import Icon from '../components/Icon.vue'
import Pagination from '../components/Pagination.vue'
import ProblemDrawer from '../components/ProblemDrawer.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { channelMeta } from '../shared'
import { request } from '../store'
import { useRemote } from '../history'
import { untilShown } from '../viewReady'
import {
  alertSummary,
  attemptLabels,
  clock,
  elapsed,
  handlingBadges,
  handlingLabels,
  relative,
  stageLabels,
  stamp,
  type HotlistSite,
  type OperationsStatus,
  type Problem,
  type ProblemPage,
  type ProblemRow,
  type ServiceRow,
  type SourceRow,
  type StatusNode,
  type TargetRow,
  type Tone,
} from '../operations'
const emit = defineEmits<{ navigate: [path: string] }>()

const status = useRemote(
  () => request<OperationsStatus>('manage/operations/status'),
  () => [],
)
const data = computed(() => status.data.value)
const kind = ref(''),
  days = ref(7),
  showShort = ref(false),
  page = ref(1)
watch([kind, days, showShort], () => (page.value = 1), { flush: 'sync' })
const history = useRemote(
  () =>
    request<ProblemPage>(
      'manage/operations/problems?' +
        new URLSearchParams({
          kind: kind.value,
          days: String(days.value),
          show_short: String(showShort.value),
          page: String(page.value),
        }),
    ),
  () => [kind.value, days.value, showShort.value, page.value],
  { keepPrevious: true },
)
// The button stays enabled so keyboard focus is not dropped while a read runs.
function refresh() {
  if (status.loading.value) return
  status.reload()
  history.reload()
}
// Returning to the tab fires both focus and visibilitychange; read once.
let returnedAt = 0
function returned() {
  if (document.visibilityState !== 'visible' || Date.now() - returnedAt < 2000) return
  returnedAt = Date.now()
  refresh()
}
onMounted(() => {
  window.addEventListener('focus', returned)
  document.addEventListener('visibilitychange', returned)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', returned)
  document.removeEventListener('visibilitychange', returned)
})

// Every time on this page is read against the snapshot, not the browser clock.
const now = () => data.value?.checked_at ?? Date.now() / 1000
const ago = (at: number | null | undefined) => relative(at, now())
const severe = (tone: Tone) => tone === 'fail' || tone === 'warn'

function problemFacts(problem: Problem) {
  if (problem.kind === 'stall')
    return ['循环已 ' + elapsed(now() - (problem.since ?? now())) + '未完成']
  const facts = []
  if (problem.since) facts.push('已持续 ' + elapsed(now() - problem.since))
  if (problem.failures) facts.push('连续失败 ' + problem.failures + ' 次')
  if (problem.next_attempt_at) facts.push(ago(problem.next_attempt_at) + '重试')
  return facts
}
const selected = ref<{ eventId: string | null; problem?: Problem }>()
const openProblem = (problem: Problem) => (selected.value = { eventId: problem.event_id, problem })
const openHistory = (row: ProblemRow) => (selected.value = { eventId: row.id })

// Phones show healthy rows folded and problem rows open; a tap flips either.
const flipped = reactive(new Set<string>())
const rowOpen = (key: string, issue: boolean) => issue !== flipped.has(key)
function toggleRow(key: string) {
  if (flipped.has(key)) flipped.delete(key)
  else flipped.add(key)
}

const sourceSteps = (row: SourceRow) => [
  { key: 'schedule', label: '调度', node: row.schedule },
  { key: 'fetch', label: '抓取', node: row.fetch },
  { key: 'parse', label: '解析', node: row.parse },
  { key: 'latest', label: '最近一轮', node: row.latest },
]
const sourceIssue = (row: SourceRow) => sourceSteps(row).some((step) => severe(step.node.tone))
// Paused sites and a stopped runtime have nothing to show past scheduling.
const sourceIdle = (row: SourceRow) => row.fetch.state === 'none'
function sourceState(row: SourceRow): { tone: Tone; text: string } {
  const blocked = sourceSteps(row).find((step) => severe(step.node.tone))
  if (blocked) return { tone: blocked.node.tone, text: blocked.label + blocked.node.label }
  if (row.schedule.tone !== 'ok') return { tone: row.schedule.tone, text: row.schedule.label }
  return { tone: 'ok', text: '正常' }
}
const codeNode = (node: StatusNode) => node.state === 'failed' || node.state === 'stale'
const nodeDetail = (node: StatusNode) =>
  codeNode(node) ? '' : [node.detail, node.at ? ago(node.at) : ''].filter(Boolean).join(' ')

const targetStatus: Record<TargetRow['status'], string> = {
  enabled: '已启用',
  paused: '已暂停',
  unconfigured: '未配置',
}
const targetActive = (row: TargetRow) => row.status === 'enabled'
const lastTone = (row: TargetRow): Tone =>
  !row.last
    ? 'none'
    : row.last.result === 'success'
      ? 'ok'
      : row.last.result === 'permanent_error'
        ? 'fail'
        : 'warn'
const targetIssue = (row: TargetRow) => targetActive(row) && severe(lastTone(row))
function targetState(row: TargetRow): { tone: Tone; text: string } {
  if (!targetActive(row)) return { tone: 'none', text: targetStatus[row.status] }
  if (!row.last) return { tone: 'none', text: '尚无发送' }
  return { tone: lastTone(row), text: attemptLabels[row.last.result] || row.last.result }
}
function queueText(row: TargetRow) {
  const waiting = row.queue.pending + row.queue.retry
  if (!waiting) return '无待发送'
  return [
    row.queue.pending ? '待发送 ' + row.queue.pending : '',
    row.queue.retry ? '等待重试 ' + row.queue.retry : '',
  ]
    .filter(Boolean)
    .join(' · ')
}
const queueDetail = (row: TargetRow) =>
  row.queue.pending + row.queue.retry && row.queue.earliest_at
    ? '最早 ' + ago(row.queue.earliest_at)
    : ''
function sendingText(row: TargetRow) {
  if (row.expired_leases) return '租约已过期 ' + row.expired_leases
  return row.sending ? '发送中 ' + row.sending : '空闲'
}
const channel = (row: TargetRow) => channelMeta[row.kind as keyof typeof channelMeta]

function hotlistState(site: HotlistSite): { tone: Tone; text: string } {
  const abnormal = site.lists.filter((item) => severe(item.tone))
  if (abnormal.length)
    return {
      tone: abnormal.some((item) => item.tone === 'fail') ? 'fail' : 'warn',
      text:
        abnormal.length === 1
          ? abnormal[0]!.period_label + abnormal[0]!.label
          : abnormal.length + ' 个榜单异常',
    }
  if (site.lists.every((item) => item.tone === 'ok')) return { tone: 'ok', text: '正常' }
  const first = site.lists.find((item) => item.tone !== 'ok') ?? site.lists[0]
  return first ? { tone: first.tone, text: first.label } : { tone: 'none', text: '—' }
}
const hotlistIssue = (site: HotlistSite) => site.lists.some((item) => severe(item.tone))

function serviceState(row: ServiceRow): { tone: Tone; text: string } {
  switch (row.state) {
    case 'running':
      return { tone: 'ok', text: '运行中' }
    case 'stalled':
      return {
        tone: 'warn',
        text: row.last_loop_at
          ? '循环已 ' + elapsed(now() - row.last_loop_at) + '未完成'
          : '循环尚未完成',
      }
    case 'failed':
      return { tone: 'fail', text: '已停止' }
    case 'stopped_with':
      return { tone: 'fail', text: '随' + (row.stopped_with || '其他服务') + '停止' }
    default:
      return { tone: 'none', text: '状态未知' }
  }
}
const serviceDetail = (row: ServiceRow) =>
  row.state !== 'running'
    ? ''
    : row.last_loop_at
      ? '最近一轮 ' + ago(Math.min(row.last_loop_at, now()))
      : '尚未完成一轮'

const alertsOff = computed(
  () => !!data.value && (!data.value.alerts.enabled || !data.value.alerts.ready_targets),
)

interface Tile {
  key: string
  icon: string
  label: string
  tone: Tone
  value: string
  note: string
}
const tiles = computed<Tile[]>(() => {
  const value = data.value
  if (!value) return []
  const sources = value.sources
  const sourceIssues = sources.filter(sourceIssue).length
  const paused = sources.filter((row) => !row.enabled).length
  const succeeded = Math.max(0, ...sources.map((row) => row.last_success_at ?? 0))
  const targets = value.targets
  const targetIssues = targets.filter(targetIssue).length
  const waiting = targets
    .filter(targetActive)
    .reduce((sum, row) => sum + row.queue.pending + row.queue.retry, 0)
  const lists = value.hotlists.flatMap((site) => site.lists)
  const listIssues = lists.filter((item) => severe(item.tone)).length
  const running = value.services.filter((row) => row.state === 'running').length
  const services = value.services.length
  return [
    {
      key: 'sources',
      icon: 'rss',
      label: '采集',
      ...(!sources.length
        ? { tone: 'none', value: '未添加网站' }
        : sourceIssues
          ? { tone: 'fail', value: sourceIssues + ' 个网站异常' }
          : paused === sources.length
            ? { tone: 'none', value: '已全部暂停' }
            : { tone: 'ok', value: '正常' }),
      note: !sources.length
        ? '添加网站后开始采集'
        : [
            sources.length + ' 个网站',
            paused ? paused + ' 个已暂停' : '',
            succeeded ? '最近成功 ' + ago(succeeded) : '',
          ]
            .filter(Boolean)
            .join(' · '),
    },
    {
      key: 'targets',
      icon: 'send',
      label: '通知',
      ...(!targets.length
        ? { tone: 'none', value: '未添加目标' }
        : targetIssues
          ? { tone: 'fail', value: targetIssues + ' 个目标异常' }
          : { tone: 'ok', value: '正常' }),
      note: !targets.length
        ? '添加目标后才能收到通知'
        : targets.length + ' 个目标 · ' + (waiting ? '待发送 ' + waiting : '无待发送'),
    },
    {
      key: 'hotlists',
      icon: 'spark',
      label: '热榜',
      ...(!lists.length
        ? { tone: 'none', value: '未显示' }
        : listIssues
          ? { tone: 'warn', value: listIssues + ' 个榜单异常' }
          : lists.some((item) => item.tone === 'ok')
            ? { tone: 'ok', value: '正常' }
            : { tone: lists[0]!.tone, value: lists[0]!.label }),
      note: !lists.length
        ? '概览未显示热榜，不刷新'
        : value.hotlists.length + ' 个网站 · ' + lists.length + ' 个榜单',
    },
    {
      key: 'services',
      icon: 'cpu',
      label: '后台服务',
      ...(running === services
        ? { tone: 'ok', value: '运行中' }
        : { tone: 'fail', value: services - running + ' 个异常' }),
      note: running + ' / ' + services + ' 正常',
    },
  ] as Tile[]
})
// Nothing failing is not the same as working: with no enabled site or target, say so.
const headline = computed(() => {
  const value = data.value
  const count = value?.problems.length ?? 0
  const calm = '当前没有需要处理的问题'
  if (count) return { tone: 'fail', icon: 'alert', text: count + ' 个问题待处理', note: '' }
  if (tiles.value.some((tile) => severe(tile.tone)))
    return { tone: 'warn', icon: 'alert', text: '有需要留意的状态', note: calm }
  if (value && !value.sources.some((row) => row.enabled))
    return { tone: 'none', icon: 'activity', text: '未在监控', note: '没有启用的监控网站' }
  if (value && !value.targets.some(targetActive))
    return { tone: 'none', icon: 'activity', text: '收不到通知', note: '没有可用的通知目标' }
  return { tone: 'ok', icon: 'check', text: '运行正常', note: calm }
})

// The four tiles are tabs over one detail panel; open on the first group that needs a look.
const chosen = ref<string>()
const group = computed(
  () => chosen.value ?? tiles.value.find((tile) => severe(tile.tone))?.key ?? 'sources',
)
function moveTab(event: KeyboardEvent, index: number) {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
  const count = tiles.value.length
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? count - 1
        : step
          ? (index + step + count) % count
          : -1
  if (next < 0) return
  event.preventDefault()
  chosen.value = tiles.value[next]!.key
  document.getElementById('ops-tab-' + chosen.value)?.focus()
}
// Lists that all read the same (say, never fetched) collapse into one line.
const hotlistUniform = (site: HotlistSite) =>
  site.lists.length > 1 &&
  !hotlistIssue(site) &&
  site.lists.every((item) => item.label === site.lists[0]!.label && item.tone !== 'ok')

const statusLabels: Record<ProblemRow['status'], string> = {
  ongoing: '进行中',
  recovered: '已恢复',
  paused: '已暂停',
}
const statusBadges: Record<ProblemRow['status'], string> = {
  ongoing: 'rose',
  recovered: 'green',
  paused: 'neutral',
}
function lastedText(row: ProblemRow) {
  if (row.ended_at) return elapsed(row.ended_at - row.started_at)
  if (row.status === 'paused') return '暂停时未恢复'
  if (row.status === 'ongoing') return elapsed(now() - row.started_at)
  return '—'
}
const kindOptions = [
  { value: '', label: '全部类型' },
  { value: 'source', label: '采集' },
  { value: 'delivery', label: '通知' },
  { value: 'runtime', label: '后台服务' },
]
const dayOptions = [
  { value: 1, label: '近 24 小时' },
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
]
await untilShown(() => status.ready() && history.ready())
</script>
<template>
  <ReadRegion
    :loading="status.loading.value"
    :error="status.error.value"
    :has-data="!!data"
    :stale="status.stale.value"
    :min-height="360"
    @retry="status.reload"
  >
    <div v-if="data" class="ops-stack">
      <section class="panel ops-overview" aria-labelledby="ops-headline">
        <div class="ops-overview-head">
          <span class="ops-health" :class="'is-' + headline.tone"
            ><Icon :name="headline.icon" :size="20"
          /></span>
          <div class="ops-overview-copy">
            <h2 id="ops-headline">{{ headline.text }}</h2>
            <p>
              <template v-if="headline.note">{{ headline.note }} · </template>观测于
              {{ clock(data.checked_at) }}
            </p>
          </div>
          <button class="button" :aria-busy="status.loading.value" @click="refresh">
            <Icon name="refresh" :size="14" />刷新
          </button>
        </div>
        <div v-if="data.problems.length" class="ops-problems" role="region" aria-label="当前问题">
          <article
            v-for="problem in data.problems"
            :key="problem.key"
            class="ops-problem"
            :class="'is-' + problem.status"
          >
            <div class="ops-problem-copy">
              <div class="ops-problem-head">
                <strong>{{ problem.label }}</strong>
                <span class="small-badge" :class="handlingBadges[problem.status]">{{
                  handlingLabels[problem.status]
                }}</span>
              </div>
              <p class="ops-problem-reason">
                {{ stageLabels[problem.stage] || problem.stage }}：{{ problem.summary }}
                <code v-if="problem.code" class="ops-code">{{ problem.code }}</code>
              </p>
              <p v-if="problem.hint" class="ops-problem-hint">{{ problem.hint }}</p>
              <p class="ops-muted">
                <span v-if="problem.since" :title="stamp(problem.since) + ' 开始'"
                  >{{ stamp(problem.since) }} 开始 · </span
                >{{ problemFacts(problem).join(' · ') }}
              </p>
            </div>
            <button class="button" @click="openProblem(problem)">
              查看详情<Icon name="arrow" :size="14" />
            </button>
          </article>
        </div>
        <p v-if="alertsOff" class="ops-alert-note">
          <Icon name="bell" :size="15" />
          <span>系统告警未启用或没有可用目标，出现故障时不会收到通知。</span>
          <button class="text-link" @click="emit('navigate', '/settings/alerts')">去设置</button>
        </p>
      </section>

      <section class="panel ops-board" aria-label="运行链路">
        <div class="ops-tabs" role="tablist" aria-label="运行链路">
          <button
            v-for="(tile, index) in tiles"
            :id="'ops-tab-' + tile.key"
            :key="tile.key"
            class="ops-tab"
            role="tab"
            :aria-selected="group === tile.key"
            :aria-controls="'ops-panel-' + tile.key"
            :tabindex="group === tile.key ? 0 : -1"
            @click="chosen = tile.key"
            @keydown="moveTab($event, index)"
          >
            <span class="ops-tab-label"
              ><span class="about-tile-icon"><Icon :name="tile.icon" :size="16" /></span
              >{{ tile.label }}</span
            >
            <strong :class="'tone-' + tile.tone"><i class="ops-dot" />{{ tile.value }}</strong>
            <small>{{ tile.note }}</small>
          </button>
        </div>
        <div
          :id="'ops-panel-' + group"
          class="ops-panel"
          role="tabpanel"
          :aria-labelledby="'ops-tab-' + group"
        >
          <template v-if="group === 'sources'">
            <div v-if="!data.sources.length" class="ops-empty">
              <span>还没有添加监控网站。</span>
              <button class="button" @click="emit('navigate', '/websites')">添加网站</button>
            </div>
            <article
              v-for="row in data.sources"
              :key="row.website_id"
              class="ops-row"
              :class="{ open: rowOpen('s' + row.website_id, sourceIssue(row)) }"
            >
              <div class="ops-row-head">
                <span class="icon-tile ops-row-icon" :class="row.enabled ? 'orange' : 'gray'"
                  ><Icon name="globe" :size="17"
                /></span>
                <div class="ops-row-name">
                  <button
                    class="text-link"
                    @click="emit('navigate', '/websites/' + row.website_id)"
                  >
                    {{ row.name }}
                  </button>
                  <span class="ops-state" :class="'tone-' + sourceState(row).tone"
                    ><i class="ops-dot" />{{ sourceState(row).text }}</span
                  >
                </div>
                <button
                  class="ops-toggle"
                  :aria-expanded="rowOpen('s' + row.website_id, sourceIssue(row))"
                  :aria-label="row.name + '：' + sourceState(row).text"
                  @click="toggleRow('s' + row.website_id)"
                >
                  <span :class="'tone-' + sourceState(row).tone"
                    ><i class="ops-dot" />{{ sourceState(row).text }}</span
                  >
                  <Icon name="down" :size="14" />
                </button>
              </div>
              <div class="ops-row-body">
                <p v-if="sourceIdle(row)" class="ops-idle">
                  <span :class="'tone-' + row.schedule.tone">{{
                    row.enabled ? row.schedule.label + '，暂不采集' : '已暂停，不采集'
                  }}</span>
                  <span v-if="row.last_success_at" :title="stamp(row.last_success_at)"
                    >最近成功 {{ ago(row.last_success_at) }}</span
                  >
                </p>
                <ol v-else class="ops-steps">
                  <li
                    v-for="step in sourceSteps(row)"
                    :key="step.key"
                    class="ops-step"
                    :class="{
                      blocked: step.node.tone === 'fail',
                      quiet: step.node.tone === 'none',
                    }"
                  >
                    <span class="ops-step-label">{{ step.label }}</span>
                    <strong :class="'tone-' + step.node.tone"
                      ><i class="ops-dot" />{{ step.node.label }}</strong
                    >
                    <code v-if="codeNode(step.node) && step.node.detail" class="ops-code">{{
                      step.node.detail
                    }}</code>
                    <small v-else-if="nodeDetail(step.node)">{{ nodeDetail(step.node) }}</small>
                  </li>
                </ol>
                <p v-if="!sourceIdle(row)" class="ops-row-times">
                  <span :title="stamp(row.last_success_at)"
                    >最近成功 {{ ago(row.last_success_at) }}</span
                  >
                  <span
                    v-if="row.enabled && row.next_attempt_at"
                    :title="stamp(row.next_attempt_at)"
                    >下次尝试 {{ ago(row.next_attempt_at) }}</span
                  >
                  <span v-if="row.gap_at" class="tone-warn" :title="stamp(row.gap_at)"
                    >可能漏帖 {{ stamp(row.gap_at) }}</span
                  >
                </p>
              </div>
            </article>
          </template>

          <template v-else-if="group === 'targets'">
            <div v-if="!data.targets.length" class="ops-empty">
              <span>还没有通知目标。</span>
              <button class="button" @click="emit('navigate', '/target/new')">添加通知目标</button>
            </div>
            <article
              v-for="row in data.targets"
              :key="row.id"
              class="ops-row"
              :class="{ open: rowOpen('t' + row.id, targetIssue(row)) }"
            >
              <div class="ops-row-head">
                <span
                  class="icon-tile ops-row-icon"
                  :class="targetActive(row) ? channel(row)?.color || 'blue' : 'gray'"
                  ><Icon :name="channel(row)?.icon || 'send'" :size="17"
                /></span>
                <div class="ops-row-name">
                  <button
                    class="text-link"
                    @click="emit('navigate', '/operations/deliveries?target=' + row.id)"
                  >
                    {{ row.name }}
                  </button>
                  <span class="ops-state" :class="'tone-' + targetState(row).tone"
                    ><i class="ops-dot" />{{ targetState(row).text }}</span
                  >
                </div>
                <button
                  class="ops-toggle"
                  :aria-expanded="rowOpen('t' + row.id, targetIssue(row))"
                  :aria-label="row.name + '：' + targetState(row).text"
                  @click="toggleRow('t' + row.id)"
                >
                  <span :class="'tone-' + targetState(row).tone"
                    ><i class="ops-dot" />{{ targetState(row).text }}</span
                  >
                  <Icon name="down" :size="14" />
                </button>
              </div>
              <div class="ops-row-body">
                <p v-if="!targetActive(row)" class="ops-idle tone-none">
                  {{ row.status === 'paused' ? '已暂停，不发送' : '未配置，不发送' }}
                </p>
                <ol v-else class="ops-steps ops-facts">
                  <li class="ops-step" :class="{ quiet: !(row.queue.pending + row.queue.retry) }">
                    <span class="ops-step-label">队列</span>
                    <strong>{{ queueText(row) }}</strong>
                    <small v-if="queueDetail(row)">{{ queueDetail(row) }}</small>
                  </li>
                  <li class="ops-step" :class="{ quiet: !row.sending && !row.expired_leases }">
                    <span class="ops-step-label">发送中</span>
                    <strong :class="{ 'tone-warn': row.expired_leases }">{{
                      sendingText(row)
                    }}</strong>
                  </li>
                  <li class="ops-step" :class="{ quiet: !row.uncertain }">
                    <span class="ops-step-label">结果不确定</span>
                    <strong :class="{ 'tone-warn': row.uncertain }">{{ row.uncertain }}</strong>
                  </li>
                  <li class="ops-step" :class="{ blocked: lastTone(row) === 'fail' }">
                    <span class="ops-step-label">最近结果</span>
                    <template v-if="row.last">
                      <strong :class="'tone-' + lastTone(row)"
                        ><i class="ops-dot" />{{
                          attemptLabels[row.last.result] || row.last.result
                        }}
                        <small :title="stamp(row.last.at)">{{ ago(row.last.at) }}</small></strong
                      >
                      <code v-if="row.last.code" class="ops-code">{{ row.last.code }}</code>
                    </template>
                    <strong v-else class="tone-none">尚无记录</strong>
                  </li>
                </ol>
              </div>
            </article>
          </template>

          <template v-else-if="group === 'hotlists'">
            <div v-if="!data.hotlists.length" class="ops-empty">概览未显示热榜，当前不刷新。</div>
            <article
              v-for="site in data.hotlists"
              :key="site.website_id"
              class="ops-row"
              :class="{ open: rowOpen('h' + site.website_id, hotlistIssue(site)) }"
            >
              <div class="ops-row-head">
                <span class="icon-tile ops-row-icon orange"><Icon name="spark" :size="17" /></span>
                <div class="ops-row-name">
                  <strong>{{ site.name }}</strong>
                  <span class="ops-state" :class="'tone-' + hotlistState(site).tone"
                    ><i class="ops-dot" />{{ hotlistState(site).text }}</span
                  >
                </div>
                <button
                  class="ops-toggle"
                  :aria-expanded="rowOpen('h' + site.website_id, hotlistIssue(site))"
                  :aria-label="site.name + ' 热榜：' + hotlistState(site).text"
                  @click="toggleRow('h' + site.website_id)"
                >
                  <span :class="'tone-' + hotlistState(site).tone"
                    ><i class="ops-dot" />{{ hotlistState(site).text }}</span
                  >
                  <Icon name="down" :size="14" />
                </button>
              </div>
              <div class="ops-row-body">
                <p v-if="hotlistUniform(site)" class="ops-idle">
                  {{ site.lists.map((item) => item.period_label).join('、') }} ·
                  {{ site.lists[0]!.label }}
                </p>
                <ol
                  v-else
                  class="ops-steps ops-facts ops-lists"
                  :style="{ '--lists': Math.min(site.lists.length, 4) }"
                >
                  <li
                    v-for="item in site.lists"
                    :key="item.period"
                    class="ops-step"
                    :class="{ blocked: item.tone === 'fail', quiet: item.tone === 'none' }"
                  >
                    <span class="ops-step-label">{{ item.period_label }}</span>
                    <strong :class="'tone-' + item.tone"
                      ><i class="ops-dot" />{{ item.label }}</strong
                    >
                    <code v-if="codeNode(item) && item.detail" class="ops-code">{{
                      item.detail
                    }}</code>
                    <small v-if="item.at" :title="stamp(item.at)">获取于 {{ ago(item.at) }}</small>
                    <small v-else-if="!codeNode(item) && nodeDetail(item)">{{
                      nodeDetail(item)
                    }}</small>
                  </li>
                </ol>
              </div>
            </article>
          </template>

          <template v-else>
            <ol class="ops-steps ops-facts ops-services">
              <li
                v-for="row in data.services"
                :key="row.id"
                class="ops-step"
                :class="{ blocked: serviceState(row).tone === 'fail' }"
              >
                <span class="ops-step-label">{{ row.name }}</span>
                <strong :class="'tone-' + serviceState(row).tone"
                  ><i class="ops-dot" />{{ serviceState(row).text }}</strong
                >
                <small v-if="serviceDetail(row)" :title="stamp(row.last_loop_at)">{{
                  serviceDetail(row)
                }}</small>
              </li>
            </ol>
          </template>
        </div>
      </section>

      <section class="panel" aria-labelledby="ops-history">
        <div class="ops-card-head ops-history-head">
          <h2 id="ops-history">问题历史</h2>
          <div class="ops-filters">
            <label class="ops-check" title="采集问题在下一轮采集即恢复，其他问题在 1 分钟内恢复"
              ><input v-model="showShort" type="checkbox" />显示自动恢复的短暂问题</label
            >
            <AppSelect v-model="kind" aria-label="问题类型" :options="kindOptions" />
            <AppSelect v-model="days" aria-label="时间范围" :options="dayOptions" />
          </div>
        </div>
        <ReadRegion
          :loading="history.loading.value"
          :error="history.error.value"
          :has-data="!!history.data.value"
          :stale="history.stale.value"
          :min-height="120"
          @retry="history.reload"
        >
          <template v-if="history.data.value">
            <div
              v-if="history.data.value.items.length"
              class="ops-head ops-history-grid"
              aria-hidden="true"
            >
              <span>状态</span><span>对象与原因</span><span>开始</span><span>持续</span
              ><span>系统告警</span>
            </div>
            <button
              v-for="row in history.data.value.items"
              :key="row.id"
              class="ops-history-row ops-history-grid"
              :aria-label="'查看问题：' + row.label"
              @click="openHistory(row)"
            >
              <span
                ><span class="small-badge" :class="statusBadges[row.status]">{{
                  statusLabels[row.status]
                }}</span></span
              >
              <span class="ops-history-what">
                <strong>{{ row.label }}</strong>
                <span
                  >{{ row.summary }}
                  <code v-if="row.code" class="ops-code">{{ row.code }}</code></span
                >
              </span>
              <span class="ops-history-time">{{ stamp(row.started_at) }}</span>
              <span class="ops-history-time">{{ lastedText(row) }}</span>
              <span class="ops-muted">{{ alertSummary(row.alerts) }}</span>
            </button>
            <div v-if="!history.data.value.total" class="ops-empty-state">
              <span class="about-tile-icon"><Icon name="check" :size="16" /></span>
              <p>这段时间没有记录到问题。</p>
            </div>
            <Pagination
              v-if="history.data.value.total > history.data.value.page_size"
              :page="history.data.value.page"
              :total="history.data.value.total"
              :page-size="history.data.value.page_size"
              label="问题历史"
              @change="(value) => (page = value)"
            />
          </template>
        </ReadRegion>
      </section>
    </div>
  </ReadRegion>
  <ProblemDrawer
    v-if="selected"
    :key="selected.eventId || selected.problem?.key"
    :event-id="selected.eventId"
    :problem="selected.problem"
    @close="selected = undefined"
    @navigate="(path) => emit('navigate', path)"
  />
</template>
<style scoped>
.ops-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ops-card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 16px 22px;
  border-bottom: 1px solid var(--border);
}
.ops-card-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

/* Overview */
.ops-overview {
  overflow: hidden;
}
.ops-overview-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 22px;
}
.ops-health {
  display: grid;
  flex: none;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
}
.ops-health.is-ok {
  color: #2f6f4f;
  background: #ecf6f0;
}
.ops-health.is-none {
  color: #6f7885;
  background: #f2f4f6;
}
.ops-health.is-warn {
  color: #8a5a0b;
  background: #fbf3e4;
}
.ops-health.is-fail {
  color: #a8324a;
  background: #fbeef0;
}
.ops-overview-copy {
  flex: 1;
  min-width: 0;
}
.ops-overview-copy h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}
.ops-overview-copy p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

/* Group tabs: the summary tiles double as the switch for the detail panel. */
.ops-tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 18px 22px;
}
.ops-tab {
  display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: #f8f9fb;
  text-align: left;
  transition:
    background 0.15s,
    border-color 0.15s,
    box-shadow 0.15s;
}
.ops-tab:hover {
  border-color: #e3e6ea;
}
.ops-tab[aria-selected='true'] {
  border-color: #ecc9b5;
  background: #fffaf7;
  box-shadow: 0 1px 2px rgb(183 94 50 / 8%);
}
.ops-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.ops-tab-label {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #808b98;
  font-size: 12px;
}
.ops-tab-label .about-tile-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
}
.ops-tab strong {
  display: block;
  font-size: 15px;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.ops-tab strong > .ops-dot {
  margin: 0 7px 2px 0;
  vertical-align: middle;
}
.ops-tab small {
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.ops-panel {
  border-top: 1px solid var(--border);
}
.ops-alert-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin: 0 22px 18px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #fdf7ec;
  color: #8a5a0b;
  font-size: 12px;
}
.ops-alert-note .text-link {
  margin-left: auto;
}

/* Current problems */
.ops-problem {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 24px;
  padding: 16px 22px 16px 19px;
  border-left: 3px solid transparent;
}
.ops-problem {
  border-top: 1px solid var(--border);
}
.ops-problems + .ops-alert-note {
  margin-top: 16px;
}
.ops-problem.is-action {
  border-left-color: #d98a98;
}
.ops-problem.is-auto_retry {
  border-left-color: #e2b765;
}
.ops-problem.is-verifying {
  border-left-color: #c3c9d1;
}
.ops-problem-copy {
  flex: 1 1 420px;
  min-width: 0;
}
.ops-problem-copy p {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
}
.ops-problem-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.ops-problem-head strong {
  font-size: 14px;
  font-weight: 600;
}
.ops-problem-head .small-badge {
  margin: 0;
}
.ops-problem-hint {
  color: #4b5562;
}
.ops-problem .button {
  gap: 6px;
}
.ops-muted {
  color: var(--muted);
  font-size: 12px;
}
.ops-code {
  display: inline-block;
  padding: 0 6px;
  border-radius: 4px;
  background: #f2f4f6;
  color: #5d6673;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.ops-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px;
  color: var(--muted);
}

/* Source and target rows */
.ops-row {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 12px 20px;
  align-items: center;
  padding: 16px 22px;
}
.ops-row + .ops-row {
  border-top: 1px solid var(--border);
}
.ops-row-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.ops-row-icon {
  width: 34px;
  height: 34px;
}
.ops-row-icon.gray {
  color: #8a939e;
  background: #f2f4f6;
}
.ops-row-name {
  display: grid;
  min-width: 0;
}
.ops-row-name .text-link {
  justify-self: start;
  max-width: 100%;
  overflow: hidden;
  font-weight: 600;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ops-state {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.ops-toggle {
  display: none;
}
.ops-row-body {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.ops-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 22px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.ops-step {
  position: relative;
  display: grid;
  align-content: start;
  gap: 2px;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: #f8f9fb;
  overflow-wrap: anywhere;
}
/* A chevron between pipeline steps; fact cells for targets stay unlinked. */
.ops-steps:not(.ops-facts) .ops-step + .ops-step::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -15px;
  width: 7px;
  height: 7px;
  border-top: 1.5px solid #c3c9d1;
  border-right: 1.5px solid #c3c9d1;
  transform: translateY(-50%) rotate(45deg);
}
.ops-facts {
  grid-template-columns: repeat(3, minmax(0, 1fr)) minmax(0, 1.5fr);
  gap: 10px;
}
.ops-step.blocked {
  border-color: #f0cdd4;
  background: #fbeef0;
}
.ops-step.quiet {
  background: #fbfbfc;
}
.ops-step.quiet strong {
  color: #6f7885;
  font-weight: 450;
}
.ops-step-label {
  color: #808b98;
  font-size: 11px;
}
.ops-step strong {
  display: block;
  font-weight: 550;
  font-variant-numeric: tabular-nums;
}
.ops-step strong > .ops-dot {
  margin: 0 6px 1px 0;
  vertical-align: middle;
}
.ops-step strong small {
  color: var(--muted);
  font-weight: 400;
  font-size: 11px;
}
.ops-step small {
  color: var(--muted);
  font-size: 11px;
}
.ops-step .ops-code {
  justify-self: start;
}
.ops-row-times {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.ops-idle {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.ops-dot {
  flex: none;
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.85;
}
.tone-ok {
  color: #2f6f4f;
}
.tone-wait,
.tone-warn {
  color: #8a5a0b;
}
.tone-fail {
  color: #a8324a;
}
.tone-none {
  color: #6f7885;
}

/* Hotlists and services */
.ops-lists {
  grid-template-columns: repeat(var(--lists, 4), minmax(0, 1fr));
  gap: 22px;
}
.ops-services {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 16px 22px;
}
.ops-row-name > strong {
  font-weight: 600;
}

/* Problem history */
.ops-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  color: #5d6673;
}
.ops-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.ops-head {
  padding: 10px 22px 6px;
  color: #808b98;
  font-size: 12px;
}
.ops-history-grid {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) 110px 120px 110px;
  gap: 12px;
  align-items: center;
}
.ops-history-row {
  width: 100%;
  padding: 11px 22px;
  border: 0;
  border-top: 1px solid var(--border);
  background: transparent;
  text-align: left;
  overflow-wrap: anywhere;
  transition: background 0.15s;
}
.ops-history-row:hover,
.ops-history-row:focus-visible {
  background: #fafbfc;
}
.ops-history-what {
  display: grid;
  min-width: 0;
}
.ops-history-what strong {
  font-weight: 550;
}
.ops-history-what > span {
  color: #5d6673;
  font-size: 12px;
}
.ops-history-time {
  font-variant-numeric: tabular-nums;
}
.small-badge.green {
  color: #417658;
  background: #f0f7f2;
}
.small-badge.rose {
  margin-left: 0;
}
.ops-empty-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 22px;
  color: var(--muted);
}
.ops-empty-state p {
  margin: 0;
}
.ops-empty-state .about-tile-icon {
  color: #2f6f4f;
  background: #ecf6f0;
}
@media (prefers-reduced-motion: reduce) {
  .ops-history-row,
  .ops-tab {
    transition: none;
  }
}
@media (max-width: 1100px) {
  .ops-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .ops-row {
    grid-template-columns: minmax(0, 1fr);
  }
  .ops-history-grid {
    grid-template-columns: 72px minmax(0, 1fr) 110px 110px;
  }
  .ops-history-grid > :nth-child(5) {
    display: none;
  }
}
/* Phones fold healthy rows; the whole row head becomes the toggle. */
@media (max-width: 760px) {
  .ops-overview-head,
  .ops-tabs,
  .ops-card-head,
  .ops-row,
  .ops-empty,
  .ops-services,
  .ops-empty-state {
    padding-left: 16px;
    padding-right: 16px;
  }
  .ops-problem {
    padding: 14px 16px 14px 13px;
  }
  .ops-problem .button {
    width: 100%;
    justify-content: center;
  }
  .ops-tabs {
    gap: 8px;
  }
  .ops-tab {
    gap: 6px;
    padding: 12px;
  }
  .ops-tab strong {
    font-size: 14px;
  }
  .ops-alert-note {
    margin: 0 16px 16px;
  }
  .ops-alert-note .text-link {
    margin-left: 0;
  }
  .ops-row {
    gap: 4px;
    padding-top: 6px;
    padding-bottom: 6px;
  }
  .ops-row-head {
    min-height: 44px;
  }
  .ops-row-name {
    flex: 1;
  }
  .ops-state {
    display: none;
  }
  .ops-toggle {
    display: flex;
    flex: none;
    align-items: center;
    gap: 8px;
    max-width: 55%;
    min-height: 44px;
    padding: 0;
    border: 0;
    background: none;
    font-size: 12px;
    text-align: right;
  }
  .ops-toggle > span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .ops-toggle :deep(svg) {
    flex: none;
    transition: transform 0.15s;
  }
  .ops-row.open .ops-toggle :deep(svg) {
    transform: rotate(180deg);
  }
  .ops-row-body {
    display: none;
    padding-bottom: 10px;
  }
  .ops-row.open .ops-row-body {
    display: grid;
  }
  .ops-steps,
  .ops-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .ops-steps:not(.ops-facts) .ops-step + .ops-step::before {
    display: none;
  }
  .ops-head {
    display: none;
  }
  .ops-history-row {
    padding: 12px 16px;
  }
  .ops-history-grid {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 12px;
  }
  .ops-history-grid > :nth-child(1) {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }
  .ops-history-grid > :nth-child(2) {
    grid-column: 1;
    grid-row: 1 / span 2;
  }
  .ops-history-grid > :nth-child(3),
  .ops-history-grid > :nth-child(4) {
    grid-row: 3;
    color: var(--muted);
    font-size: 12px;
  }
  .ops-history-grid > :nth-child(4) {
    grid-column: 2;
    justify-self: end;
  }
  .ops-history-grid > :nth-child(5) {
    display: block;
    grid-column: 2;
    grid-row: 2;
    justify-self: end;
    font-size: 11px;
  }
  .ops-filters {
    width: 100%;
  }
  .ops-filters > :deep(*) {
    flex: 1 1 140px;
  }
  .ops-check {
    flex-basis: 100% !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  .ops-toggle :deep(svg) {
    transition: none;
  }
}
</style>
