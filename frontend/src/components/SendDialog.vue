<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Icon from './Icon.vue'
import { request } from '../store'
import { resultLabels, kindLabels } from '../history'
interface Preview {
  target_id: string
  target_name: string
  kind: string
  revision: number
  enabled: boolean
  source_event_id: string | null
  title: string
  uncertain: boolean
}
const props = defineProps<{ action: 'test' | 'resend'; id: string }>()
const emit = defineEmits<{ close: []; complete: [path: string] }>()
const dialog = ref<HTMLDialogElement>()
const preview = ref<Preview>()
const busy = ref(false),
  loading = ref(true),
  error = ref('')
const result = ref<{ id: string; result: string; finished_at: number | null }>()
// getRandomValues also works for the supported direct HTTP deployment.
const bytes = crypto.getRandomValues(new Uint8Array(16))
bytes[6] = (bytes[6]! & 15) | 64
bytes[8] = (bytes[8]! & 63) | 128
const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
const requestId = [
  hex.slice(0, 8),
  hex.slice(8, 12),
  hex.slice(12, 16),
  hex.slice(16, 20),
  hex.slice(20),
].join('-')
const base =
  props.action === 'test' ? 'targets/' + props.id + '/test' : 'deliveries/' + props.id + '/resend'
async function load() {
  loading.value = true
  error.value = ''
  try {
    preview.value = await request<Preview>('manage/' + base + '-preview')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
async function send() {
  if (busy.value || !preview.value) return
  busy.value = true
  error.value = ''
  try {
    result.value = await request('manage/' + base, 'POST', {
      request_id: requestId,
      revision: preview.value.revision,
    })
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function close() {
  if (!busy.value) emit('close')
}
onMounted(() => {
  dialog.value?.showModal()
  load()
})
</script>
<template>
  <dialog ref="dialog" class="dialog" @cancel.prevent="close">
    <div class="dialog-top">
      <span class="dialog-icon"><Icon name="send" :size="23" /></span
      ><button class="icon-button" :disabled="busy" aria-label="关闭通知操作" @click="close">
        <Icon name="close" />
      </button>
    </div>
    <h2>{{ action === 'test' ? '测试通知目标' : '手动重发这条通知？' }}</h2>
    <p v-if="loading" role="status">正在读取当前目标配置…</p>
    <div v-if="error" class="form-errors" role="alert">
      <p>{{ error }}</p>
      <button v-if="!preview" class="button" @click="load">重新加载</button>
    </div>
    <template v-if="preview">
      <p>
        <strong>{{ preview.target_name }}</strong> · {{ kindLabels[preview.kind] }} · 配置版本
        {{ preview.revision }}
      </p>
      <p v-if="action === 'test'">
        将发送一条 SeekBell 测试消息。暂停目标也可测试；测试独立记录，不改变自动通知。
      </p>
      <template v-else
        ><p class="record-title">{{ preview.title }}</p>
        <p>
          使用当前目标配置发送原消息快照。保留原投递记录，不改变自动去重；手动重发单独留证，不自动重试。
        </p>
        <p class="warning-note">
          {{
            preview.uncertain
              ? '原投递曾有结果未知，接收端可能已经收到；重发可能重复。'
              : '接收端可能已经收到原通知，确认后将再次发送。'
          }}
        </p></template
      >
      <p v-if="result" role="status" class="info-note">
        {{ resultLabels[result.result] || '结果已记录'
        }}{{ result.finished_at === null ? '；尝试尚未结束或曾被中断，请查看记录。' : '' }}
      </p>
      <p v-if="result?.result === 'unknown'" class="small-note">
        接收端可能已经收到，不会自动重试。刷新记录可查看后续保存的结果。
      </p>
      <p v-if="preview.kind === 'smtp'" class="small-note">
        成功只表示 SMTP 服务器接受，不保证进入收件箱。
      </p>
      <div class="dialog-actions spaced">
        <button class="button" :disabled="busy" @click="close">
          {{ result ? '关闭' : '取消' }}</button
        ><button
          v-if="result"
          class="button primary"
          @click="
            emit(
              'complete',
              '/notifications/' + (action === 'test' ? 'tests' : 'manual') + '/' + result.id,
            )
          "
        >
          查看记录</button
        ><button v-else class="button primary" :disabled="busy" @click="send">
          {{
            busy
              ? '正在发送…'
              : error
                ? '查询或重试本次操作'
                : action === 'test'
                  ? '确认发送测试消息'
                  : '确认手动重发'
          }}
        </button>
      </div>
      <p v-if="error" class="small-note">
        重试沿用同一操作标识，已建立的尝试不会再次发送；也可到记录页查询。
      </p>
    </template>
    <button v-else-if="!loading" class="button" @click="close">关闭</button>
  </dialog>
</template>
