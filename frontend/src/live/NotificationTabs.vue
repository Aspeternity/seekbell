<script setup lang="ts">
import { state } from './store'
import { historyGet, useRemote } from './history'
import type { Page } from './history'
defineProps<{ tab: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const counts = useRemote(
  async () => {
    const values = await Promise.all(
      ['deliveries', 'manual', 'tests'].map((path) =>
        historyGet<Page<unknown>>(path, { page_size: 1 }),
      ),
    )
    return { deliveries: values[0]!.total, manual: values[1]!.total, tests: values[2]!.total }
  },
  () => [],
)
</script>
<template>
  <nav class="page-tabs" aria-label="通知管理分类">
    <button
      v-for="item in [
        { id: 'targets', label: '通知目标', count: state.targets.length },
        { id: 'deliveries', label: '投递记录', count: counts.data.value?.deliveries },
        { id: 'manual', label: '手动重发', count: counts.data.value?.manual },
        { id: 'tests', label: '测试记录', count: counts.data.value?.tests },
      ]"
      :key="item.id"
      :class="{ active: tab === item.id }"
      :aria-current="tab === item.id ? 'page' : undefined"
      @click="emit('navigate', '/notifications/' + item.id)"
    >
      {{ item.label }}<span :title="counts.error.value || undefined">{{ item.count ?? '—' }}</span>
    </button>
  </nav>
</template>
