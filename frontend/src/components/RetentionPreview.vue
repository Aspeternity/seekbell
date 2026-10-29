<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { formatTime, request } from '../store'
interface Preview {
  days: number
  checked_at: number
  counts: Record<string, number>
  protected_posts: number
}
const props = defineProps<{ days: number }>()
const data = ref<Preview>(),
  busy = ref(false),
  error = ref('')
let generation = 0,
  active = true
watch(
  () => props.days,
  () => {
    ++generation
    data.value = undefined
    error.value = ''
    busy.value = false
  },
)
onBeforeUnmount(() => {
  active = false
})
const labels: Record<string, string> = {
  posts: '帖子',
  deliveries: '已完成自动投递',
  tests: '已完成目标测试',
  manual: '已完成手动重发',
  source_runs: '采集记录',
}
async function preview() {
  if (busy.value || !Number.isInteger(props.days) || props.days < 1 || props.days > 365) return
  const current = ++generation
  busy.value = true
  error.value = ''
  try {
    const value = await request<Preview>('manage/retention/preview?days=' + props.days)
    if (active && current === generation) data.value = value
  } catch (e) {
    if (active && current === generation) error.value = (e as Error).message
  } finally {
    if (current === generation) busy.value = false
  }
}
</script>
<template>
  <div class="form-stack">
    <button
      class="button"
      type="button"
      :disabled="busy || !Number.isInteger(days) || days < 1 || days > 365"
      @click="preview"
    >
      {{ busy ? '正在估算…' : '预览清理影响' }}
    </button>
    <p v-if="error" class="form-errors" role="alert">{{ error }}</p>
    <template v-if="data">
      <h3>按 {{ data.days }} 天保留预估</h3>
      <dl class="detail-grid">
        <div v-for="(label, key) in labels" :key="key">
          <dt>{{ label }}</dt>
          <dd>{{ data.counts[key] }}</dd>
        </div>
      </dl>
      <p class="small-note">
        另有
        {{ data.protected_posts }}
        篇过期帖子因投递依赖暂时保留。判定和命中随可删除帖子清理；独立去重账本保留。
      </p>
      <p class="small-note">
        检查于
        {{
          formatTime(new Date(data.checked_at * 1000).toISOString())
        }}。这是只读估算，未保存策略、未执行删除；后台分批执行时数量可能变化，不代表可释放磁盘字节。
      </p>
    </template>
  </div>
</template>
