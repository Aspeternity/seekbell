<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AppSelect from '../components/AppSelect.vue'
import Icon from '../components/Icon.vue'
import Pagination from '../components/Pagination.vue'
import ProblemDrawer from '../components/ProblemDrawer.vue'
import ReadRegion from '../components/ReadRegion.vue'
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
  problemReason,
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
function refresh() {
  status.reload()
  history.reload()
}
function visible() {
  if (document.visibilityState === 'visible') refresh()
}
onMounted(() => {
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', visible)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', refresh)
  document.removeEventListener('visibilitychange', visible)
})

const nowSeconds = () => data.value?.checked_at ?? Date.now() / 1000
function problemFacts(problem: Problem) {
  if (problem.kind === 'stall')
    return ['循环已 ' + elapsed(nowSeconds() - (problem.since ?? nowSeconds())) + '未完成']
  const facts = []
  if (problem.since)
    facts.push(stamp(problem.since) + ' 开始，已持续 ' + elapsed(nowSeconds() - problem.since))
  if (problem.failures) facts.push('连续失败 ' + problem.failures + ' 次')
  if (problem.next_attempt_at) facts.push('下次重试 ' + stamp(problem.next_attempt_at))
  if (problem.hint) facts.push(problem.hint)
  return facts
}

const selected = ref<{ eventId: string | null; problem?: Problem }>()
const openProblem = (problem: Problem) => (selected.value = { eventId: problem.event_id, problem })
const openHistory = (row: ProblemRow) => (selected.value = { eventId: row.id })

const flipped = reactive(new Set<string>())
const severe = (tone: string) => tone === 'fail' || tone === 'warn'
const rowOpen = (key: string, issue: boolean) => issue !== flipped.has(key)
function toggleRow(key: string) {
  if (flipped.has(key)) flipped.delete(key)
  else flipped.add(key)
}
const sourceNodes = (row: SourceRow) => [
  { key: 'schedule', label: '调度', node: row.schedule },
  { key: 'fetch', label: '抓取', node: row.fetch },
  { key: 'parse', label: '解析', node: row.parse },
  { key: 'latest', label: '最近一轮', node: row.latest },
]
const sourceIssue = (row: SourceRow) => sourceNodes(row).some((item) => severe(item.node.tone))
function sourceSummary(row: SourceRow) {
  const blocked = sourceNodes(row).find((item) => severe(item.node.tone))
  if (blocked) return blocked.label + blocked.node.label
  if (row.schedule.tone !== 'ok') return row.schedule.label
  return '正常 · ' + stamp(row.last_success_at)
}
const nodeDetail = (node: StatusNode) =>
  [node.detail, node.at ? stamp(node.at) : ''].filter(Boolean).join(' ')

const targetStatus: Record<TargetRow['status'], string> = {
  enabled: '已启用',
  paused: '已暂停',
  unconfigured: '未配置',
}
const targetActive = (row: TargetRow) => row.status === 'enabled'
function queueText(row: TargetRow) {
  if (!targetActive(row)) return '—'
  const parts = []
  if (row.queue.pending) parts.push('待发送 ' + row.queue.pending)
  if (row.queue.retry) parts.push('等待重试 ' + row.queue.retry)
  if (!parts.length) return '无待发送'
  return parts.join('，') + ' · 最早 ' + stamp(row.queue.earliest_at)
}
function sendingText(row: TargetRow) {
  if (!targetActive(row)) return '—'
  if (row.expired_leases) return '租约已过期 ' + row.expired_leases
  return row.sending ? '发送中 ' + row.sending : '空闲'
}
function lastText(row: TargetRow) {
  if (!row.last) return '尚无记录'
  const label = attemptLabels[row.last.result] || row.last.result
  return [label, stamp(row.last.at), row.last.code].filter(Boolean).join(' · ')
}
const lastTone = (row: TargetRow) =>
  !row.last
    ? 'none'
    : row.last.result === 'success'
      ? 'ok'
      : row.last.result === 'permanent_error'
        ? 'fail'
        : 'warn'
