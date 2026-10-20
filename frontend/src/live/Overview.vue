<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import { state, request, formatTime } from './store'
import { useRemote } from './history'
import type { OverviewData } from './overview'
import Feedback from './Feedback.vue'
const emit = defineEmits<{ navigate: [path: string] }>()
const range = ref<'24h' | '7d'>('24h')
const selected = ref<number | null>(null)
const remote = useRemote(
  () => request<OverviewData>('manage/overview?range=' + range.value),
  () => [range.value],
)
const data = remote.data
const chart = computed(() => data.value?.buckets || [])
const maximum = computed(() => Math.max(1, ...chart.value.map((b) => b.matches)))
const graph = computed(() =>
  chart.value
    .map(
      (b, i) =>
        ((i + 0.5) * 700) / chart.value.length + ',' + (154 - (b.matches / maximum.value) * 126),
    )
    .join(' '),
)
const stamp = (value: number | null) =>
  value === null ? '尚未记录' : formatTime(new Date(value * 1000).toISOString())
const point = computed(() => (selected.value === null ? undefined : chart.value[selected.value]))
function setRange(value: '24h' | '7d') {
  selected.value = null
  range.value = value
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">YOUR SIGNAL, LESS NOISE</p>
      <h1 tabindex="-1">留意你关心的<span class="heading-dot">。</span></h1>
      <p class="subtitle">采集、命中与通知，都有迹可循。</p>
    </div>
    <button class="button primary" @click="emit('navigate', '/task/new')">
      <Icon name="plus" :size="18" />新建任务
    </button>
  </section>
  <div class="overview-meta">
    <span>服务端历史统计 · {{ state.settings.timezone }}</span>
    <button class="text-link" :disabled="remote.loading.value" @click="remote.reload">
      刷新概览
    </button>
  </div>
  <div class="segmented compact" aria-label="统计范围">
    <button
      :class="{ active: range === '24h' }"
      :aria-pressed="range === '24h'"
      @click="setRange('24h')"
    >
      24 小时
    </button>
    <button
      :class="{ active: range === '7d' }"
      :aria-pressed="range === '7d'"
      @click="setRange('7d')"
    >
      7 天
    </button>
  </div>
  <Feedback :loading="remote.loading.value" :error="remote.error.value" @retry="remote.reload" />
  <template v-if="data">
    <div v-if="!data.runtime_active" class="warning-note">
      <Icon name="clock" :size="18" /><span
        >后台采集与通知发送尚未启动。已启用的配置不会自动执行。</span
      >
    </div>
    <section v-if="!data.configuration.websites" class="panel overview-welcome">
      <span class="icon-tile orange"><Icon name="globe" /></span>
      <div>
        <h2>先选择你想关注的网站</h2>
        <p>从内置网站库添加，再创建规则和通知。</p>
      </div>
      <button class="button primary" @click="emit('navigate', '/websites')">
        添加网站<Icon name="plus" :size="16" />
      </button>
    </section>
    <p class="small-note overview-window">
      统计时段：{{ stamp(data.start) }} 至 {{ stamp(data.end) }}（左闭右开）；以下均为已保存记录。
    </p>
    <section class="stats-grid" aria-label="概览统计">
      <article class="stat-card">
        <div class="stat-label">已启用任务配置<Icon name="layers" :size="18" /></div>
        <div class="stat-value">
          {{ data.configuration.enabled_tasks }}<span>/ {{ data.configuration.tasks }}</span>
        </div>
        <p>
          {{ data.configuration.websites }} 个网站 · {{ data.configuration.targets }} 个通知目标
        </p>
      </article>
      <article class="stat-card">
        <div class="stat-label">
          {{ range === '24h' ? '近 24 小时' : '近 7 天' }}命中<Icon name="activity" :size="18" />
        </div>
        <div class="stat-value" data-testid="overview-matches">
          {{ data.window.matches }}<span>条</span>
        </div>
        <p>按任务版本累计，含同帖多任务命中</p>
      </article>
      <article class="stat-card">
        <div class="stat-label">自动渠道确认接受<Icon name="send" :size="18" /></div>
        <div class="stat-value" data-testid="overview-delivered">
          {{ data.window.delivered }}<span>次</span>
        </div>
        <p>自动投递按时段内回执；同帖与目标去重</p>
      </article>
      <article class="stat-card">
        <div class="stat-label">当前待关注自动投递<Icon name="alert" :size="18" /></div>
        <div class="stat-value" data-testid="overview-attention">
          {{ data.current.attention }}<span>次</span>
        </div>
        <p>全部自动记录：失败、重试或曾未知，按事件去重</p>
        <button class="text-link" @click="emit('navigate', '/notifications/deliveries')">
          查看投递记录
        </button>
      </article>
    </section>
    <div class="metric-strip">
      <div>
        <span>时段内本地帖子</span><strong>{{ data.window.posts }}</strong>
      </div>
      <div>
        <span>信息不足判定</span><strong>{{ data.window.insufficient_data }}</strong>
      </div>
      <div>
        <span>采集失败次数</span><strong>{{ data.window.source_failures }}</strong>
      </div>
      <p>
        自动队列：等待 {{ data.current.queue.pending || 0 }} · 重试
        {{ data.current.queue.retry || 0 }} · 在途 {{ data.current.queue.leased || 0 }} · 曾未知
        {{ data.current.uncertain }}
      </p>
    </div>
    <div class="overview-columns">
      <section class="panel chart-panel">
        <div class="panel-heading">
          <div>
            <h2>命中趋势</h2>
            <p>{{ range === '24h' ? '每点 1 小时' : '每点 24 小时' }}，从统计时段起点分桶</p>
          </div>
          <span class="small-badge neutral">真实记录</span>
        </div>
        <div class="chart-legend">
          <span><i />任务版本命中</span
          ><span class="muted">{{
            point
              ? stamp(point.start) + ' 至 ' + stamp(point.end) + ' · ' + point.matches + ' 条'
              : '合计 ' + data.window.matches + ' 条'
          }}</span>
        </div>
        <div class="chart-wrap">
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
            :aria-label="'服务端命中趋势，合计 ' + data.window.matches + ' 条'"
          >
            <path d="M0 28H700M0 91H700M0 154H700" class="chart-grid" />
            <polyline
              :points="graph"
              fill="none"
              stroke="#db7843"
              stroke-width="2.5"
              vector-effect="non-scaling-stroke"
            />
            <circle
              v-for="(bucket, i) in chart"
              :key="bucket.start"
              :cx="((i + 0.5) * 700) / chart.length"
              :cy="154 - (bucket.matches / maximum) * 126"
              r="5"
              fill="#fff"
              stroke="#db7843"
              stroke-width="2"
              class="chart-point"
              tabindex="0"
              :aria-label="
                stamp(bucket.start) + ' 至 ' + stamp(bucket.end) + '：' + bucket.matches + ' 条'
              "
              @mouseenter="selected = i"
              @mouseleave="selected = null"
              @focus="selected = i"
              @blur="selected = null"
            >
              <title>
                {{ stamp(bucket.start) }} 至 {{ stamp(bucket.end) }}：{{ bucket.matches }} 条
              </title>
            </circle>
          </svg>
        </div>
        <div class="chart-x">
          <span>{{ stamp(data.start) }}</span
          ><span>{{ stamp((data.start + data.end) / 2) }}</span
          ><span>{{ stamp(data.end) }}</span>
        </div>
      </section>
      <section class="panel source-panel">
        <div class="panel-heading">
          <h2>网站采集</h2>
          <button class="text-link" @click="emit('navigate', '/websites')">
            管理网站<Icon name="arrow" :size="14" />
          </button>
        </div>
        <div v-if="!data.sources.length" class="empty-state">
          <Icon name="globe" :size="30" />
          <h3>还没有监控网站</h3>
          <p>添加后查看已保存的采集状态。</p>
        </div>
        <div v-for="source in data.sources" :key="source.source_id" class="overview-source">
          <button class="overview-website-row" @click="emit('navigate', '/websites')">
            <span class="icon-tile orange"><Icon name="globe" :size="18" /></span
            ><span
              ><strong>{{ source.name }}</strong
              ><small>最后成功：{{ stamp(source.last_success_at) }}</small></span
            ><span class="result-pill" :class="source.failures ? 'no' : 'neutral'">{{
              !source.enabled ? '配置已暂停' : source.failures ? '最近采集失败' : '配置已启用'
            }}</span>
          </button>
          <p class="small-note">
            最后尝试：{{ stamp(source.last_attempt_at) }} · 连续失败 {{ source.failures
            }}{{ source.error_code ? ' · ' + source.error_code : '' }}
          </p>
          <p v-if="source.possible_gap" class="small-note">
            曾发现可能缺口：{{ stamp(source.last_gap_at) }}
          </p>
        </div>
        <p class="source-note"><Icon name="shield" :size="15" />历史成功时间不代表当前正在采集。</p>
      </section>
    </div>
    <section class="panel activity-panel">
      <div class="panel-heading">
        <div>
          <h2>最近命中</h2>
          <p>所选时段内最近 5 条，使用当时任务名称</p>
        </div>
        <button class="text-link" @click="emit('navigate', '/content')">查看内容与命中</button>
      </div>
      <div v-for="(hit, i) in data.recent_matches" :key="i" class="activity-row">
        <span class="timeline-dot orange"><Icon name="spark" :size="17" /></span>
        <div class="activity-copy">
          <button v-if="hit.post_id" @click="emit('navigate', '/content/' + hit.post_id)">
            {{ hit.title }}</button
          ><strong v-else>原内容已清理</strong>
          <p>
            {{ hit.task_name }} · 版本 {{ hit.task_version
            }}{{ hit.task_deleted ? ' · 任务已删除' : '' }}
          </p>
        </div>
        <span class="result-pill yes">命中</span><time>{{ stamp(hit.at) }}</time>
      </div>
      <div v-if="!data.recent_matches.length" class="empty-state">
        <Icon name="inbox" :size="28" />
        <h3>此时段还没有命中记录</h3>
        <p>历史统计会在保存真实记录后更新。</p>
      </div>
    </section>
  </template>
</template>
<style scoped>
.overview-window {
  margin: 18px 0;
}
.overview-source > p {
  margin: 0 20px 12px;
  overflow-wrap: anywhere;
}
.chart-legend {
  gap: 12px;
  flex-wrap: wrap;
}
.chart-x {
  gap: 12px;
}
.activity-copy {
  min-width: 0;
  overflow-wrap: anywhere;
}
.overview-website-row > span:nth-child(2) {
  min-width: 0;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .overview-website-row {
    flex-wrap: wrap;
  }
  .chart-x {
    font-size: 10px;
  }
}
</style>
