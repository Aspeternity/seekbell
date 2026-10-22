<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { historyGet, useRemote } from '../history'
import { state } from '../store'
import { readCacheRevision } from '../readCache'
const props = defineProps<{ modelValue: string; scope: string; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const before = ref(''),
  dates = ref<string[]>([])
watch(
  () => [props.scope, state.settings.timezone, readCacheRevision.value],
  () => {
    before.value = ''
    dates.value = []
  },
  { flush: 'sync' },
)
const remote = useRemote(
  () =>
    historyGet<{ items: string[]; next_before: string | null }>('dates', {
      scope: props.scope,
      timezone: state.settings.timezone,
      before: before.value,
    }),
  () => [props.scope, state.settings.timezone, before.value],
  {
    cacheKey: () =>
      JSON.stringify(['history:dates', props.scope, state.settings.timezone, before.value]),
  },
)
watch(
  remote.data,
  (value) => {
    if (value)
      dates.value = [...new Set([...(before.value ? dates.value : []), ...value.items])]
        .sort()
        .reverse()
  },
  { immediate: true },
)
const choices = computed(() =>
  props.modelValue && !dates.value.includes(props.modelValue)
    ? [props.modelValue, ...dates.value]
    : dates.value,
)
function choose(event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value === 'earlier') {
    before.value = remote.data.value?.next_before || ''
    select.value = props.modelValue
  } else emit('update:modelValue', select.value)
}
</script>
<template>
  <div class="history-date-filter">
    <select
      :value="modelValue"
      :aria-label="label"
      :aria-busy="remote.loading.value"
      @change="choose"
    >
      <option value="">全部日期</option>
      <option v-for="date in choices" :key="date" :value="date">
        {{ date.replaceAll('-', '/') }}
      </option>
      <option
        v-if="remote.data.value?.next_before"
        value="earlier"
        :disabled="remote.loading.value"
      >
        加载更早日期…
      </option>
    </select>
    <button
      v-if="remote.error.value"
      class="text-link"
      :aria-label="'重新读取' + label"
      :title="remote.error.value"
      @click="remote.reload"
    >
      重试日期
    </button>
  </div>
</template>
<style scoped>
.history-date-filter {
  width: 110px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
select {
  width: 100%;
}
@media (max-width: 760px) {
  .history-date-filter {
    flex: 1;
    min-width: 120px;
  }
  select {
    width: 100%;
  }
}
</style>
