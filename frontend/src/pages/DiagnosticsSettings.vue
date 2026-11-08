<script setup lang="ts">
// Transitional: the previous diagnostics, moved verbatim out of About until the diagnostics rebuild.
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { loadReadiness } from '../api'
import { request } from '../store'
import { useRemote } from '../history'
import Feedback from '../components/Feedback.vue'
import CurrentFaults from '../components/CurrentFaults.vue'
import SystemEventLog from '../components/SystemEventLog.vue'
interface RuntimeInfo {
  active: boolean
  status: string
  code: string | null
}
const diagnostics = useRemote(
  () => request<Record<string, unknown>>('manage/diagnostics'),
  () => [],
  { cacheKey: () => 'diagnostics:summary' },
)
const readiness = useRemote(loadReadiness, () => [], { cacheKey: () => 'diagnostics:ready' })
const runtime = useRemote(
  () => request<RuntimeInfo>('manage/runtime'),
  () => [],
  { cacheKey: () => 'diagnostics:runtime' },
)
const faults = ref<InstanceType<typeof CurrentFaults>>(),
  eventLog = ref<InstanceType<typeof SystemEventLog>>(),
  faultTotal = ref<number>()
const copied = ref(''),
  showing = ref(false)
const summary = computed(() =>
  diagnostics.data.value ? JSON.stringify(diagnostics.data.value, null, 2) : '',
)
async function copyDiagnostics() {
  showing.value = true
  copied.value = ''
  try {
    if (!navigator.clipboard?.writeText) throw new Error()
    await navigator.clipboard.writeText(summary.value)
    copied.value = '已复制'
  } catch {
    copied.value = '请手动复制下方内容'
  }
}
const busy = computed(() => readiness.loading.value || runtime.loading.value)
const runtimeLabel = computed(() => {
  const data = runtime.data.value
  if (!data) return ''
  if (data.active) return '运行中'
  return (
    {
      starting: '正在启动',
      stopping: '正在停止',
      stopped: '已停止',
      failed: '异常停止',
      unavailable: '状态不可用',
      idle: '未启动',
    }[data.status] || '未运行'
  )
})
function refresh() {
  readiness.reload()
  runtime.reload()
  diagnostics.reload()
  faults.value?.reload()
  eventLog.value?.reload()
}
</script>
<template>
  <div class="settings-stack">
    <section class="panel settings-card" aria-labelledby="readiness-title">
      <div class="panel-heading">
        <h2 id="readiness-title">服务状态</h2>
        <div class="about-copy">
          <span v-if="copied" role="status">{{ copied }}</span>
          <button class="button" :disabled="!diagnostics.data.value" @click="copyDiagnostics">
            <Icon name="copy" :size="14" />复制诊断摘要
          </button>
          <button class="button" :disabled="busy" @click="refresh">
            <Icon name="refresh" :size="14" />刷新运行信息
          </button>
        </div>
      </div>
      <div class="form-content form-stack">
        <textarea
          v-if="showing"
          class="text-input diagnostic-summary"
          aria-label="诊断摘要"
          :value="summary"
          readonly
          rows="10"
        />
        <dl class="status-tiles">
          <div>
            <dt>服务</dt>
            <dd v-if="readiness.data.value === 'ok'" class="status-value ok" role="status">
              已就绪
            </dd>
            <dd v-else-if="readiness.data.value" class="status-value bad" role="alert">
              未就绪，请检查数据库和后台
            </dd>
            <dd v-else class="status-value pending" aria-label="读取中" />
          </div>
          <div>
            <dt>后台任务</dt>
            <dd
              v-if="runtime.data.value"
              class="status-value"
              :class="runtime.data.value.active ? 'ok' : 'bad'"
            >
              <span>{{ runtimeLabel }}</span>
              <code v-if="runtime.data.value.code">{{ runtime.data.value.code }}</code>
            </dd>
            <dd v-else class="status-value pending" aria-label="读取中" />
          </div>
          <div>
            <dt>当前故障</dt>
            <dd
              v-if="faultTotal !== undefined"
              class="status-value"
              :class="faultTotal ? 'bad' : 'ok'"
            >
              {{ faultTotal ? faultTotal + ' 项' : '无' }}
            </dd>
            <dd v-else class="status-value pending" aria-label="读取中" />
          </div>
        </dl>
        <Feedback
          :loading="false"
          :error="readiness.error.value"
          :retained="!!readiness.data.value"
          @retry="readiness.reload"
        />
        <Feedback
          :loading="false"
          :error="runtime.error.value"
          :retained="!!runtime.data.value"
          @retry="runtime.reload"
        />
        <CurrentFaults ref="faults" @total="faultTotal = $event" />
      </div>
    </section>
    <SystemEventLog ref="eventLog" />
  </div>
</template>
