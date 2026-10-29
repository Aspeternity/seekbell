<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatTime, request } from '../store'
import { useRemote } from '../history'
import type { Page } from '../history'
import Feedback from './Feedback.vue'
import Pagination from './Pagination.vue'
interface Fault {
  component: string
  label: string
  code: string | null
  since: number
}
const emit = defineEmits<{ total: [value: number | undefined] }>()
const page = ref(1)
const faults = useRemote(
  () => request<Page<Fault>>('manage/alerts/state?page=' + page.value),
  () => [page.value],
  { cacheKey: () => 'alerts:faults:' + page.value, keepPrevious: true },
)
watch(
  () => faults.data.value?.total,
  (total) => emit('total', total),
  { immediate: true },
)
const stamp = (value: number) => formatTime(new Date(value * 1000).toISOString())
defineExpose({ reload: faults.reload })
</script>
<template>
  <Feedback
    :loading="false"
    :error="faults.error.value"
    :retained="!!faults.data.value"
    @retry="faults.reload"
  />
  <ul v-if="faults.data.value?.total" class="fault-list" aria-label="当前故障">
    <li v-for="fault in faults.data.value.items" :key="fault.component">
      <strong>{{ fault.label }}</strong>
      <code v-if="fault.code">{{ fault.code }}</code>
      <span>{{ stamp(fault.since) }} 起</span>
    </li>
  </ul>
  <Pagination
    v-if="(faults.data.value?.total ?? 0) > 20"
    label="当前故障"
    :page="page"
    :page-size="20"
    :total="faults.data.value!.total"
    @change="page = $event"
  />
</template>
