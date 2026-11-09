<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { signedIn } from '../store'
import { historyGet } from '../history'
import Feedback from './Feedback.vue'
import {
  notificationCounts,
  countsLoading,
  countsError,
  countsRevision,
  loadNotificationCounts,
} from '../notificationCounts'
const props = defineProps<{ tab: string; pendingTab?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
function reload() {
  if (signedIn.value) void loadNotificationCounts(() => historyGet('counts'))
}
function visible() {
  if (document.visibilityState === 'visible') reload()
}
watch(countsRevision, reload, { immediate: true })
watch(() => props.tab, reload)
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
  <div class="notification-tabs-region">
    <nav class="record-tabs" aria-label="通知记录分类">
      <button
        v-for="item in [
          { id: 'deliveries', label: '投递记录', count: notificationCounts?.deliveries },
          { id: 'manual', label: '手动重发', count: notificationCounts?.manual },
          { id: 'tests', label: '测试记录', count: notificationCounts?.tests },
        ]"
        :key="item.id"
        :class="{ active: tab === item.id }"
        :aria-current="tab === item.id ? 'page' : undefined"
        :aria-busy="pendingTab === item.id || undefined"
        @click="emit('navigate', '/operations/' + item.id)"
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
    <div class="notification-tabs-feedback">
      <Feedback
        :loading="countsLoading"
        :error="countsError"
        :retained="!!notificationCounts"
        :delay="200"
        subtle
        @retry="reload"
      />
    </div>
  </div>
</template>
<style scoped>
.notification-tabs-region {
  position: relative;
  margin-bottom: 14px;
}
.record-tabs {
  display: inline-flex;
  max-width: 100%;
  overflow-x: auto;
  gap: 2px;
  padding: 3px;
  background: #eff1f4;
  border-radius: 8px;
}
.record-tabs button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #4c5561;
  white-space: nowrap;
}
.record-tabs button.active {
  background: #fff;
  color: #ad643c;
  font-weight: 550;
}
.notification-tabs-feedback {
  position: absolute;
  top: 100%;
  right: 8px;
  z-index: 3;
}
.notification-tabs-feedback :deep(.remote-feedback) {
  margin: 0;
  padding: 4px 8px;
  background: #fff;
  border-radius: 4px;
}

.notification-count {
  min-width: 16px;
  display: inline-block;
}
</style>
