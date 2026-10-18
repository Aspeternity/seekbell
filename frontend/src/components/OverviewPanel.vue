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
      <h2>概览</h2>
      <NButton :loading="loading" @click="load">刷新概览</NButton>
    </div>
    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>
    <template v-if="overview">
      <NAlert v-if="!overview.scheduler.healthy" type="error" class="notice"
        >后台组件异常，请检查服务并重启恢复；存活检查与业务健康分开。</NAlert
      >
      <NAlert v-else-if="!overview.scheduler.enabled" type="warning" class="notice"
        >后台调度已由启动配置关闭，当前只保存和查看配置。</NAlert
      >
      <NCard title="NodeSeek 官方 RSS" class="record-card">
        <div class="record-meta">
          <NTag :type="overview.site.enabled ? 'success' : 'default'">{{
            overview.site.enabled ? '来源已启用' : '来源已暂停'
          }}</NTag>
          <NTag>{{
            overview.scheduler.enabled && overview.scheduler.healthy
              ? '后台调度运行中'
              : '后台调度未就绪'
          }}</NTag>
        </div>
        <p>最近成功采集：{{ localDate(overview.site.last_success_at) }}</p>
        <p>最近尝试：{{ localDate(overview.site.last_attempt_at) }}</p>
        <p>
          最近窗口：{{ overview.site.window_count }} 条 · 连续失败 {{ overview.site.failures }} 次
        </p>
        <p>最近连接错误：{{ sourceError(overview.site.last_error_code) }}</p>
        <p v-if="overview.site.failures">
          下次允许尝试：{{ localDate(overview.site.next_attempt_at) }}
        </p>
        <NAlert v-if="overview.site.possible_gap" type="warning"
          >曾发现可能的 RSS 窗口缺口（{{
            localDate(overview.site.last_gap_at)
          }}），无法据此确定漏帖数量。</NAlert
        >
        <p class="muted">
          仅处理 RSS
          当前返回的窗口；长时间停机可能无法补齐已移出窗口的帖子。浏览器关闭不影响后台运行。
        </p>
      </NCard>
      <div class="stats-grid" aria-label="本地统计">
        <NCard title="启用任务 / 全部任务"
          >{{ overview.counts.enabled_tasks }} / {{ overview.counts.tasks }}</NCard
        >
        <NCard title="通知目标">{{ overview.counts.targets }}</NCard>
        <NCard title="本地帖子">{{ overview.counts.posts }}</NCard>
        <NCard title="规则命中">{{ overview.counts.hits }}</NCard>
        <NCard title="等待 / 重试 / 在途"
          >{{ overview.counts.deliveries.pending }} / {{ overview.counts.deliveries.retry }} /
          {{ overview.counts.deliveries.leased }}</NCard
        >
        <NCard title="渠道接受 / 失败 / 已取消"
          >{{ overview.counts.deliveries.sent }} / {{ overview.counts.deliveries.failed }} /
          {{ overview.counts.deliveries.cancelled }}</NCard
        >
      </div>
      <NAlert v-if="overview.counts.uncertain" type="warning" class="notice"
        >{{
          overview.counts.uncertain
        }}
        条投递曾出现结果未知，后续成功仍保留标记；重试可能重复。</NAlert
      >
      <p class="muted">
        统计基于本地保留记录，不代表收件人已阅读。SMTP 成功只表示邮件服务器接受。状态每 5
        秒刷新；时间按系统显示时区显示。
      </p>
    </template>
  </section>
</template>
