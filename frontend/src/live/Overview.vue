<script setup lang="ts">
import Icon from '../prototype/components/Icon.vue'
import { state } from './store'
const emit = defineEmits<{ navigate: [path: string] }>()
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">A LITTLE LESS NOISE</p>
      <h1 tabindex="-1">留意你关心的。</h1>
      <p class="subtitle">从一个网站，一条规则，开始你的信息空间。</p>
    </div>
    <button class="button primary" @click="emit('navigate', '/task/new')">
      <Icon name="plus" :size="18" />新建任务
    </button>
  </section>
  <div class="metric-strip">
    <div>
      <span>已添加网站</span><strong>{{ state.websites.length }}</strong>
    </div>
    <div>
      <span>监控任务</span><strong>{{ state.tasks.length }}</strong>
    </div>
    <div>
      <span>通知目标</span><strong>{{ state.targets.length }}</strong>
    </div>
    <p><Icon name="shield" :size="18" />配置已保存到服务端</p>
  </div>
  <section class="panel empty-state">
    <Icon name="globe" :size="36" />
    <h2>{{ state.websites.length ? '关注已经就绪' : '从第一个关心的网站开始' }}</h2>
    <p>先添加内置网站，配置通知目标，再保存你的监控任务。</p>
    <button class="button primary" @click="emit('navigate', '/websites')">管理监控网站</button>
    <button class="button" @click="emit('navigate', '/notifications/targets')">配置通知目标</button>
  </section>
  <div class="bottom-note">
    <Icon name="clock" :size="18" />
    <p>
      当前已接入认证、配置保存与历史查询。采集、通知发送与概览统计将在后续阶段接入，尚未启动后台监控。
    </p>
  </div>
</template>
