<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getTargetDeletePreview, removeTarget } from '@workspace'
import type { Target } from '../shared'
import type { TargetDeletePreview } from '../targetDeletion'
import Icon from './Icon.vue'
const props = defineProps<{ target: Target }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const preview = ref<TargetDeletePreview>()
const loading = ref(true),
  busy = ref(false),
  error = ref('')
let opener: HTMLElement | null = null
async function load() {
  if (busy.value) return
  loading.value = true
  error.value = ''
  preview.value = undefined
  try {
    preview.value = await getTargetDeletePreview(props.target.id)
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    loading.value = false
  }
}
async function remove() {
  if (busy.value || loading.value || !preview.value) return
  busy.value = true
  error.value = ''
  try {
    await removeTarget(props.target, preview.value.confirmation)
    emit('close')
  } catch (reason) {
    error.value = (reason as Error).message
    preview.value = undefined
  } finally {
    busy.value = false
  }
}
function close() {
  if (!busy.value) emit('close')
}
onMounted(() => {
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  dialog.value?.showModal()
  load()
})
onBeforeUnmount(() => {
  dialog.value?.close()
  if (opener?.isConnected) opener.focus({ preventScroll: true })
})
</script>
<template>
  <dialog
    ref="dialog"
    class="dialog target-delete-dialog"
    aria-labelledby="target-delete-title"
    aria-describedby="target-delete-note"
    @cancel.prevent="close"
  >
    <span class="dialog-icon"><Icon name="trash" :size="23" /></span>
    <h2 id="target-delete-title">删除「{{ preview?.target_name || target.name }}」？</h2>
    <p v-if="loading" role="status">正在读取关联任务…</p>
    <div v-if="error" class="form-errors" role="alert">
      <p>{{ error }}</p>
      <button class="button" :disabled="loading" @click="load">重新加载</button>
    </div>
    <template v-if="preview">
      <template v-if="preview.tasks.length">
        <p class="target-delete-intro">删除后，以下任务将没有通知目标：</p>
        <ul class="target-delete-list" aria-label="删除后没有通知目标的任务" tabindex="0">
          <li v-for="task in preview.tasks" :key="task.id">
            <strong>{{ task.name }}</strong>
            <span>{{ task.enabled ? '删除后暂停' : '保持暂停' }}</span>
          </li>
        </ul>
      </template>
      <p v-if="preview.alerts_disabled">此目标也用于系统告警，删除后系统告警将关闭。</p>
    </template>
    <p id="target-delete-note">任务规则和历史记录会保留。</p>
    <div class="dialog-actions">
      <button class="button" :disabled="busy" @click="close">取消</button>
      <button class="button primary" :disabled="busy || loading || !preview" @click="remove">
        {{ busy ? '正在删除…' : '删除' }}
      </button>
    </div>
  </dialog>
</template>
<style scoped>
.target-delete-dialog {
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
}
.target-delete-dialog h2,
.target-delete-list strong {
  overflow-wrap: anywhere;
}
.target-delete-dialog .target-delete-intro {
  margin-bottom: 12px;
}
.target-delete-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: min(30dvh, 240px);
  overflow-y: auto;
}
.target-delete-list li {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid #eee9e2;
  font-size: 13px;
  line-height: 1.6;
}
.target-delete-list strong {
  flex: 1;
  min-width: 0;
  font-weight: 600;
}
.target-delete-list span {
  flex-shrink: 0;
  color: #8b7462;
  font-size: 12px;
}
</style>
