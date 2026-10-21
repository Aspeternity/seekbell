<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import Toggle from '../prototype/components/Toggle.vue'
import { state, request, formatTime, websiteName, setTaskEnabled } from './store'
import { useRemote } from './history'
import type { OverviewData } from './overview'
import Feedback from './Feedback.vue'
const emit = defineEmits<{ navigate: [path: string] }>()
const range = ref<'24h' | '7d'>('24h'),
  query = ref(''),
  filter = ref('all')
const selectedPoint = ref<number | null>(null)
const remote = useRemote(
  () => request<OverviewData>('manage/overview?range=' + range.value),
  () => [range.value],
)
const data = remote.data
const stamp = (value: number | null) =>
  value === null ? '尚未记录' : formatTime(new Date(value * 1000).toISOString())
const tasks = computed(() =>
  state.tasks.map((task) => {
    const stats = data.value?.tasks.find((row) => row.id === task.id)
    return { ...task, hits: stats?.matches ?? 0, lastHit: stamp(stats?.last_match_at ?? null) }
  }),
)
const active = computed(() => data.value?.configuration.enabled_tasks || 0)
const targets = computed(() => state.targets)
const filtered = computed(() =>
  tasks.value.filter(
    (task) =>
      task.name.toLowerCase().includes(query.value.toLowerCase()) &&
      (filter.value === 'all' || (filter.value === 'active' ? task.enabled : !task.enabled)),
  ),
)
const chart = computed(() => data.value?.buckets.map((bucket) => bucket.matches) || [])
const maximum = computed(() => Math.max(1, ...chart.value))
const total = computed(() => data.value?.window.matches || 0)
const attentionCount = computed(() => data.value?.current.attention || 0)
const graph = computed(() =>
  chart.value
    .map(
      (value, i) =>
        ((i + 0.5) * 700) / chart.value.length + ',' + (154 - (value / maximum.value) * 126),
    )
    .join(' '),
)
const selected = computed(() =>
  selectedPoint.value === null ? null : data.value?.buckets[selectedPoint.value],
)
const chartLabels = computed(() =>
  data.value
    ? Array.from({ length: 7 }, (_, i) => {
        const label = stamp(data.value!.start + ((data.value!.end - data.value!.start) * i) / 6)
        return range.value === '24h' ? label.split(' ').at(-1)! : label.split(' ')[0]!
      })
    : [],
)
const websites = computed(
  () =>
    data.value?.sources.map((source) => ({
      ...source,
      id: source.website_id,
      health: source.failures ? 'error' : source.last_success_at === null ? 'waiting' : 'healthy',
    })) || [],
)
const activities = computed(() => data.value?.recent_matches || [])
function setRange(value: '24h' | '7d') {
  range.value = value
  selectedPoint.value = null
}
function clearFilters() {
  query.value = ''
  filter.value = 'all'
}
async function toggle(id: string) {
  const task = state.tasks.find((task) => task.id === id)
  if (task) {
    await setTaskEnabled(task, !task.enabled)
    remote.reload()
  }
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">YOUR SIGNAL, LESS NOISE</p>
      <h1 tabindex="-1">每一条在意的，都不错过<span class="heading-dot">。</span></h1>
      <p class="subtitle">让 SeekBell 留意新帖，把时间留给更重要的事。</p>
    </div>
  </section>
  <div class="overview-meta">
    <span
      ><span class="status-dot" />{{
        state.websites.length
          ? '已添加 ' + state.websites.length + ' 个网站'
          : '等待添加第一个网站'
      }}<span class="separator">/</span
      >{{ state.websites.filter((w) => w.enabled).length }} 个已启用</span
    ><button
      class="text-link"
      aria-label="刷新概览"
      :disabled="remote.loading.value"
      @click="remote.reload"
    >
      刷新概览<span v-if="data"> · {{ stamp(data.end) }}</span>
    </button>
  </div>
  <Feedback :loading="remote.loading.value" :error="remote.error.value" @retry="remote.reload" />
  <template v-if="data">
    <div v-if="!data.runtime_active && data.runtime.status !== 'failed'" class="warning-note">
      <Icon name="clock" :size="18" /><span
        >后台采集与通知发送尚未启动。已启用的配置不会自动执行。</span
      >
    </div>
    <p v-if="data.runtime.status === 'failed'" class="form-errors" role="alert">
      后台任务已停止（{{ data.runtime.code }}），请检查服务；数据库历史仍可读取。
    </p>
    <section v-if="!state.websites.length" class="panel overview-welcome">
      <span class="icon-tile orange"><Icon name="globe" /></span>
      <div>
        <h2>先选择你想关注的网站</h2>
        <p>从内置网站库按需添加，再创建规则和通知。首次部署不会默认启用任何网站。</p>
      </div>
      <button class="button primary" @click="emit('navigate', '/websites')">
        添加网站<Icon name="plus" :size="16" />
      </button>
    </section>
    <div
      v-else-if="state.websites.some((w) => !w.enabled || w.health === 'error')"
      class="warning-note"
    >
      <Icon name="alert" :size="18" /><span>{{
        state.websites.some((w) => w.enabled && w.health === 'error')
          ? '来源连接异常，请检查采集设置。'
          : '部分网站已暂停，关联任务暂不采集新帖。'
      }}</span
      ><button class="text-link" @click="emit('navigate', '/websites')">查看网站</button>
    </div>
    <section class="stats-grid" aria-label="概览统计">
      <article class="stat-card">
        <div class="stat-label">已启用任务<Icon name="layers" :size="18" /></div>
        <div class="stat-value">
          {{ active }}<span>/ {{ tasks.length }}</span
          ><svg class="mini-chart" viewBox="0 0 92 32" aria-hidden="true">
            <path d="M1 27H16V20H30V23H44V13H58V17H74V5H91" />
          </svg>
        </div>
        <p><span class="status-dot green-dot" /> {{ tasks.length - active }} 个任务已暂停</p>
      </article>
      <article class="stat-card">
        <div class="stat-label">
          {{ range === '24h' ? '近 24 小时' : '近 7 天' }}命中<Icon name="activity" :size="18" />
        </div>
        <div class="stat-value" data-testid="overview-matches">
          {{ total }}<span>条</span
          ><span class="stat-accent">捕获新信号 <Icon name="spark" :size="15" /></span>
        </div>
        <p>按任务版本累计，含同帖多任务命中</p>
      </article>
      <article class="stat-card">
        <div class="stat-label">成功投递<Icon name="send" :size="18" /></div>
        <div
          class="stat-value"
          data-testid="overview-delivered"
          title="渠道已接受；不代表收件箱送达"
        >
          {{ data.window.delivered }}<span>次</span
          ><span class="mini-bars" aria-hidden="true"
            ><i
              v-for="(height, i) in chart
                .slice(-9)
                .map((value) => Math.max(2, (value / maximum) * 30))"
              :key="i"
              :style="{ height: height + 'px' }"
          /></span>
        </div>
        <p>渠道接受回执，按帖子与目标去重</p>
      </article>
      <article class="stat-card">
        <div class="stat-label">待关注的投递<Icon name="alert" :size="18" /></div>
        <div class="stat-value" data-testid="overview-attention">
          {{ attentionCount }}<span>次</span><span class="small-badge amber">需关注</span>
        </div>
        <p>查看通知管理中的异常与重试记录</p>
      </article>
    </section>
    <div class="overview-columns">
      <section class="panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>命中趋势</h2>
            <p>关心的内容，正在被发现</p>
          </div>
          <div class="segmented compact" aria-label="统计范围">
            <button
              :class="{ active: range === '24h' }"
              :aria-pressed="range === '24h'"
              @click="setRange('24h')"
            >
              24 小时</button
            ><button
              :class="{ active: range === '7d' }"
              :aria-pressed="range === '7d'"
              @click="setRange('7d')"
            >
              7 天
            </button>
          </div>
        </div>
        <div class="chart-legend">
          <span><i />任务命中</span
          ><span class="muted">{{
            selected
              ? stamp(selected.start) +
                ' 至 ' +
                stamp(selected.end) +
                ' · ' +
                selected.matches +
                ' 条'
              : '合计 ' + total + ' 条'
          }}</span>
        </div>
        <div
          class="chart-wrap"
          :title="'统计时段：' + stamp(data.start) + ' 至 ' + stamp(data.end) + '（左闭右开）'"
        >
          <div class="chart-y">
            <span>{{ maximum }}</span
            ><span>{{ maximum / 2 }}</span
            ><span>0</span>
          </div>
          <svg
            class="trend-chart"
            viewBox="0 0 700 175"
            preserveAspectRatio="none"
            role="img"
            :aria-label="'命中趋势，合计 ' + total + ' 条'"
          >
            <defs>
              <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#e78a52" stop-opacity=".20" />
                <stop offset="100%" stop-color="#e78a52" stop-opacity=".015" />
              </linearGradient>
            </defs>
            <path d="M0 28H700M0 91H700M0 154H700" class="chart-grid" />
            <polygon :points="'0,154 ' + graph + ' 700,154'" fill="url(#area)" />
            <polyline
              :points="graph"
              fill="none"
              stroke="#db7843"
              stroke-width="2.5"
              vector-effect="non-scaling-stroke"
            />
            <circle
              v-for="(value, i) in chart"
              :key="i"
              :cx="((i + 0.5) * 700) / chart.length"
              :cy="154 - (value / maximum) * 126"
              r="5"
              fill="#fff"
              stroke="#db7843"
              stroke-width="2"
              class="chart-point"
              tabindex="0"
              @focus="selectedPoint = i"
              @blur="selectedPoint = null"
              @mouseenter="selectedPoint = i"
              @mouseleave="selectedPoint = null"
            >
              <title>
                {{ stamp(data.buckets[i]!.start) }} 至 {{ stamp(data.buckets[i]!.end) }}：{{
                  value
                }}
                条
              </title>
            </circle>
          </svg>
        </div>
        <div class="chart-x">
          <span v-for="label in chartLabels" :key="label">{{ label }}</span>
        </div>
      </section>
      <section class="panel source-panel">
        <div class="panel-heading">
          <h2>网站采集</h2>
          <button class="text-link" @click="emit('navigate', '/websites')">
            管理网站<Icon name="arrow" :size="14" />
          </button>
        </div>
        <div v-if="!state.websites.length" class="empty-state">
          <Icon name="globe" :size="30" />
          <h3>还没有监控网站</h3>
          <p>添加后，在这里查看各个网站的状态。</p>
        </div>
        <div v-for="w in websites" :key="w.id" class="overview-website-row overview-source">
          <span class="icon-tile orange"><Icon name="globe" :size="18" /></span
          ><span
            ><strong>{{ websiteName(w.id) }}</strong
            ><small>{{ stamp(w.last_success_at) }}</small></span
          ><span
            class="result-pill"
            :class="!w.enabled ? 'neutral' : w.health === 'healthy' ? 'yes' : 'unknown'"
            >{{
              !w.enabled
                ? '已暂停'
                : w.health === 'error'
                  ? '异常'
                  : w.health === 'healthy'
                    ? '正常'
                    : '待采集'
            }}</span
          >
        </div>
        <p class="source-note"><Icon name="shield" :size="15" />各网站独立配置，同站任务共享采集</p>
        <details class="advanced overview-diagnostics">
          <summary>采集与运行详情</summary>
          <div v-for="source in data.sources" :key="source.source_id" class="small-note">
            <strong>{{ source.name }}</strong>
            <p>
              最后尝试：{{ stamp(source.last_attempt_at) }} · 连续失败 {{ source.failures
              }}{{ source.error_code ? ' · ' + source.error_code : '' }}
            </p>
            <p>下次可尝试：{{ stamp(source.next_attempt_at) }}</p>
            <p v-if="source.possible_gap">曾发现可能缺口：{{ stamp(source.last_gap_at) }}</p>
          </div>
          <p class="small-note">
            本地帖子 {{ data.window.posts }} · 信息不足 {{ data.window.insufficient_data }} ·
            采集失败 {{ data.window.source_failures }}
          </p>
          <p class="small-note">
            自动队列：等待 {{ data.current.queue.pending || 0 }} · 重试
            {{ data.current.queue.retry || 0 }} · 在途 {{ data.current.queue.leased || 0 }} · 曾未知
            {{ data.current.uncertain }}
          </p>
        </details>
      </section>
    </div>
    <section class="panel tasks-panel">
      <div class="panel-heading">
        <div class="inline-title">
          <h2>监控任务</h2>
          <span class="count-badge">{{ tasks.length }}</span>
        </div>
        <div class="task-tools">
          <label class="search-input"
            ><Icon name="search" :size="16" /><input
              v-model="query"
              aria-label="搜索任务"
              placeholder="搜索任务…" /></label
          ><select v-model="filter" aria-label="筛选任务状态">
            <option value="all">全部状态</option>
            <option value="active">已启用</option>
            <option value="paused">已暂停</option>
          </select>
        </div>
      </div>
      <div class="task-table-head">
        <span>任务名称</span><span>通知目标</span
        ><span>{{ range === '24h' ? '近24小时命中' : '近7天命中' }}</span
        ><span>最近命中</span><span>状态</span><span />
      </div>
      <div v-for="task in filtered" :key="task.id" class="task-row">
        <button class="task-name" @click="emit('navigate', '/task/' + task.id)">
          <span class="icon-tile" :class="task.color"><Icon :name="task.icon" /></span
          ><span
            ><strong>{{ task.name }}</strong
            ><small>{{
              task.description || websiteName(task.websiteId) + ' · 新帖监控'
            }}</small></span
          >
        </button>
        <div class="target-icons">
          <span
            v-for="target in targets.filter((t) => task.targets.includes(t.id))"
            :key="target.id"
            :title="target.name"
            class="target-icon"
            :class="target.color"
            ><Icon :name="target.icon" :size="16" /><span class="sr-only">{{
              target.name
            }}</span></span
          >
        </div>
        <span class="task-hits"
          >{{ task.hits
          }}<small class="mobile-only">
            {{ range === '24h' ? '近24小时命中' : '近7天命中' }}</small
          ></span
        ><span class="muted task-time">{{ task.lastHit }}</span>
        <div class="task-status">
          <Toggle
            :model-value="task.enabled"
            :label="task.name + '启用状态'"
            @update:model-value="toggle(task.id)"
          /><span>{{ task.enabled ? '已启用' : '已暂停' }}</span>
        </div>
        <button
          class="icon-button task-edit"
          :aria-label="'编辑' + task.name"
          @click="emit('navigate', '/task/' + task.id)"
        >
          <Icon name="arrow" :size="17" />
        </button>
      </div>
      <div v-if="!tasks.length" class="empty-state">
        <Icon name="layers" :size="28" />
        <h3>还没有监控任务</h3>
        <p>添加网站后，为你关心的内容设置一条规则。</p>
      </div>
      <div v-else-if="!filtered.length" class="empty-state">
        <Icon name="search" :size="28" />
        <h3>没有找到匹配的任务</h3>
        <p>试试其他关键词，或查看全部状态。</p>
        <button class="button" @click="clearFilters">清除筛选</button>
      </div>
      <div class="table-footer">
        <span>显示 {{ filtered.length }} 个任务</span
        ><span><Icon name="help" :size="14" />暂停后恢复，不补发期间的帖子</span>
      </div>
    </section>
    <section class="panel activity-panel">
      <div class="panel-heading">
        <div>
          <h2>最近命中</h2>
          <p>从信息流中，找到与你有关的内容</p>
        </div>
        <button class="text-link" @click="emit('navigate', '/content')">查看内容与命中</button>
      </div>
      <div v-for="(item, index) in activities" :key="index" class="activity-row">
        <span class="timeline-dot orange"><Icon name="spark" :size="17" /></span>
        <div class="activity-copy">
          <button v-if="item.post_id" @click="emit('navigate', '/content/' + item.post_id)">
            {{ item.title }}</button
          ><strong v-else>原内容已清理</strong>
          <p>
            <span>{{ item.task_name }}</span
            ><span>版本 {{ item.task_version }}{{ item.task_deleted ? ' · 任务已删除' : '' }}</span>
          </p>
        </div>
        <span class="result-pill yes"><span class="status-dot" />命中</span
        ><time>{{ stamp(item.at) }}</time>
      </div>
      <div v-if="!activities.length" class="empty-state">
        <Icon name="inbox" :size="28" />
        <p>还没有命中记录。</p>
      </div>
    </section>
    <footer class="page-footer">
      <span><Icon name="bell" :size="14" /> SeekBell · 留意你关心的</span
      ><span>管理界面 <span class="separator">·</span> v0.4</span>
    </footer>
  </template>
</template>

<style scoped>
.chart-x,
.chart-legend {
  gap: 12px;
  flex-wrap: wrap;
}
.activity-copy {
  min-width: 0;
  overflow-wrap: anywhere;
}
.overview-diagnostics {
  margin: 0 20px 16px;
}
.overview-source > span:nth-child(2) {
  min-width: 0;
}
.overview-source strong,
.task-name strong {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .overview-source {
    flex-wrap: wrap;
  }
  .chart-x {
    font-size: 10px;
  }
}
</style>
