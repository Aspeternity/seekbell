<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { MAX_NAME } from '../backups'
import Icon from './Icon.vue'
// Asks for an optional backup name, both before "back up now" and when renaming.
const props = defineProps<{
  title: string
  action: string
  busyAction: string
  initial?: string
  busy: boolean
  error: string
}>()
const emit = defineEmits<{ submit: [name: string]; close: [] }>()
const dialog = ref<HTMLDialogElement>()
const input = ref<HTMLInputElement>()
const name = ref(props.initial ?? '')
let opener: HTMLElement | null = null
function close() {
  if (!props.busy) emit('close')
}
// A click on the backdrop targets the dialog itself, as does one on its padding:
// only a point outside the dialog box closes it.
function backdrop(event: MouseEvent) {
  const box = dialog.value?.getBoundingClientRect()
  if (event.target !== dialog.value || !box) return
  const inside =
    event.clientX >= box.left &&
    event.clientX <= box.right &&
    event.clientY >= box.top &&
    event.clientY <= box.bottom
  if (!inside) close()
}
onMounted(() => {
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  dialog.value?.showModal()
  input.value?.select()
})
onBeforeUnmount(() => {
  dialog.value?.close()
  if (opener?.isConnected) opener.focus({ preventScroll: true })
})
</script>
<template>
  <dialog
    ref="dialog"
    class="dialog backup-name-dialog"
    aria-labelledby="backup-name-title"
    @cancel.prevent="close"
    @click="backdrop"
  >
    <span class="dialog-icon"><Icon name="edit" :size="22" /></span>
    <h2 id="backup-name-title">{{ title }}</h2>
    <form class="backup-name-form" @submit.prevent="busy || emit('submit', name)">
      <label for="backup-name">名称（选填）</label>
      <input
        id="backup-name"
        ref="input"
        v-model="name"
        class="text-input"
        type="text"
        autocomplete="off"
        placeholder="例如：调整规则前"
        :maxlength="MAX_NAME"
        :disabled="busy"
        :aria-invalid="!!error"
        aria-describedby="backup-name-error"
      />
      <p id="backup-name-error" class="backup-name-error" role="alert">{{ error }}</p>
      <div class="dialog-actions">
        <button type="button" class="button" :disabled="busy" @click="close">取消</button>
        <button class="button primary" :disabled="busy">{{ busy ? busyAction : action }}</button>
      </div>
    </form>
  </dialog>
</template>
