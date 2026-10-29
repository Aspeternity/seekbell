<script setup lang="ts">
import StorageSummary from '../components/StorageSummary.vue'
import RetentionPreview from '../components/RetentionPreview.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import { confirmAction, formatTime, request, runtime, state } from '../store'
interface Policy {
  days: number
  revision: number
  next_run_at: number
  last_run_at: number | null
  last_counts: Record<string, number>
}
let active = true
onBeforeUnmount(() => {
  active = false
})
const emit = defineEmits<{ dirty: [value: boolean] }>()
const policy = ref<Policy | null>(null)
const storage = ref<InstanceType<typeof StorageSummary>>()
const days = ref(30)
const busy = ref(false),
  error = ref(''),
  saved = ref(false)
const dirty = computed(() => !!policy.value && days.value !== policy.value.days)
watch(
  dirty,
  (value) => {
    emit('dirty', value)
    if (value) saved.value = false
  },
  { immediate: true },
)
const labels: Record<string, string> = {
  posts: '帖子',
  evaluations: '规则判定',
  hits: '命中记录',
  deliveries: '自动投递',
  attempts: '投递尝试',
  tests: '目标测试',
  manual: '手动重发',
  source_runs: '采集记录',
  system_events: '系统事件',
  alerts: '告警投递',
}
const time = (value: number | null) =>
  value ? formatTime(new Date(value * 1000).toISOString()) : '尚未执行'
