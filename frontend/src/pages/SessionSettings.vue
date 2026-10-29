<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { confirmAction, formatTime, request } from '../store'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
const emit = defineEmits<{ dirty: [value: boolean] }>()
const data = ref<{ expires_at: number; other_sessions: number }>(),
  busy = ref(false),
  error = ref(''),
  done = ref('')
let active = true
onBeforeUnmount(() => {
  active = false
})
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const value = await request<{ expires_at: number; other_sessions: number }>('auth/sessions')
    if (active) data.value = value
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function revoke() {
  confirmAction(
    '退出其他会话？',
    '其他浏览器需要重新登录，当前会话继续使用。',
    async () => {
      if (busy.value) return
      busy.value = true
      error.value = ''
      emit('dirty', true)
      try {
        await request('auth/sessions/others', 'DELETE')
        if (active) {
          data.value!.other_sessions = 0
          done.value = '其他会话已退出。'
        }
      } catch (e) {
        if (active) error.value = (e as Error).message
      } finally {
        busy.value = false
        if (active) emit('dirty', false)
      }
    },
    '退出其他会话',
  )
}
onMounted(load)
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading"><h2>登录会话</h2></div>
    <FormFeedback :error="error" @retry="load" />
    <ReadRegion :loading="busy && !data" error="" :has-data="!!data" :min-height="130">
      <div v-if="data" class="form-content form-stack">
        <p>当前会话到期：{{ formatTime(new Date(data.expires_at * 1000).toISOString()) }}</p>
        <p>其他有效会话：{{ data.other_sessions }}</p>
        <p class="small-note">会话有效期为12小时。修改管理员资料也会使其他会话失效。</p>
        <p v-if="done" class="info-note" role="status">{{ done }}</p>
        <button class="button" :disabled="busy || !data.other_sessions" @click="revoke">
          退出其他会话
        </button>
      </div>
    </ReadRegion>
  </section>
</template>
