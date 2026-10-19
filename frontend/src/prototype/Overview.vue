<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from './components/Icon.vue'
import Toggle from './components/Toggle.vue'
import { targets } from './model'
import type { Task } from './model'
const props = defineProps<{ tasks: Task[] }>()
const emit = defineEmits<{
  edit: [id: string]
  create: []
  toggle: [id: string]
  notice: [message: string]
}>()
const range = ref('24h'),
  query = ref(''),
  filter = ref('all')
const active = computed(() => props.tasks.filter((task) => task.enabled).length)
const filtered = computed(() =>
  props.tasks.filter(
    (task) =>
      task.name.toLowerCase().includes(query.value.toLowerCase()) &&
      (filter.value === 'all' || (filter.value === 'active' ? task.enabled : !task.enabled)),
  ),
)
const daily = [0, 1, 0, 0, 1, 0, 2, 1, 3, 2, 1, 4, 2, 3, 1, 2, 4, 2, 1, 3, 2, 4, 2, 1]
const weekly = [29, 36, 24, 48, 32, 57, 42]
const chart = computed(() => (range.value === '24h' ? daily : weekly))
const total = computed(() => chart.value.reduce((sum, value) => sum + value, 0))
const graph = computed(() =>
  chart.value
    .map(
      (value, i) =>
        ((i * 700) / (chart.value.length - 1)).toFixed(1) +
        ',' +
        (154 - (value / (range.value === '24h' ? 5 : 60)) * 126).toFixed(1),
    )
    .join(' '),
)
const selectedPoint = ref<number | null>(null)
function setRange(value: string) {
  range.value = value
  selectedPoint.value = null
}
function clearFilters() {
  query.value = ''
  filter.value = 'all'
}
const activities = [
  {
    title: 'DMIT 洛杉矶套餐补货，附本次优惠信息',
    task: '好价服务器雷达',
    category: '优惠',
    time: '14:28',
    icon: 'spark',
    color: 'orange',
    state: '已送达',
    status: 'yes',
  },
  {
    title: '分享一个轻量的 Docker 自托管面板',
    task: '自托管灵感收集',
    category: '技术',
    time: '14:12',
    icon: 'code',
    color: 'purple',
    state: '已送达',
    status: 'yes',
  },
  {
    title: '三条线路的晚高峰体验与测评记录',
    task: '网络与线路观察',
    category: '测评',
    time: '13:54',
    icon: 'globe',
    color: 'blue',
    state: '等待重试',
    status: 'unknown',
  },
]
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">YOUR SIGNAL, LESS NOISE</p>
      <h1 tabindex="-1">每一条在意的，都不错过<span class="heading-dot">。</span></h1>
      <p class="subtitle">让 SeekBell 留意新帖，把时间留给更重要的事。</p>
    </div>
    <button class="button primary" @click="emit('create')">
      <Icon name="plus" :size="18" />新建任务
    </button>
  </section>
  <div class="overview-meta">
    <span
      ><span class="status-dot green-dot" />监控运行中 <span class="separator">/</span>
      <strong>NodeSeek</strong> 官方 RSS</span
    ><span class="muted">演示快照 · 10 月 19 日 14:30</span>
  </div>
  <section class="stats-grid" aria-label="概览统计">
    <article class="stat-card">
      <div class="stat-label">运行中的任务<Icon name="layers" :size="18" /></div>
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
      <div class="stat-value">
        {{ total }}<span>条</span
        ><span class="stat-accent">捕获新信号 <Icon name="spark" :size="15" /></span>
      </div>
      <p>按任务累计，含同帖多任务命中</p>
    </article>
    <article class="stat-card">
      <div class="stat-label">成功投递<Icon name="send" :size="18" /></div>
      <div class="stat-value">
        {{ range === '24h' ? 38 : 249 }}<span>次</span
        ><span class="mini-bars" aria-hidden="true"
          ><i
            v-for="(height, i) in [10, 18, 13, 22, 16, 25, 21, 30, 25]"
            :key="i"
            :style="{ height: height + 'px' }"
        /></span>
      </div>
      <p>按帖子与目标合并后统计</p>
    </article>
    <article class="stat-card">
      <div class="stat-label">待关注的投递<Icon name="alert" :size="18" /></div>
      <div class="stat-value">1<span>次</span><span class="small-badge amber">正在重试</span></div>
      <p>模拟：Bark 服务暂时不可达</p>
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
          selectedPoint !== null
            ? (range === '24h' ? selectedPoint + ':00' : '10 月 ' + (13 + selectedPoint) + ' 日') +
              ' · ' +
              chart[selectedPoint] +
              ' 条'
            : '合计 ' + total + ' 条'
        }}</span>
      </div>
      <div class="chart-wrap">
        <div class="chart-y">
          <span>{{ range === '24h' ? 5 : 60 }}</span
          ><span>{{ range === '24h' ? 3 : 30 }}</span
          ><span>0</span>
        </div>
        <svg
          class="trend-chart"
          viewBox="0 0 700 175"
          preserveAspectRatio="none"
          role="img"
          :aria-label="'模拟命中趋势，合计 ' + total + ' 条'"
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
            :cx="(i * 700) / (chart.length - 1)"
            :cy="154 - (value / (range === '24h' ? 5 : 60)) * 126"
            r="5"
            fill="#fff"
            stroke="#db7843"
            stroke-width="2"
            class="chart-point"
            @mouseenter="selectedPoint = i"
            @mouseleave="selectedPoint = null"
          >
            <title>
              {{ range === '24h' ? i + ':00' : '10 月 ' + (13 + i) + ' 日' }}：{{ value }} 条
            </title>
          </circle>
        </svg>
      </div>
      <div class="chart-x">
        <span
          v-for="label in range === '24h'
            ? ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '23:00']
            : ['10/13', '10/14', '10/15', '10/16', '10/17', '10/18', '10/19']"
          :key="label"
          >{{ label }}</span
        >
      </div>
    </section>
    <section class="panel source-panel">
      <div class="panel-heading">
        <h2>采集状态</h2>
        <span class="live-label"><span class="status-dot green-dot" /> 正常</span>
      </div>
      <div class="source-identity">
        <div class="source-logo">N<span>›</span></div>
        <div>
          <h3>NodeSeek</h3>
          <p>官方 RSS · 唯一采集来源</p>
        </div>
        <Icon name="globe" :size="18" />
      </div>
      <dl class="source-data">
        <div>
          <dt>最近成功采集</dt>
          <dd>14:29:56</dd>
        </div>
        <div>
          <dt>采集间隔</dt>
          <dd>10 <span>秒</span></dd>
        </div>
        <div>
          <dt>本日发现新帖</dt>
          <dd>286 <span>条</span></dd>
        </div>
      </dl>
      <div class="uptime-bars" aria-label="最近 30 次模拟采集均成功">
        <i v-for="n in 30" :key="n" />
      </div>
      <div class="uptime-label"><span>最近 30 次采集</span><span>全部成功</span></div>
      <p class="source-note"><Icon name="shield" :size="15" />全部任务共享采集，不重复请求</p>
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
          <option value="active">运行中</option>
          <option value="paused">已暂停</option>
        </select>
      </div>
    </div>
    <div class="task-table-head">
      <span>任务名称</span><span>通知目标</span><span>今日命中</span><span>最近命中</span
      ><span>状态</span><span />
    </div>
    <div v-for="task in filtered" :key="task.id" class="task-row">
      <button class="task-name" @click="emit('edit', task.id)">
        <span class="icon-tile" :class="task.color"><Icon :name="task.icon" /></span
        ><span
          ><strong>{{ task.name }}</strong
          ><small>{{ task.description || 'NodeSeek · 新帖监控' }}</small></span
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
      <span class="task-hits">{{ task.hits }}<small class="mobile-only"> 今日命中</small></span
      ><span class="muted task-time">{{ task.lastHit }}</span>
      <div class="task-status">
        <Toggle
          :model-value="task.enabled"
          :label="task.name + '启用状态'"
          @update:model-value="emit('toggle', task.id)"
        /><span>{{ task.enabled ? '运行中' : '已暂停' }}</span>
      </div>
      <button
        class="icon-button task-edit"
        :aria-label="'编辑' + task.name"
        @click="emit('edit', task.id)"
      >
        <Icon name="arrow" :size="17" />
      </button>
    </div>
    <div v-if="!filtered.length" class="empty-state">
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
      <span class="small-badge neutral">模拟内容</span>
    </div>
    <div v-for="(item, index) in activities" :key="item.title" class="activity-row">
      <span class="timeline-dot" :class="item.color"><Icon :name="item.icon" :size="17" /></span>
      <div class="activity-copy">
        <button
          @click="
            emit(
              'notice',
              '模拟帖子 ' + (index + 1) + '：' + item.title + '。此原型不打开真实论坛。',
            )
          "
        >
          {{ item.title }}
        </button>
        <p>
          <span>{{ item.category }}</span
          ><span>{{ item.task }}</span
          ><span>NodeSeek</span>
        </p>
      </div>
      <span class="result-pill" :class="item.status"
        ><span class="status-dot" />{{ item.state }}</span
      ><time>{{ item.time }}</time>
    </div>
  </section>
  <footer class="page-footer">
    <span><Icon name="bell" :size="14" /> SeekBell · 留意你关心的</span
    ><span>本地交互原型 <span class="separator">·</span> v0.1</span>
  </footer>
</template>
