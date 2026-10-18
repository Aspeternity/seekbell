<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NDescriptions,
  NDescriptionsItem,
  NSpin,
  NTag,
  zhCN,
} from 'naive-ui'
import { loadSystemInfo } from './api'
import type { VersionInfo } from './api'

const info = ref<VersionInfo | null>(null)
const loading = ref(false)
const error = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  info.value = null
  try {
    info.value = await loadSystemInfo()
  } catch (cause) {
    error.value =
      cause instanceof Error ? cause.message : '无法连接服务，请检查后端运行状态后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <NConfigProvider
    :locale="zhCN"
    :theme-overrides="{ common: { primaryColor: '#1b645b', primaryColorHover: '#257d71' } }"
  >
    <main class="shell">
      <header class="header">
        <a class="brand" href="/" aria-label="SeekBell 首页"><span class="bell">S</span>SeekBell</a>
        <NTag :bordered="false">M1 · 核心验证</NTag>
      </header>

      <section class="intro" aria-labelledby="page-title">
        <p class="eyebrow">从新帖，到你关心的消息</p>
        <h1 id="page-title">SeekBell 已起步。</h1>
        <p class="description">
          为 NodeSeek 新帖监控建立可验证的运行基础。当前提供服务状态与版本信息。
        </p>
      </section>

      <NCard title="运行信息" class="status-card">
        <template #header-extra>
          <NButton secondary :loading="loading" @click="refresh">刷新状态</NButton>
        </template>
        <NSpin :show="loading">
          <div role="status" aria-live="polite" :aria-busy="loading">
            <NAlert v-if="error" title="暂时无法读取状态" type="error">{{ error }}</NAlert>
            <NDescriptions v-else-if="info" :column="1" label-placement="left" bordered>
              <NDescriptionsItem label="服务状态">
                <NTag type="success" size="small" :bordered="false">已就绪</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem label="应用版本">{{ info.version }}</NDescriptionsItem>
              <NDescriptionsItem label="代码版本">
                <code>{{ info.build_revision }}</code>
              </NDescriptionsItem>
              <NDescriptionsItem label="数据库迁移">
                <code>{{ info.database_revision ?? '尚未初始化' }}</code>
              </NDescriptionsItem>
            </NDescriptions>
            <p v-else>正在读取服务状态…</p>
          </div>
        </NSpin>
      </NCard>

      <NAlert title="当前阶段" type="info" :bordered="false" class="phase-note">
        监控、通知和管理员功能将在后续阶段接入。当前不会采集论坛或发送通知。
      </NAlert>
      <footer>SeekBell · 自托管的新帖监控与通知</footer>
    </main>
  </NConfigProvider>
</template>
