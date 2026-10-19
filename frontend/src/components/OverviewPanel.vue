<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NCard, NTag } from 'naive-ui'
import { getOverview, localDate, message, sourceError } from '../management'
import type { Overview } from '../management'

const overview = ref<Overview | null>(null)
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    overview.value = await getOverview()
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
  timer = setInterval(() => void load(), 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section aria-label="运行概览" :aria-busy="loading">
    <div class="panel-heading">
      <div>
        <h2>概览</h2>
        <p class="section-lead">
          实时监控核心指标、采集源健康度与通知队列状态（每 5 秒自动刷新）。
        </p>
      </div>
      <NButton :loading="loading" @click="load">刷新概览</NButton>
    </div>

    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>

    <template v-if="overview">
      <NAlert v-if="!overview.scheduler.healthy" type="error" class="notice">
        后台组件异常，请检查服务并重启恢复；存活检查与业务健康分开。
      </NAlert>
      <NAlert v-else-if="!overview.scheduler.enabled" type="warning" class="notice">
        后台调度已由启动配置关闭，当前只保存和查看配置。
      </NAlert>
      <NAlert v-if="overview.counts.uncertain" type="warning" class="notice">
        {{ overview.counts.uncertain }} 条投递曾出现结果未知，后续成功仍保留标记；重试可能重复。
      </NAlert>

      <!-- Top 6-Column KPI Strip -->
      <div class="stats-grid" aria-label="本地统计">
        <div class="kpi-card kpi-teal">
          <span class="kpi-label">启用任务 / 全部任务</span>
          <div class="stat-number">
            {{ overview.counts.enabled_tasks }} <small>/ {{ overview.counts.tasks }}</small>
          </div>
          <span class="kpi-sub">活跃三值规则监控</span>
        </div>
        <div class="kpi-card kpi-blue">
          <span class="kpi-label">通知目标</span>
          <div class="stat-number">{{ overview.counts.targets }}</div>
          <span class="kpi-sub">四渠道已配置接收端</span>
        </div>
        <div class="kpi-card kpi-indigo">
          <span class="kpi-label">本地帖子</span>
          <div class="stat-number">{{ overview.counts.posts }}</div>
          <span class="kpi-sub">保留期内存档新帖</span>
        </div>
        <div class="kpi-card kpi-emerald">
          <span class="kpi-label">规则命中</span>
          <div class="stat-number">{{ overview.counts.hits }}</div>
          <span class="kpi-sub">累计触发命中次数</span>
        </div>
        <div class="kpi-card kpi-amber">
          <span class="kpi-label">等待 / 重试 / 在途</span>
          <div class="stat-number">
            {{ overview.counts.deliveries.pending }} / {{ overview.counts.deliveries.retry }} /
            {{ overview.counts.deliveries.leased }}
          </div>
          <span class="kpi-sub">当前活跃投递队列</span>
        </div>
        <div class="kpi-card kpi-slate">
          <span class="kpi-label">渠道接受 / 失败 / 已取消</span>
          <div class="stat-number">
            {{ overview.counts.deliveries.sent }} / {{ overview.counts.deliveries.failed }} /
            {{ overview.counts.deliveries.cancelled }}
          </div>
          <span class="kpi-sub">历史终态投递统计</span>
        </div>
      </div>

      <!-- Bottom 2-Column Overview Dashboard -->
      <div class="overview-dashboard-grid">
        <NCard title="监控站点实时状态" class="record-card">
          <div class="overview-site-row">
            <div class="site-card-identity">
              <span class="site-avatar">NS</span>
              <div>
                <h3 class="site-card-title">NodeSeek 官方 RSS</h3>
                <span class="site-card-sub">官方新帖 RSS 采集适配器</span>
              </div>
            </div>
            <div class="record-meta" style="margin: 0">
              <NTag :type="overview.site.enabled ? 'success' : 'default'">{{
                overview.site.enabled ? '来源已启用' : '来源已暂停'
              }}</NTag>
              <NTag
                :type="
                  overview.scheduler.enabled && overview.scheduler.healthy ? 'info' : 'warning'
                "
              >
                {{
                  overview.scheduler.enabled && overview.scheduler.healthy
                    ? '后台调度运行中'
                    : '后台调度未就绪'
                }}
              </NTag>
            </div>
          </div>

          <div class="kv-grid" style="margin-top: 14px">
            <div class="kv-box">
              <p>最近成功采集：{{ localDate(overview.site.last_success_at) }}</p>
            </div>
            <div class="kv-box">
              <p>最近尝试：{{ localDate(overview.site.last_attempt_at) }}</p>
            </div>
            <div class="kv-box">
              <p>
                最近窗口：{{ overview.site.window_count }} 条 · 连续失败
                {{ overview.site.failures }} 次
              </p>
            </div>
            <div class="kv-box">
              <p>最近连接错误：{{ sourceError(overview.site.last_error_code) }}</p>
            </div>
          </div>

          <p v-if="overview.site.failures" class="muted" style="margin-top: 8px">
            下次允许尝试：{{ localDate(overview.site.next_attempt_at) }}
          </p>
          <NAlert v-if="overview.site.possible_gap" type="warning" class="notice">
            曾发现可能的 RSS 窗口缺口（{{
              localDate(overview.site.last_gap_at)
            }}），无法据此确定漏帖数量。
          </NAlert>
        </NCard>

        <NCard title="采集与投递运行说明" class="record-card">
          <div class="info-list">
            <div class="info-item">
              <strong>窗口采集与基线防刷屏</strong>
              <p class="muted">
                仅处理 RSS
                当前返回的窗口；首次启用或主动暂停后恢复只建立基线，不推送旧帖。长时间停机可能无法补齐已移出窗口的帖子。
              </p>
            </div>
            <div class="info-item">
              <strong>后台常驻与投递确认</strong>
              <p class="muted">
                浏览器关闭不影响后台运行。统计基于本地保留记录，渠道接受不代表收件人已阅读，SMTP
                成功只表示邮件服务器接受。
              </p>
            </div>
          </div>
        </NCard>
      </div>
    </template>
  </section>
</template>
