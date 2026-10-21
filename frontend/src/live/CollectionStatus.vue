<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import type { OverviewData } from './overview'

type Source = OverviewData['sources'][number]
const props = defineProps<{
  sources: Source[]
  stamp: (value: number | null) => string
  timezone: string
}>()
const errorTrigger = ref<HTMLButtonElement>()
const errorPanel = ref<HTMLElement>()
const selectedId = defineModel<string>({ default: '' })
const errorsOpen = ref(false)
const current = computed(() =>
  props.sources.find((source) => source.source_id === selectedId.value),
)
const failures = computed(() =>
  props.sources.filter((source) => source.enabled && source.failures > 0),
)
const multiple = computed(() => props.sources.length > 1)
const health = (source: Source) =>
  !source.enabled
    ? 'paused'
    : source.failures
      ? 'error'
      : source.last_success_at === null
        ? 'waiting'
        : 'healthy'
const status = (source: Source) =>
  ({ paused: '已暂停', error: '异常', waiting: '待采集', healthy: '正常' })[health(source)]
const runs = computed(() => current.value?.recent_runs ?? [])
const failedCount = computed(() => runs.value.filter((run) => run.status === 'failure').length)
const unknownCount = computed(() => runs.value.filter((run) => run.status === 'unknown').length)
const slots = computed(() => [
  ...Array.from({ length: Math.max(0, 30 - runs.value.length) }, () => null),
  ...runs.value,
])
const resultLabel = computed(() =>
  !runs.value.length
    ? '暂无记录'
    : failedCount.value
      ? failedCount.value + ' 次失败'
      : unknownCount.value
        ? unknownCount.value + ' 次未知'
        : runs.value.length === 30
          ? '全部成功'
          : '已记录 ' + runs.value.length + ' 次',
)
watch(
  () => props.sources.map((source) => source.source_id),
  (ids) => {
    if (!ids.includes(selectedId.value)) selectedId.value = ids[0] ?? ''
    errorsOpen.value = false
  },
  { immediate: true },
)
watch(failures, (items) => {
  if (items.length < 2) errorsOpen.value = false
})
function closeErrors(focus = false) {
  errorsOpen.value = false
  if (focus) nextTick(() => errorTrigger.value?.focus())
}
function move(direction: number) {
  const index = props.sources.findIndex((source) => source.source_id === selectedId.value)
  selectedId.value =
    props.sources[(index + direction + props.sources.length) % props.sources.length]!.source_id
  closeErrors()
}
async function showErrors() {
  if (failures.value.length === 1) {
    selectedId.value = failures.value[0]!.source_id
    closeErrors()
  } else {
    errorsOpen.value = !errorsOpen.value
    if (errorsOpen.value) {
      await nextTick()
      errorPanel.value?.querySelector<HTMLButtonElement>('button')?.focus()
    }
  }
}
function selectError(source: Source) {
  selectedId.value = source.source_id
  closeErrors(true)
}
function outside(event: PointerEvent) {
  const target = event.target as Node
  if (
    errorsOpen.value &&
    !errorPanel.value?.contains(target) &&
    !errorTrigger.value?.contains(target)
  )
    closeErrors()
}
function escape(event: KeyboardEvent) {
  if (errorsOpen.value && event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeErrors(true)
  }
}
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('keydown', escape)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('keydown', escape)
})
</script>

