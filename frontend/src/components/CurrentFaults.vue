<script setup lang="ts">
import { ref } from 'vue'
import { formatTime, request } from '../store'
import { useRemote } from '../history'
import type { Page } from '../history'
import Pagination from './Pagination.vue'
import ReadRegion from './ReadRegion.vue'
interface Fault {
  component: string
  label: string
  code: string | null
  since: number
}
const page = ref(1)
const faults = useRemote(
  () => request<Page<Fault>>('manage/alerts/state?page=' + page.value),
  () => [page.value],
  { cacheKey: () => 'alerts:faults:' + page.value, keepPrevious: true },
)
const stamp = (value: number) => formatTime(new Date(value * 1000).toISOString())
defineExpose({ reload: faults.reload })
</script>
<template>
  <ReadRegion
    :loading="faults.loading.value"
    :error="faults.error.value"
    :has-data="!!faults.data.value"
    :stale="faults.stale.value"
    :min-height="80"
    @retry="faults.reload"
    ><template v-if="faults.data.value">
      <p v-if="!faults.data.value.total" class="small-note">当前没有已记录的故障。</p>
      <article
        v-for="fault in faults.data.value.items"
        :key="fault.component"
        class="history-evaluation"
      >
        <strong>{{ fault.label }}</strong>
        <p>{{ fault.code }} · {{ stamp(fault.since) }}</p>
      </article>
      <Pagination
        v-if="faults.data.value.total > 20"
        label="当前故障"
        :page="page"
        :page-size="20"
        :total="faults.data.value.total"
        @change="page = $event"
      /> </template
  ></ReadRegion>
</template>