const cleaned = computed(() =>
  Object.values(policy.value?.last_counts || {}).reduce((sum, count) => sum + count, 0),
)
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  saved.value = false
  try {
    const result = await request<Policy>('manage/retention')
    if (!active) return
    policy.value = result
    days.value = result.days
    state.settings.retention = result.days
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
// Status refresh keeps an unsaved draft: only the background fields are
// replaced, and a changed revision still surfaces as a conflict on save.
async function refreshStatus() {
  storage.value?.reload()
  if (!dirty.value) return load()
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await request<Policy>('manage/retention')
    if (active && policy.value)
      Object.assign(policy.value, {
        next_run_at: result.next_run_at,
        last_run_at: result.last_run_at,
        last_counts: result.last_counts,
      })
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function refresh() {
  if (dirty.value)
    confirmAction('重新读取保留策略？', '尚未保存的保留天数将丢失。', load, '放弃修改并读取')
  else load()
}
async function persist(values: { days: number; revision: number }) {
  if (busy.value) return
  busy.value = true
  saved.value = false
  error.value = ''
  try {
    const value = await request<Policy>('manage/retention', 'PUT', values)
    if (active) {
      policy.value = value
      days.value = value.days
      state.settings.retention = value.days
      saved.value = true
    }
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function discard() {
  if (!policy.value || busy.value) return
  confirmAction(
    '放弃本页修改？',
    '将恢复本次读取的保留策略。',
    () => {
      days.value = policy.value!.days
      error.value = ''
    },
    '放弃修改',
  )
}
function save() {
  if (busy.value || !policy.value || !dirty.value) return
  error.value = ''
  if (!Number.isInteger(days.value) || days.value < 1 || days.value > 365) {
    error.value = '保留天数应为1–365之间的整数。'
    return
  }
  const values = { days: days.value, revision: policy.value.revision }
  if (days.value < policy.value.days)
    confirmAction(
      '保存历史保留策略？',
      '缩短为' +
        values.days +
        '天后，后台将分批清理过期普通历史。已清理的数据无法恢复；未完成投递及其依赖、独立去重账本保留。',
      () => persist(values),
      '确认保存策略',
    )
  else void persist(values)
}
onMounted(load)
</script>
<template>
  <div class="settings-stack">
    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>历史保留策略</h2>
          <p>按保存的天数，分批清理普通历史</p>
        </div>
        <Icon name="clock" :size="19" />
      </div>
      <FormFeedback :error="error" @retry="refresh" />
      <ReadRegion :loading="busy && !policy" error="" :has-data="!!policy" :min-height="400">
        <form v-if="policy" class="form-content form-stack" @submit.prevent="save">
          <section class="settings-section" aria-labelledby="retention-days-title">
            <div class="settings-section-heading">
              <h3 id="retention-days-title">保留期限</h3>
              <p>超过期限的普通历史由后台分批清理。</p>
            </div>
            <div class="form-stack">
              <label for="retention-days">普通历史保留天数</label>
              <div class="unit-input">
                <input
                  id="retention-days"
                  v-model.number="days"
                  type="number"
                  class="text-input"
                  min="1"
                  max="365"
                  step="1"
                  required
                  :disabled="busy"
                /><span>天</span>
              </div>
              <p class="small-note">默认 30 天，可设置为 1–365 天，按 UTC 的连续 24 小时计算。</p>
            </div>
          </section>
          <section class="settings-section" aria-labelledby="retention-scope-title">
            <div class="settings-section-heading">
              <h3 id="retention-scope-title">清理范围</h3>
              <p>保存前可预览本次天数的清理影响。</p>
            </div>
            <div class="form-stack">
              <div class="info-note">
                <Icon name="shield" :size="18" />
                <p>独立去重记录始终保留，旧帖子再次出现在 RSS 中也不会重新自动发送。</p>
              </div>
              <p class="settings-body-text">
                超过期限的帖子、判定、命中、已完成投递及尝试、已完成测试/手动重发、采集记录和已完成的系统事件告警会自动清理。
              </p>
              <details class="settings-details">
                <summary>哪些记录暂不清理</summary>
                <p class="small-note">
                  待发送、重试、在途、未完成操作及其依赖暂不清理。投递从进入终态或最近结果留证起计算保留期。旧版本升级时已有终态投递会额外保留完整周期。
                </p>
              </details>
              <p class="warning-note">
                清理不可撤销；延长保留天数不会恢复已经删除的历史。清理记录后磁盘文件不一定立即缩小。
              </p>
              <RetentionPreview :days="days" />
            </div>
          </section>
          <div class="inline-form-footer settings-savebar">
            <span role="status">{{
              saved ? '保留策略已保存' : dirty ? '有未保存的修改' : '没有未保存的修改'
            }}</span>
            <div class="inline-actions">
              <button class="button" type="button" :disabled="busy || !dirty" @click="discard">
                放弃修改
              </button>
              <button class="button primary" type="submit" :disabled="busy || !dirty">
                {{ busy ? '处理中…' : '保存保留策略' }}
              </button>
            </div>
          </div>
        </form>
      </ReadRegion>
    </section>
    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>存储与清理状态</h2>
          <p>数据库占用与后台自动清理进度</p>
        </div>
        <button class="button" type="button" :disabled="busy" @click="refreshStatus">
          刷新状态
        </button>
      </div>
      <div class="form-content form-stack">
        <section class="settings-section" aria-labelledby="storage-title">
          <div class="settings-section-heading">
            <h3 id="storage-title">存储占用</h3>
            <p>服务端数据目录的当前占用。</p>
          </div>
          <StorageSummary ref="storage" />
        </section>
        <section class="settings-section" aria-labelledby="cleanup-title">
          <div class="settings-section-heading">
            <h3 id="cleanup-title">后台清理</h3>
            <p>约每小时检查一次，积压时连续分批执行。</p>
          </div>
          <ReadRegion :loading="busy && !policy" error="" :has-data="!!policy" :min-height="120">
            <div v-if="policy" class="form-stack">
              <dl class="detail-grid settings-metrics">
                <div>
                  <dt>后台状态</dt>
                  <dd>{{ runtime.active ? '运行中' : '未运行，等待服务恢复' }}</dd>
                </div>
                <div>
                  <dt>最近一批</dt>
                  <dd>{{ time(policy.last_run_at) }}</dd>
                </div>
                <div>
                  <dt>下次检查</dt>
                  <dd>{{ policy.next_run_at ? time(policy.next_run_at) : '等待后台处理' }}</dd>
                </div>
              </dl>
              <p v-if="policy.last_run_at && !cleaned" class="small-note">
                最近一批没有需要清理的记录。
              </p>
              <details v-else-if="policy.last_run_at" class="settings-details">
                <summary>最近一批共清理 {{ cleaned }} 条记录</summary>
                <dl class="detail-grid retention-counts" aria-label="最近一批清理数量">
                  <div v-for="(label, key) in labels" :key="key">
                    <dt>{{ label }}</dt>
                    <dd>{{ policy.last_counts[key] || 0 }}</dd>
                  </div>
                </dl>
              </details>
            </div>
          </ReadRegion>
        </section>
      </div>
    </section>
  </div>
</template>