<template>
  <section class="panel source-panel collection-card" aria-label="采集状态">
    <div class="panel-heading collection-heading">
      <div class="collection-heading-title">
        <h2>采集状态</h2>
        <span v-if="multiple" class="collection-summary">
          {{ sources.length }} 个网站 ·
          <button
            v-if="failures.length"
            ref="errorTrigger"
            type="button"
            class="collection-error-trigger"
            :aria-label="'查看 ' + failures.length + ' 个异常网站'"
            :aria-haspopup="failures.length > 1 ? 'dialog' : undefined"
            :aria-expanded="failures.length > 1 ? errorsOpen : undefined"
            :aria-controls="errorsOpen ? 'collection-errors' : undefined"
            @click="showErrors"
          >
            {{ failures.length }} 个异常
          </button>
          <span v-else>0 个异常</span>
        </span>
      </div>
      <span
        v-if="current"
        class="live-label collection-health"
        :class="health(current)"
        :aria-label="current.name + '当前采集状态：' + status(current)"
        ><span class="status-dot" />{{ status(current) }}</span
      >
      <div
        v-if="errorsOpen"
        id="collection-errors"
        ref="errorPanel"
        class="collection-error-panel"
        role="dialog"
        aria-label="异常网站"
      >
        <p>选择要查看的异常网站</p>
        <button
          v-for="source in failures"
          :key="source.source_id"
          type="button"
          @click="selectError(source)"
        >
          <span>{{ source.name }}</span
          ><small>异常</small><Icon name="arrow" :size="14" />
        </button>
      </div>
    </div>
    <div v-if="current" class="collection-body" aria-live="polite">
      <div class="source-identity">
        <div class="source-logo">
          {{ current.website_id === 'nodeseek' ? 'N' : current.name.slice(0, 1) }}<span>›</span>
        </div>
        <div>
          <h3 :title="current.name">{{ current.name }}</h3>
          <p>
            {{ current.website_id === 'nodeseek' ? '官方 RSS' : 'RSS' }} ·
            {{ multiple ? '同站任务共享采集' : '唯一采集来源' }}
          </p>
        </div>
        <Icon name="globe" :size="18" />
      </div>
      <dl class="source-data">
        <div>
          <dt>最近成功采集</dt>
          <dd>{{ stamp(current.last_success_at) }}</dd>
        </div>
        <div>
          <dt>采集间隔</dt>
          <dd>{{ current.interval_seconds }} <span>秒</span></dd>
        </div>
        <div :title="'按 ' + timezone + ' 的自然日统计首次发现记录'">
          <dt>本日发现新帖</dt>
          <dd>{{ current.today_posts }} <span>条</span></dd>
        </div>
      </dl>
      <div
        class="uptime-bars"
        role="img"
        :aria-label="
          '最近 ' + runs.length + ' 次采集，' + failedCount + ' 次失败，' + unknownCount + ' 次未知'
        "
      >
        <i
          v-for="(run, index) in slots"
          :key="index"
          :class="{
            'is-empty': !run,
            'is-error': run?.status === 'failure',
            'is-unknown': run?.status === 'unknown',
          }"
          :title="
            run
              ? stamp(run.at) +
                ' · ' +
                { success: '成功', failure: '失败', unknown: '未知' }[run.status]
              : '尚无采集记录'
          "
        />
      </div>
      <div class="uptime-label">
        <span>最近 30 次采集</span><span>{{ resultLabel }}</span>
      </div>
    </div>
    <div v-else class="empty-state collection-body">
      <Icon name="globe" :size="30" />
      <h3>还没有监控网站</h3>
      <p>添加后，在这里查看网站的采集状态。</p>
    </div>
    <div class="source-note collection-footer" :class="{ solo: !multiple }">
      <button
        v-if="multiple"
        type="button"
        class="icon-button collection-nav"
        aria-label="上一个网站"
        @click="move(-1)"
      >
        <Icon name="previous" :size="18" />
      </button>
      <span
        ><Icon name="shield" :size="15" />{{
          multiple ? '同站任务' : '全部任务'
        }}共享采集，不重复请求</span
      >
      <button
        v-if="multiple"
        type="button"
        class="icon-button collection-nav"
        aria-label="下一个网站"
        @click="move(1)"
      >
        <Icon name="next" :size="18" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.collection-card {
  display: flex;
  flex-direction: column;
}
.collection-heading {
  position: relative;
}
.collection-heading-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 9px;
  min-width: 0;
}
.collection-heading h2 {
  white-space: nowrap;
}
.collection-summary {
  color: #6f7885;
  font-size: 10px;
  white-space: nowrap;
}
.collection-error-trigger {
  background: none;
  border: 0;
  padding: 0;
  color: #b46055;
  font: inherit;
}
.collection-health {
  flex-shrink: 0;
  min-width: 49px;
  justify-content: flex-end;
}
.collection-health.error {
  color: #b46055;
}
.collection-health.waiting {
  color: #a87d42;
}
.collection-health.paused {
  color: #6f7885;
}
.collection-health .status-dot {
  background: currentColor;
}
.collection-body {
  flex: 1;
  min-height: 211px;
}
.source-identity > div:nth-child(2) {
  min-width: 0;
  flex: 1;
}
.source-logo {
  flex-shrink: 0;
}
.source-identity h3 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.collection-card .source-data {
  grid-template-columns: 1fr;
  gap: 11px;
}
.collection-card .source-data > div {
  flex-direction: row;
  gap: 12px;
  border: 0;
  min-width: 0;
}
.collection-card .source-data dd {
  white-space: nowrap;
}
.collection-card .uptime-bars i.is-empty {
  background: #e4e8eb;
}
.collection-card .uptime-bars i.is-unknown {
  background: #d7bb86;
}
.collection-card .uptime-bars i.is-error {
  background: #c68c55;
}
.collection-footer {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 30px;
  gap: 7px;
  padding: 7px 10px;
}
.collection-footer.solo {
  grid-template-columns: minmax(0, 1fr);
  padding: 10px 18px;
}
.collection-footer > span {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
}
.collection-footer > span > svg {
  flex-shrink: 0;
}
.collection-nav {
  width: 30px;
  height: 30px;
}
.collection-error-panel {
  position: absolute;
  top: calc(100% - 2px);
  left: 18px;
  right: 18px;
  z-index: 40;
  padding: 8px;
  background: white;
  border: 1px solid #e9ebee;
  border-radius: 8px;
  box-shadow: 0 8px 28px #292e351a;
  max-height: 244px;
  overflow: auto;
}
.collection-error-panel > p {
  padding: 4px 8px 8px;
  font-size: 10px;
  color: #6f7885;
}
.collection-error-panel > button {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  text-align: left;
  padding: 9px 8px;
  background: none;
  border: 0;
  border-radius: 5px;
  color: #4d5762;
  font: inherit;
  font-size: 12px;
}
.collection-error-panel > button:hover,
.collection-error-panel > button:focus-visible {
  background: #f9ebe2;
}
.collection-error-panel > button > span {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.collection-error-panel small {
  color: #b46055;
  font-size: 10px;
}
@media (pointer: coarse) {
  .collection-nav {
    min-width: 40px;
    min-height: 40px;
  }
  .collection-footer {
    grid-template-columns: 40px minmax(0, 1fr) 40px;
  }
  .collection-error-panel > button {
    min-height: 44px;
  }
}
</style>
