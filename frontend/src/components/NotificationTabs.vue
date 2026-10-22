<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { state, signedIn } from '../store'
import { historyGet } from '../history'
import Feedback from './Feedback.vue'
import {
  notificationCounts,
  countsLoading,
  countsError,
  countsRevision,
  loadNotificationCounts,
} from '../notificationCounts'
defineProps<{ tab: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
function reload() {
  if (signedIn.value) void loadNotificationCounts(() => historyGet('counts'))
}
function visible() {
  if (document.visibilityState === 'visible') reload()
}
watch(countsRevision, reload, { immediate: true })
onMounted(() => {
  window.addEventListener('focus', reload)
  document.addEventListener('visibilitychange', visible)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', reload)
  document.removeEventListener('visibilitychange', visible)
})
</script>
<template>
  <nav class="page-tabs" aria-label="通知管理分类">
    <button
      v-for="item in [
        { id: 'targets', label: '通知目标', count: state.targets.length },
        { id: 'deliveries', label: '投递记录', count: notificationCounts?.deliveries },
        { id: 'manual', label: '手动重发', count: notificationCounts?.manual },
        { id: 'tests', label: '测试记录', count: notificationCounts?.tests },
      ]"
      :key="item.id"
      :class="{ active: tab === item.id }"
      :aria-current="tab === item.id ? 'page' : undefined"
      @click="emit('navigate', '/notifications/' + item.id)"
    >
      {{ item.label
      }}<span
        class="notification-count"
        :aria-busy="countsLoading"
        :aria-label="item.count === undefined ? '数量读取中' : undefined"
        >{{ item.count ?? '' }}</span
      >
    </button>
  </nav>
  <Feedback
    :loading="countsLoading"
    :error="countsError"
    :retained="!!notificationCounts"
    :delay="200"
    subtle
    @retry="reload"
  />
</template>
<style scoped>
.notification-count {
  min-width: 16px;
  display: inline-block;
}
</style>
