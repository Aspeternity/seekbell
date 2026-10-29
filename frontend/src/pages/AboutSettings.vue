<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { loadReadiness, loadVersionInfo } from '../api'
import { request } from '../store'
import { useRemote } from '../history'
import Feedback from '../components/Feedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import CurrentFaults from '../components/CurrentFaults.vue'
import SystemEventLog from '../components/SystemEventLog.vue'
interface Diagnostics {
  application: string
  version: string
  build_revision: string
  database_revision: string
  runtime: RuntimeInfo
  supported_websites: { id: string; name: string }[]
  fault_codes: string[]
  checked_at: number
}
interface RuntimeInfo {
  active: boolean
  status: string
  code: string | null
}
const diagnostics = useRemote(
  () => request<Diagnostics>('manage/diagnostics'),
  () => [],
  { cacheKey: () => 'about:diagnostics' },
)
const version = useRemote(loadVersionInfo, () => [], { cacheKey: () => 'about:version' })
const readiness = useRemote(loadReadiness, () => [], { cacheKey: () => 'about:ready' })
const runtime = useRemote(
  () => request<RuntimeInfo>('manage/runtime'),
  () => [],
  { cacheKey: () => 'about:runtime' },
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
const busy = computed(
  () => version.loading.value || readiness.loading.value || runtime.loading.value,
)
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
const websites = computed(() =>
  diagnostics.data.value?.supported_websites.map((row) => row.name).join('、'),
)
const docs = 'https://github.com/Aspeternity/seekbell/blob/main/'
function refresh() {
  version.reload()
  readiness.reload()
  runtime.reload()
  diagnostics.reload()
  faults.value?.reload()
  eventLog.value?.reload()
}
</script>
<template>
  <div class="settings-stack">
    <section class="panel about-card" aria-label="版本信息">
      <div class="about-brand">
        <span class="brand-icon"><Icon name="bell" :size="24" /></span>
        <div>
          <h2>SeekBell<span class="brand-period">.</span></h2>
          <p>留意你关心的。</p>
        </div>
      </div>
      <ReadRegion
        :loading="version.loading.value"
        :error="version.error.value"
        :has-data="!!version.data.value"
        :min-height="64"
        @retry="version.reload"
      >
        <dl v-if="version.data.value" class="about-facts">
          <div>
            <dt>应用版本</dt>
            <dd data-testid="app-version">{{ version.data.value.version }}</dd>
          </div>
          <div>
            <dt>数据库版本</dt>
            <dd data-testid="database-revision">
              <code>{{ version.data.value.database_revision ?? '未记录迁移版本' }}</code>
            </dd>
          </div>
          <div>
            <dt>代码版本</dt>
            <dd data-testid="build-revision" :title="version.data.value.build_revision">
              <code>{{ version.data.value.build_revision }}</code>
            </dd>
          </div>
          <div v-if="websites">
            <dt>支持网站</dt>
            <dd data-testid="supported-websites">{{ websites }}</dd>
          </div>
        </dl>
        <p v-if="version.data.value?.build_revision === 'development'" class="small-note">
          本地开发构建，未固定代码提交版本。
        </p>
      </ReadRegion>
      <div class="about-footer">
        <nav class="about-links" aria-label="帮助文档">
          <a class="text-link" :href="docs + 'README.md'" target="_blank" rel="noopener noreferrer"
            >使用说明</a
          >
          <a
            class="text-link"
            :href="docs + 'docs/BACKUP_RESTORE.md'"
            target="_blank"
            rel="noopener noreferrer"
            >备份恢复</a
          >
          <a
            class="text-link"
            :href="docs + 'docs/RELEASES.md'"
            target="_blank"
            rel="noopener noreferrer"
            >升级与回退</a
          >
        </nav>
        <div class="about-copy">
          <span v-if="copied" role="status">{{ copied }}</span>
          <button class="button" :disabled="!diagnostics.data.value" @click="copyDiagnostics">
            <Icon name="copy" :size="14" />复制诊断摘要
          </button>
        </div>
      </div>
      <textarea
        v-if="showing"
        class="text-input diagnostic-summary"
        aria-label="诊断摘要"
        :value="summary"
        readonly
        rows="10"
      />
    </section>
    <section class="panel settings-card" aria-labelledby="readiness-title">
      <div class="panel-heading">
        <h2 id="readiness-title">服务状态</h2>
        <button class="button" :disabled="busy" @click="refresh">
          <Icon name="refresh" :size="14" />刷新运行信息
        </button>
      </div>
      <div class="form-content form-stack">
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
