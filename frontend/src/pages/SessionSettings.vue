<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { confirmAction, request } from '../store'
import { stamp } from '../settings'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { untilShown } from '../viewReady'
interface Sessions {
  expires_at: number
  remembered: boolean
  other_sessions: number
}
// Raised after the administrator changes, which signs every other session out.
const props = defineProps<{ generation: number }>()
const emit = defineEmits<{ dirty: [value: boolean]; logout: [] }>()
const data = ref<Sessions>(),
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
    const value = await request<Sessions>('auth/sessions')
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
watch(
  () => props.generation,
  () => {
    done.value = ''
    void load()
  },
)
await untilShown(load())
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>登录会话</h2>
        <p>登录有效 12 小时；登录时勾选“保持登录”则为 30 天</p>
      </div>
      <div class="inline-actions">
        <button class="button" :disabled="busy || !data?.other_sessions" @click="revoke">
          退出其他会话
        </button>
        <button class="button" type="button" :disabled="busy" @click="emit('logout')">
          退出登录
        </button>
      </div>
    </div>
    <FormFeedback :error="error" @retry="load" />
    <ReadRegion :loading="busy && !data" error="" :has-data="!!data" :min-height="130">
      <div v-if="data" class="form-content form-stack">
        <dl class="detail-grid settings-metrics">
          <div>
            <dt>当前会话到期</dt>
            <dd>{{ stamp(data.expires_at) }}{{ data.remembered ? '（已保持登录）' : '' }}</dd>
          </div>
          <div>
            <dt>其他有效会话</dt>
            <dd>{{ data.other_sessions }}</dd>
          </div>
        </dl>
        <p v-if="done" class="info-note" role="status">{{ done }}</p>
      </div>
    </ReadRegion>
  </section>
</template>