const targetIssue = (row: TargetRow) =>
  targetActive(row) && (lastTone(row) === 'fail' || lastTone(row) === 'warn')

const openHotlists = ref(false)
function hotlistLine(site: HotlistSite) {
  const abnormal = site.lists.find((item) => severe(item.tone))
  if (abnormal)
    return { tone: abnormal.tone, text: abnormal.period_label + '：' + listText(abnormal) }
  if (site.lists.every((item) => item.tone === 'ok'))
    return { tone: 'ok', text: site.lists.length + ' 个榜单 · 最近刷新正常' }
  return { tone: site.lists[0]?.tone ?? 'none', text: listText(site.lists[0]!) }
}
function listText(item: HotlistSite['lists'][number]) {
  return [item.label, nodeDetail(item)].filter(Boolean).join(' · ')
}

function serviceText(row: ServiceRow) {
  switch (row.state) {
    case 'running':
      return '运行中 · 最近完成循环 ' + stamp(row.last_loop_at)
    case 'stalled':
      return row.last_loop_at
        ? '循环已 ' + elapsed(nowSeconds() - row.last_loop_at) + '未完成'
        : '循环尚未完成'
    case 'failed':
      return '已停止'
    case 'stopped_with':
      return '随' + (row.stopped_with || '其他服务') + '停止'
    default:
      return '状态未知'
  }
}
const serviceTone = (row: ServiceRow) =>
  row.state === 'running'
    ? 'ok'
    : row.state === 'stalled'
      ? 'warn'
      : row.state === 'unknown'
        ? 'none'
        : 'fail'
const alertsOff = computed(
  () => !!data.value && (!data.value.alerts.enabled || !data.value.alerts.ready_targets),
)

