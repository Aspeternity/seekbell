<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { loadTelegramPreview, state } from '@workspace'
import type { TelegramPreviewMessage } from '../notificationPreview'
const props = defineProps<{ summary: boolean; summaryLimit: number }>()
const message = ref<TelegramPreviewMessage>()
const error = ref('')
const loading = ref(false)
let generation = 0
let requestTimer: ReturnType<typeof setTimeout> | undefined
let feedbackTimer: ReturnType<typeof setTimeout> | undefined
const titleEnd = computed(() => {
  const entity = message.value?.entities.find(
    (entity) => entity.type === 'bold' && entity.offset === 0,
  )
  return entity?.length || 0
})
const title = computed(() => message.value?.text.slice(0, titleEnd.value) || '')
const body = computed(() => message.value?.text.slice(titleEnd.value).replace(/^\n\n/, '') || '')
const button = computed(() => message.value?.reply_markup?.inline_keyboard[0]?.[0]?.text)
function reload(delay = 0) {
  const current = ++generation
  clearTimeout(requestTimer)
  clearTimeout(feedbackTimer)
  loading.value = false
  error.value = ''
  const limit = props.summary ? props.summaryLimit : 0
  if (!Number.isInteger(limit) || limit < 0 || limit > 1000) {
    error.value = '摘要长度应为 0–1000 的整数，调整后将更新预览。'
    return
  }
  const options = {
    include_summary: props.summary,
    summary_limit: limit,
    timezone: state.settings.timezone,
  }
  feedbackTimer = setTimeout(() => (loading.value = true), 200)
  const run = async () => {
    try {
      const result = await loadTelegramPreview(options)
      if (current === generation) message.value = result
    } catch {
      if (current === generation) error.value = '消息预览暂时无法生成，请重试。'
    } finally {
      if (current === generation) {
        clearTimeout(feedbackTimer)
        loading.value = false
      }
    }
  }
  if (delay) requestTimer = setTimeout(run, delay)
  else void run()
}
let initial = true
watch(
  () => [props.summary, props.summaryLimit, state.settings.timezone],
  () => {
    reload(initial ? 0 : 150)
    initial = false
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  generation++
  clearTimeout(requestTimer)
  clearTimeout(feedbackTimer)
})
</script>
<template>
  <h3 v-if="message" class="telegram-preview-title">{{ title }}</h3>
  <p v-if="message" class="telegram-preview-body">{{ body }}</p>
  <span v-if="button" class="telegram-preview-link">{{ button }}</span>
  <p v-if="loading" class="small-note" role="status">
    {{ message ? '正在更新预览…' : '正在生成消息预览…' }}
  </p>
  <div v-if="error" class="small-note telegram-preview-error" role="alert">
    <p>{{ error }}{{ message ? '当前保留上次预览。' : '' }}</p>
    <button type="button" class="text-link" @click="reload()">重新生成预览</button>
  </div>
</template>
<style scoped>
.telegram-preview-title {
  font-weight: 600;
}
.telegram-preview-body {
  white-space: pre-wrap;
}
.telegram-preview-link {
  display: block;
  margin-top: 14px;
  border: 1px solid #e3e9ed;
  border-radius: 6px;
  padding: 8px 12px;
  text-align: center;
  color: #a4714d;
  font-size: 12px;
  line-height: 1.6;
}
.telegram-preview-error p {
  margin: 10px 0 4px;
}
</style>
