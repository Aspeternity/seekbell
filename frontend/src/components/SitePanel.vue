<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInputNumber, NSwitch, NTag } from 'naive-ui'
import { getSite, localDate, message, sourceError, write } from '../management'
import type { ProbeResult, SiteState } from '../management'

const props = defineProps<{ csrf: string }>()
const site = ref<SiteState | null>(null)
const enabled = ref(false)
const interval = ref<number | null>(10)
const draftRevision = ref(0)
const loading = ref(false)
const busy = ref(false)
const configOpen = ref(false)
const error = ref('')
const notice = ref('')
const probe = ref<ProbeResult | null>(null)
const stale = computed(() => site.value && draftRevision.value !== site.value.revision)
let timer: ReturnType<typeof setInterval> | undefined

function useSettings(value: SiteState) {
  site.value = value
  enabled.value = value.enabled
  interval.value = value.interval_seconds
  draftRevision.value = value.revision
}

function openConfig() {
  if (site.value) {
    enabled.value = site.value.enabled
    interval.value = site.value.interval_seconds
    draftRevision.value = site.value.revision
  }
  configOpen.value = true
}

async function load(reset = false) {
  if (loading.value || busy.value) return
  loading.value = true
  error.value = ''
  try {
    const latest = await getSite()
    if (reset) useSettings(latest)
    else site.value = latest
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}

async function save() {
  busy.value = true
  error.value = notice.value = ''
  try {
    useSettings(
      await write<SiteState>(
        '/site',
        'PUT',
        {
          enabled: enabled.value,
          interval_seconds: interval.value,
          expected_revision: draftRevision.value,
        },
        props.csrf,
      ),
    )
    notice.value = '网站设置已保存。首次成功和主动暂停后的恢复只建立基线，不推送窗口内旧帖。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}

async function testConnection() {
  busy.value = true
  error.value = notice.value = ''
  probe.value = null
  try {
    probe.value = await write<ProbeResult>('/site/test', 'POST', {}, props.csrf)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
    await load()
  }
}

onMounted(() => {
  void load(true)
  timer = setInterval(() => void load(), 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section aria-label="监控网站管理" :aria-busy="loading || busy">
    <div class="panel-heading">
      <div>
        <h2>监控网站</h2>
        <p class="section-lead">
          每个网站卡片实时汇总来源运行态与基线状态；点击卡片即可展开当前网站的采集配置与连接测试。
        </p>
      </div>
      <NButton :loading="loading" :disabled="busy" @click="load(true)">重新读取设置</NButton>
    </div>

    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>
    <NAlert v-if="notice" type="success" role="status" class="notice">{{ notice }}</NAlert>

    <div v-if="site" class="site-cards-grid">
      <!-- Compact Integrated Website Card -->
      <article
        class="site-compact-card"
        :class="{ 'site-card-active': configOpen, 'site-card-enabled': site.enabled }"
        role="button"
        tabindex="0"
        aria-label="配置 NodeSeek 官方 RSS"
        @click="openConfig"
        @keydown.enter.prevent="openConfig"
        @keydown.space.prevent="openConfig"
      >
        <div class="site-card-top">
          <div class="site-card-identity">
            <span class="site-avatar">NS</span>
            <div>
              <h3 class="site-card-title">NodeSeek 官方 RSS</h3>
              <span class="site-card-sub">每 {{ site.interval_seconds }} 秒轮询 · 官方 RSS 源</span>
            </div>
          </div>
          <div class="site-card-badges">
            <NTag size="small" :type="site.enabled ? 'success' : 'default'">{{
              site.enabled ? '来源已启用' : '来源已暂停'
            }}</NTag>
            <NTag
              size="small"
              :type="site.initialized && !site.needs_baseline ? 'info' : 'warning'"
            >
              {{
                !site.initialized
                  ? '尚未建立基线'
                  : site.needs_baseline
                    ? '恢复时需要重建基线'
                    : '基线已建立'
              }}
            </NTag>
          </div>
        </div>

        <div class="site-card-metrics">
          <div class="site-metric-row">
            <span class="site-metric-dot" :class="{ ok: site.failures === 0 }"></span>
            <strong
              >最近 RSS 窗口：{{ site.window_count }} 条 · 连续失败 {{ site.failures }} 次</strong
            >
          </div>
          <div class="site-metric-grid">
            <span>最近成功采集：{{ localDate(site.last_success_at) }}</span>
            <span>最近尝试：{{ localDate(site.last_attempt_at) }}</span>
            <span class="site-metric-full"
              >最近连接错误：{{ sourceError(site.last_error_code) }}</span
            >
          </div>
        </div>

        <NAlert v-if="site.possible_gap" type="warning" class="notice site-inline-alert">
          曾发现可能的窗口缺口，无法精确确定漏帖数量。
        </NAlert>

        <div class="site-card-footer">
          <span class="site-url-chip">{{ site.url }}</span>
          <span class="site-configure-cta">点击配置网站 →</span>
        </div>
      </article>

      <!-- Future Multi-Site Slot Card -->
      <div class="site-compact-card site-placeholder-card" aria-hidden="true">
        <div class="site-card-top">
          <div class="site-card-identity">
            <span class="site-avatar site-avatar-muted">+</span>
            <div>
              <h3 class="site-card-title">更多站点适配器</h3>
              <span class="site-card-sub">多站点卡片矩阵架构预留</span>
            </div>
          </div>
          <NTag size="small" :bordered="false">规划中</NTag>
        </div>
        <p class="muted" style="margin: 8px 0 0">
          后续新增监控站点将以独立小卡片并列展示在此矩阵中，各自具备独立采集状态、基线与点击弹窗配置。
        </p>
      </div>
    </div>

    <!-- Click-to-Open Website Configuration Modal / Drawer -->
    <div v-if="site && configOpen" class="site-drawer-backdrop" @click.self="configOpen = false">
      <div class="site-drawer" role="dialog" aria-modal="true" aria-label="NodeSeek 官方 RSS 配置">
        <div class="site-drawer-header">
          <div class="site-card-identity">
            <span class="site-avatar">NS</span>
            <div>
              <h3>NodeSeek 官方 RSS · 网站配置</h3>
              <a :href="site.url" target="_blank" rel="noopener noreferrer" class="external-link">{{
                site.url
              }}</a>
            </div>
          </div>
          <NButton size="small" secondary @click="configOpen = false">关闭配置</NButton>
        </div>

        <div class="site-drawer-body">
          <NAlert v-if="stale" type="warning" class="notice">
            网站设置已在其他页面修改，请重新读取设置后再保存。
          </NAlert>
          <NAlert v-if="!site.configuration_valid" type="error" class="notice">
            保存的来源配置不匹配内置适配器，采集会被拒绝。
          </NAlert>
          <NAlert v-if="!site.scheduler.enabled" type="warning" class="notice">
            后台调度由启动配置关闭，保存不会在当前进程中启动采集。
          </NAlert>
          <NAlert v-else-if="!site.scheduler.healthy" type="error" class="notice">
            后台组件异常，请检查服务并重启恢复。
          </NAlert>

          <p class="muted">仅支持标题、摘要、作者用户名和版块。没有全文、回帖或网页采集。</p>

          <NForm @submit.prevent="save">
            <div class="form-grid">
              <NFormItem label="启用网站采集">
                <NSwitch v-model:value="enabled" :disabled="busy" aria-label="启用网站采集" />
              </NFormItem>
              <NFormItem label="采集间隔（秒）" :label-props="{ for: 'site-interval' }">
                <NInputNumber
                  v-model:value="interval"
                  :min="1"
                  :max="86400"
                  :precision="0"
                  :disabled="busy"
                  :input-props="{ id: 'site-interval', required: true }"
                />
              </NFormItem>
            </div>
            <p class="muted">
              默认 10 秒是实现候选值，不代表官方限频许可。失败会退避，429/Retry-After
              会延长等待；修改频率或启停不能绕过已有退避。
            </p>
            <div class="actions">
              <NButton
                type="primary"
                attr-type="submit"
                :loading="busy"
                :disabled="stale || interval === null"
              >
                保存网站设置
              </NButton>
              <NButton :disabled="busy" @click="testConnection">测试 RSS 连接</NButton>
            </div>
          </NForm>

          <NAlert
            v-if="probe"
            :type="probe.status === 'success' ? 'success' : 'warning'"
            role="status"
            class="notice"
          >
            <template v-if="probe.status === 'success'">
              连接测试成功：返回 {{ probe.raw_count }} 条，合法条目
              {{ probe.valid_count }} 条。本次不存帖子、不建立基线或发送通知。
            </template>
            <template v-else>
              {{ probe.status === 'backoff' ? '正在退避，未发出请求' : '连接测试失败' }}：{{
                sourceError(probe.code)
              }}。下次允许尝试：{{ localDate(probe.next_attempt_at) }}
            </template>
          </NAlert>

          <div class="drawer-status-summary">
            <p class="muted" style="margin: 0">
              连接测试共用采集请求锁；失败会记录状态并退避。主动暂停后恢复会重建基线；程序意外重启保留已见状态，只处理仍在
              RSS 窗口中的未见帖。
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