const statusLabels: Record<ProblemRow['status'], string> = {
  ongoing: '进行中',
  recovered: '已恢复',
  paused: '已暂停',
}
const statusTones: Record<ProblemRow['status'], string> = {
  ongoing: 'fail',
  recovered: 'ok',
  paused: 'none',
}
function lastedText(row: ProblemRow) {
  if (row.ended_at) return elapsed(row.ended_at - row.started_at)
  if (row.status === 'paused') return '暂停时未恢复'
  if (row.status === 'ongoing') return elapsed(nowSeconds() - row.started_at)
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
  <div class="ops-toolbar">
    <span v-if="data" class="ops-observed">观测于 {{ clock(data.checked_at) }}</span>
    <button class="button" :disabled="status.loading.value" @click="refresh">
      <Icon name="refresh" :size="14" />刷新
    </button>
  </div>
  <ReadRegion
    :loading="status.loading.value"
    :error="status.error.value"
    :has-data="!!data"
    :stale="status.stale.value"
    :min-height="360"
    @retry="status.reload"
  >
    <div v-if="data" class="ops-stack">
      <section v-if="data.problems.length" class="panel" aria-labelledby="ops-problems">
        <h2 id="ops-problems" class="ops-title">
          当前问题 <span class="ops-count">{{ data.problems.length }}</span>
        </h2>
        <article v-for="problem in data.problems" :key="problem.key" class="ops-problem">
          <div class="ops-problem-copy">
            <div class="ops-problem-head">
              <strong>{{ problem.label }}</strong>
              <span class="small-badge" :class="handlingBadges[problem.status]">{{
                handlingLabels[problem.status]
              }}</span>
            </div>
            <p>{{ problemReason(problem) }}</p>
            <p class="ops-muted">{{ problemFacts(problem).join(' · ') }}</p>
          </div>
          <button class="button" @click="openProblem(problem)">查看详情</button>
        </article>
        <p v-if="alertsOff" class="ops-note">
          系统告警未启用或没有可用目标，出现故障时不会收到通知。
          <button class="text-link" @click="emit('navigate', '/settings/alerts')">去设置</button>
        </p>
      </section>
      <section v-else class="panel ops-clear">
        <strong class="tone-ok">当前没有需要处理的问题</strong>
        <span v-if="alertsOff" class="tone-wait">
          系统告警未启用或没有可用目标，出现故障时不会收到通知
          <button class="text-link" @click="emit('navigate', '/settings/alerts')">去设置</button>
        </span>
      </section>

      <section class="panel ops-section" aria-labelledby="ops-sources">
        <h2 id="ops-sources" class="ops-title-inline">采集链路 <small>按网站</small></h2>
        <div v-if="!data.sources.length" class="ops-empty">
          <span>还没有添加监控网站。</span>
          <button class="button" @click="emit('navigate', '/websites')">添加网站</button>
        </div>
        <template v-else>
          <div class="ops-head ops-source-grid" aria-hidden="true">
            <span>网站</span><span>调度</span><span>抓取</span><span>解析</span><span>最近一轮</span
            ><span>最近成功</span><span>下次尝试</span>
          </div>
          <article
            v-for="row in data.sources"
            :key="row.website_id"
            class="ops-row ops-source-grid"
            :class="{ open: rowOpen('s' + row.website_id, sourceIssue(row)) }"
          >
            <div class="ops-row-name">
              <button class="text-link" @click="emit('navigate', '/websites/' + row.website_id)">
                {{ row.name }}
              </button>
              <small v-if="row.gap_at" class="tone-wait">可能漏帖 {{ stamp(row.gap_at) }}</small>
              <button
                class="ops-toggle"
                :aria-expanded="rowOpen('s' + row.website_id, sourceIssue(row))"
                :aria-label="row.name + '：' + sourceSummary(row)"
                @click="toggleRow('s' + row.website_id)"
              >
                <span :class="sourceIssue(row) ? 'tone-fail' : 'tone-ok'">{{
                  sourceSummary(row)
                }}</span>
                <Icon name="down" :size="14" />
              </button>
            </div>
            <div class="ops-row-body">
              <div
                v-for="item in sourceNodes(row)"
                :key="item.key"
                class="ops-node"
                :class="{ blocked: item.node.tone === 'fail' }"
              >
                <span class="ops-cell-label">{{ item.label }}</span>
                <div>
                  <strong :class="'tone-' + item.node.tone"
                    ><i class="ops-dot" />{{ item.node.label }}</strong
                  >
                  <small v-if="nodeDetail(item.node)">{{ nodeDetail(item.node) }}</small>
                </div>
              </div>
              <div class="ops-cell">
                <span class="ops-cell-label">最近成功</span>{{ stamp(row.last_success_at) }}
              </div>
              <div class="ops-cell">
                <span class="ops-cell-label">下次尝试</span>{{ stamp(row.next_attempt_at) }}
              </div>
            </div>
          </article>
        </template>
      </section>

      <section class="panel ops-section" aria-labelledby="ops-targets">
        <h2 id="ops-targets" class="ops-title-inline">
          通知链路 <small>按目标 · 没有待发不代表渠道已验证可用</small>
        </h2>
        <div v-if="!data.targets.length" class="ops-empty">
          <span>还没有通知目标。</span>
          <button class="button" @click="emit('navigate', '/target/new')">添加通知目标</button>
        </div>
        <template v-else>
          <div class="ops-head ops-target-grid" aria-hidden="true">
            <span>目标</span><span>状态</span><span>队列</span><span>发送中</span
            ><span>结果不确定</span><span>最近结果</span>
          </div>
          <article
            v-for="row in data.targets"
            :key="row.id"
            class="ops-row ops-target-grid"
            :class="{ open: rowOpen('t' + row.id, targetIssue(row)) }"
          >
            <div class="ops-row-name">
              <button
                class="text-link"
                @click="emit('navigate', '/operations/deliveries?target=' + row.id)"
              >
                {{ row.name }}
              </button>
              <button
                class="ops-toggle"
                :aria-expanded="rowOpen('t' + row.id, targetIssue(row))"
                :aria-label="row.name + '：' + lastText(row)"
                @click="toggleRow('t' + row.id)"
              >
                <span :class="'tone-' + lastTone(row)">{{
                  targetActive(row) ? lastText(row) : targetStatus[row.status]
                }}</span>
                <Icon name="down" :size="14" />
              </button>
            </div>
            <div class="ops-row-body">
              <div class="ops-cell" :class="targetActive(row) ? 'tone-ok' : 'tone-none'">
                <span class="ops-cell-label">状态</span>{{ targetStatus[row.status] }}
              </div>
              <div class="ops-cell">
                <span class="ops-cell-label">队列</span>{{ queueText(row) }}
              </div>
              <div class="ops-cell">
                <span class="ops-cell-label">发送中</span>{{ sendingText(row) }}
              </div>
              <div class="ops-cell">
                <span class="ops-cell-label">结果不确定</span
                >{{ targetActive(row) ? row.uncertain : '—' }}
              </div>
              <div class="ops-cell" :class="'tone-' + lastTone(row)">
                <span class="ops-cell-label">最近结果</span>{{ lastText(row) }}
              </div>
            </div>
          </article>
        </template>
      </section>

      <div class="ops-pair">
        <section class="panel ops-section" aria-labelledby="ops-hotlists">
          <div class="ops-card-head">
            <h2 id="ops-hotlists" class="ops-title-inline">热榜</h2>
            <button
              v-if="data.hotlists.length"
              class="text-link"
              :aria-expanded="openHotlists"
              @click="openHotlists = !openHotlists"
            >
              {{ openHotlists ? '收起各榜' : '展开各榜' }}
            </button>
          </div>
          <p v-if="!data.hotlists.length" class="ops-muted">热榜模块未显示，当前不刷新。</p>
          <template v-for="site in data.hotlists" :key="site.website_id">
            <div class="ops-line">
              <strong>{{ site.name }}</strong>
              <span :class="'tone-' + hotlistLine(site).tone">{{ hotlistLine(site).text }}</span>
            </div>
            <template v-if="openHotlists">
              <div v-for="item in site.lists" :key="item.period" class="ops-line ops-subline">
                <span>{{ item.period_label }}</span>
                <span :class="'tone-' + item.tone">{{ listText(item) }}</span>
              </div>
            </template>
          </template>
        </section>
        <section class="panel ops-section" aria-labelledby="ops-services">
          <h2 id="ops-services" class="ops-title-inline">后台服务</h2>
          <div v-for="row in data.services" :key="row.id" class="ops-line">
            <strong>{{ row.name }}</strong>
            <span :class="'tone-' + serviceTone(row)">{{ serviceText(row) }}</span>
          </div>
        </section>
      </div>

      <section class="panel ops-section" aria-labelledby="ops-history">
        <div class="ops-card-head ops-history-head">
          <h2 id="ops-history" class="ops-title-inline">问题历史</h2>
          <div class="ops-filters">
            <label class="ops-check"
              ><input v-model="showShort" type="checkbox" />显示 1 分钟内自动恢复的问题</label
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
              <span>状态</span><span>对象</span><span>原因</span><span>开始</span><span>持续</span
              ><span>系统告警</span>
            </div>
            <button
              v-for="row in history.data.value.items"
              :key="row.id"
              class="ops-history-row ops-history-grid"
              :aria-label="'查看问题：' + row.label"
              @click="openHistory(row)"
            >
              <span :class="'tone-' + statusTones[row.status]">{{ statusLabels[row.status] }}</span>
              <span>{{ row.label }}</span>
              <span
                >{{ row.summary }}<template v-if="row.code"> · {{ row.code }}</template></span
              >
              <span>{{ stamp(row.started_at) }}</span>
              <span>{{ lastedText(row) }}</span>
              <span class="ops-muted">{{ alertSummary(row.alerts) }}</span>
            </button>
            <p v-if="!history.data.value.total" class="ops-muted">
              这段时间没有记录到问题。记录按历史保留策略清理。
            </p>
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
.ops-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  color: #5d6673;
}
.ops-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ops-title {
  margin: 0;
  padding: 14px 20px;
  font-size: 15px;
  font-weight: 600;
}
.ops-count {
  font-weight: 400;
  color: #5d6673;
}
.ops-problem {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 24px;
  padding: 14px 20px;
  border-top: 1px solid #e9ebee;
}
.ops-problem-copy {
  flex: 1 1 420px;
  min-width: 0;
}
.ops-problem-copy p {
  margin: 0;
  overflow-wrap: anywhere;
}
.ops-problem-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.ops-muted,
.ops-problem-copy .ops-muted {
  color: #5d6673;
  font-size: 12px;
}
.ops-note {
  margin: 0;
  padding: 10px 20px;
  border-top: 1px solid #e9ebee;
  color: #8a5a0b;
}
.ops-clear {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 6px 16px;
  padding: 14px 20px;
}
.ops-section {
  padding: 14px 20px 16px;
}
.ops-title-inline {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
}
.ops-title-inline small {
  font-weight: 400;
  font-size: 12px;
  color: #5d6673;
}
.ops-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #5d6673;
}
.ops-head {
  color: #5d6673;
  font-size: 12px;
  padding-bottom: 6px;
}
.ops-source-grid {
  display: grid;
  grid-template-columns: 150px repeat(3, minmax(0, 1fr)) minmax(0, 1.7fr) 96px 96px;
  gap: 8px;
  align-items: center;
}
.ops-target-grid {
  display: grid;
  grid-template-columns: 170px 90px minmax(0, 1.4fr) 90px 90px minmax(0, 1.6fr);
  gap: 8px;
  align-items: center;
}
.ops-history-grid {
  display: grid;
  grid-template-columns: 70px minmax(0, 1.2fr) minmax(0, 1.5fr) 96px 110px minmax(0, 0.8fr);
  gap: 8px;
}
.ops-row {
  padding: 8px 0;
  border-top: 1px solid #f0f1f3;
  overflow-wrap: anywhere;
}
.ops-row-name {
  min-width: 0;
}
.ops-row-name > small {
  display: block;
}
.ops-row-body {
  display: contents;
}
.ops-toggle {
  display: none;
}
.ops-node {
  padding: 6px 10px;
  border-radius: 7px;
  min-width: 0;
}
.ops-node.blocked {
  background: #fbeef0;
}
.ops-node strong {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.ops-node small {
  display: block;
  font-size: 12px;
  color: #5d6673;
}
.ops-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.8;
}
.ops-cell {
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.ops-cell-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
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
  color: #5d6673;
}
.ops-pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}
.ops-card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
}
.ops-card-head .ops-title-inline {
  margin: 0;
}
.ops-history-head {
  margin-bottom: 10px;
}
.ops-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
}
.ops-line > :first-child {
  flex: none;
}
.ops-line > :last-child {
  text-align: right;
  overflow-wrap: anywhere;
}
.ops-subline {
  padding-left: 14px;
  color: #5d6673;
}
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
}
.ops-history-row {
  width: 100%;
  padding: 9px 0;
  border: 0;
  border-top: 1px solid #f0f1f3;
  background: transparent;
  text-align: left;
  overflow-wrap: anywhere;
}
.ops-history-row:hover {
  background: #fafbfc;
}
/* The fixed columns no longer fit beside the sidebar on a medium screen. */
@media (max-width: 1100px) {
  .ops-source-grid,
  .ops-target-grid {
    display: block;
  }
  .ops-head.ops-head {
    display: none;
  }
  .ops-row-body {
    display: none;
  }
  .ops-row.open .ops-row-body {
    display: block;
  }
  .ops-toggle {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    width: 100%;
    min-height: 44px;
    padding: 0;
    border: 0;
    background: none;
    text-align: left;
  }
  .ops-cell-label {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip-path: none;
    color: #5d6673;
    flex: none;
  }
  .ops-node,
  .ops-cell {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 0;
    border-radius: 0;
    text-align: right;
  }
  .ops-node.blocked {
    background: none;
  }
  .ops-node strong {
    justify-content: flex-end;
  }
  .ops-history-grid {
    grid-template-columns: 56px minmax(0, 1fr);
  }
  .ops-history-row > :nth-child(n + 3):not(:nth-child(6)) {
    grid-column: 2;
  }
  .ops-history-row > :nth-child(6) {
    grid-column: 2;
  }
  .ops-pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
