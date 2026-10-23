<script setup lang="ts">
import { computed } from 'vue'
import Icon from '../components/Icon.vue'
import { loadReadiness, loadVersionInfo } from '../api'
import { request } from '../store'
import { useRemote } from '../history'
import ReadRegion from '../components/ReadRegion.vue'
interface RuntimeInfo {
  active: boolean
  status: string
  code: string | null
}
const version = useRemote(loadVersionInfo, () => [], { cacheKey: () => 'about:version' })
const readiness = useRemote(loadReadiness, () => [], { cacheKey: () => 'about:ready' })
const runtime = useRemote(
  () => request<RuntimeInfo>('manage/runtime'),
  () => [],
  { cacheKey: () => 'about:runtime' },
)
const busy = computed(
  () => version.loading.value || readiness.loading.value || runtime.loading.value,
)
const runtimeLabel = computed(() => {
  const data = runtime.data.value
  if (!data) return ''
  if (data.active) return '循环运行中'
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
  version.reload()
  readiness.reload()
  runtime.reload()
}
</script>
<template>
  <div class="side-stack">
    <section class="panel about-card" aria-label="版本信息">
      <span class="brand-icon"><Icon name="bell" :size="26" /></span>
      <h2 id="version-title">SeekBell<span class="brand-period">.</span></h2>
      <p>留意你关心的。</p>
      <span class="small-badge neutral">单管理员 · 自托管</span>
      <div>
        <ReadRegion
          :loading="version.loading.value"
          :error="version.error.value"
          :has-data="!!version.data.value"
          :min-height="120"
          @retry="version.reload"
        >
          <template v-if="version.data.value">
            <dl class="detail-grid">
              <div>
                <dt>应用版本</dt>
                <dd data-testid="app-version">{{ version.data.value.version }}</dd>
              </div>
              <div>
                <dt>数据库迁移版本</dt>
                <dd data-testid="database-revision">
                  <code>{{ version.data.value.database_revision ?? '未记录迁移版本' }}</code>
                </dd>
              </div>
              <div class="wide">
                <dt>代码版本</dt>
                <dd data-testid="build-revision">
                  <code>{{ version.data.value.build_revision }}</code>
                </dd>
              </div>
            </dl>
            <p v-if="version.data.value.build_revision === 'development'" class="small-note">
              本地开发构建，未固定代码提交版本。
            </p>
          </template>
        </ReadRegion>
        <p>内置网站适配 · 当前支持 NodeSeek</p>
        <button class="button spaced" :disabled="busy" @click="refresh">刷新运行信息</button>
      </div>
    </section>
    <section class="panel settings-card" aria-labelledby="readiness-title">
      <div class="panel-heading"><h2 id="readiness-title">服务状态</h2></div>
      <div class="form-content form-stack">
        <ReadRegion
          :loading="readiness.loading.value"
          :error="readiness.error.value"
          :has-data="!!readiness.data.value"
          :min-height="70"
          @retry="readiness.reload"
        >
          <p
            v-if="readiness.data.value"
            :class="readiness.data.value === 'ok' ? 'info-note' : 'form-errors'"
            :role="readiness.data.value === 'ok' ? 'status' : 'alert'"
          >
            {{
              readiness.data.value === 'ok' ? '服务已就绪' : '服务未就绪，请检查数据库和后台状态。'
            }}
          </p>
        </ReadRegion>
        <ReadRegion
          :loading="runtime.loading.value"
          :error="runtime.error.value"
          :has-data="!!runtime.data.value"
          :min-height="70"
          @retry="runtime.reload"
        >
          <dl v-if="runtime.data.value" class="detail-grid">
            <div>
              <dt>后台运行状态</dt>
              <dd>{{ runtimeLabel }}</dd>
            </div>
            <div>
              <dt>诊断代码</dt>
              <dd>{{ runtime.data.value.code || '无' }}</dd>
            </div>
          </dl>
        </ReadRegion>
        <p class="small-note">
          就绪检查验证数据库和后台循环。RSS 与通知渠道的实际结果请查看概览和系统告警；
          就绪不表示外部服务可用或消息已送达。
        </p>
      </div>
    </section>
  </div>
</template>
