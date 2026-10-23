<script setup lang="ts">
import Icon from '../components/Icon.vue'
import NotificationTabs from '../components/NotificationTabs.vue'
import Targets from './Targets.vue'
import Records from './Records.vue'
defineProps<{ tab: string; recordId?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
</script>
<template>
  <template v-if="!recordId">
    <section class="page-heading">
      <div>
        <p class="eyebrow">GOOD NEWS, YOUR WAY</p>
        <h1 tabindex="-1">通知管理</h1>
        <p class="subtitle">把关心的消息，送到你习惯的地方。</p>
      </div>
      <button class="button primary" @click="emit('navigate', '/target/new')">
        <Icon name="plus" :size="18" />添加通知目标
      </button>
    </section>
    <NotificationTabs :tab="tab" @navigate="(path) => emit('navigate', path)" />
  </template>
  <Targets v-if="tab === 'targets'" @navigate="(path) => emit('navigate', path)" />
  <Records
    v-else
    :key="tab + ':' + (recordId || '')"
    :tab="tab"
    :record-id="recordId"
    @navigate="(path) => emit('navigate', path)"
  />
</template>
