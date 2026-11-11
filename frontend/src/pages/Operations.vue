<script setup lang="ts">
import { computed, onMounted } from 'vue'
import Content from './Content.vue'
import NotificationRecords from './NotificationRecords.vue'
import OperationsStatus from './OperationsStatus.vue'
import { signedIn, state } from '../store'
import { prepareRecords, recordTabs } from '../recordQueries'
const props = defineProps<{ section: string; recordId?: string; initialTarget?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const tabs = [
  { id: 'status', label: '运行状态', path: '/operations/status' },
  { id: 'content', label: '内容与命中', path: '/operations/content' },
  { id: 'records', label: '通知记录', path: '/operations/deliveries' },
]
const isRecords = computed(() => (recordTabs as readonly string[]).includes(props.section))
const current = computed(() => (isRecords.value ? 'records' : props.section))
onMounted(() => {
  if (signedIn.value)
    for (const tab of recordTabs) void prepareRecords(tab, state.settings.timezone).catch(() => {})
})
</script>
<template>
  <template v-if="!recordId">
    <section class="page-heading">
      <div>
        <p class="eyebrow">WATCHING THE WATCHERS</p>
        <h1 tabindex="-1">运行中心</h1>
        <p class="subtitle">每条链路是否正常，出了什么问题，怎么确认修好。</p>
      </div>
    </section>
    <nav class="page-tabs" aria-label="运行中心分类">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: current === tab.id }"
        :aria-current="current === tab.id ? 'page' : undefined"
        @click="emit('navigate', tab.path)"
      >
        {{ tab.label }}
      </button>
    </nav>
  </template>
  <!-- The previous section stays until the next one has its data (viewReady.ts). -->
  <Suspense suspensible>
    <OperationsStatus v-if="section === 'status'" @navigate="(path) => emit('navigate', path)" />
    <Content
      v-else-if="section === 'content'"
      :key="recordId || 'list'"
      :selected-id="recordId"
      @navigate="(path) => emit('navigate', path)"
    />
    <NotificationRecords
      v-else
      :tab="section"
      :record-id="recordId"
      :initial-target="initialTarget"
      @navigate="(path) => emit('navigate', path)"
    />
  </Suspense>
</template>
