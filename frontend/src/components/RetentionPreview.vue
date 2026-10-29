<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { formatTime, request } from '../store'
interface Preview {
  days: number
  checked_at: number
  counts: Record<string, number>
  protected_posts: number
}
const props = defineProps<{ days: number }>()
const data = ref<Preview>(),
  open = ref(false),
  busy = ref(false),
  error = ref('')
let generation = 0,
  active = true
const valid = computed(() => Number.isInteger(props.days) && props.days >= 1 && props.days <= 365)
function close() {
  ++generation
  open.value = false
  data.value = undefined
  error.value = ''
  busy.value = false
}
// A changed draft invalidates the estimate; it is re-read only on request.
watch(() => props.days, close)
onBeforeUnmount(() => {
  active = false
})
const labels: Record<string, string> = {
  posts: '帖子',
  deliveries: '自动投递',
  tests: '目标测试',
  manual: '手动重发',
  source_runs: '采集记录',
}
async function toggle() {
  if (open.value) return close()
  if (!valid.value) return
  const current = ++generation
  open.value = true
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
  <div class="retention-preview">
    <button
      class="button"
      type="button"
      :disabled="!valid"
      :aria-expanded="open"
      aria-controls="retention-preview-result"
      @click="toggle"
    >
      {{ open ? '收起预览' : '预览清理影响' }}
    </button>
    <div v-if="open" id="retention-preview-result" class="retention-preview-box">
      <p v-if="busy" class="small-note" role="status">正在估算…</p>
      <p v-else-if="error" class="form-errors" role="alert">{{ error }}</p>
      <template v-else-if="data">
        <p class="retention-preview-title">按 {{ data.days }} 天保留，预计清理</p>
        <dl class="detail-grid retention-counts" aria-label="清理预估数量">
          <div v-for="(label, key) in labels" :key="key">
            <dt>{{ label }}</dt>
            <dd>{{ data.counts[key] || 0 }}</dd>
          </div>
        </dl>
        <p class="small-note">
          <template v-if="data.protected_posts"
            >{{ data.protected_posts }} 篇帖子因投递未完成暂时保留。</template
          >估算于
          {{
            formatTime(new Date(data.checked_at * 1000).toISOString())
          }}，仅供参考，不会删除任何记录。
        </p>
      </template>
    </div>
  </div>
</template>
<style scoped>
.retention-preview {
  display: grid;
  gap: 12px;
  justify-items: start;
}
.retention-preview-box {
  display: grid;
  gap: 14px;
  width: 100%;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fafbfc;
}
.retention-preview-box > p {
  margin: 0;
}
.retention-preview-title {
  font-size: 13px;
  font-weight: 600;
  color: #2f343b;
}
</style>
