<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'
import Icon from './Icon.vue'
defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const titleId = useId()
let opener: HTMLElement | null = null
let overflow = ''
onMounted(() => {
  opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  overflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  dialog.value?.showModal()
})
onBeforeUnmount(() => {
  dialog.value?.close()
  document.body.style.overflow = overflow
  if (opener?.isConnected) opener.focus({ preventScroll: true })
})
</script>
<template>
  <Teleport to="body">
    <dialog
      ref="dialog"
      class="result-dialog"
      :aria-labelledby="titleId"
      @cancel.prevent="emit('close')"
      @click.self="emit('close')"
    >
      <header>
        <h2 :id="titleId">{{ title }}</h2>
        <button type="button" class="icon-button" aria-label="关闭结果窗口" @click="emit('close')">
          <Icon name="close" :size="20" />
        </button>
      </header>
      <div class="result-dialog-body"><slot /></div>
      <footer>
        <slot name="footer" />
        <button type="button" class="button" @click="emit('close')">关闭</button>
      </footer>
    </dialog>
  </Teleport>
</template>
<style>
.result-dialog {
  zoom: var(--workspace-scale, 1);
  width: min(900px, calc(100vw / var(--workspace-scale, 1) - 48px));
  max-width: none;
  max-height: calc(85dvh / var(--workspace-scale, 1));
  padding: 0;
  margin: auto;
  border: 1px solid #e4e8ec;
  border-radius: 13px;
  color: var(--text);
  background: #fff;
  box-shadow: 0 18px 60px #20283226;
}
.result-dialog[open] {
  display: flex;
  flex-direction: column;
}
.result-dialog::backdrop {
  background: #27313d66;
}
.result-dialog > header,
.result-dialog > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  flex-shrink: 0;
}
.result-dialog > header {
  border-bottom: 1px solid #eceff2;
}
.result-dialog h2 {
  margin: 0;
  font-size: 17px;
}
.result-dialog-body {
  min-height: 0;
  padding: 20px 22px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.result-dialog > footer {
  border-top: 1px solid #eceff2;
  justify-content: flex-end;
}
.result-dialog > footer .pagination {
  flex: 1;
  min-width: 0;
  padding: 0;
  margin: 0;
  border: 0;
}
.result-dialog-body p,
.result-dialog-body li {
  overflow-wrap: anywhere;
}
@media (max-width: 760px) {
  .result-dialog {
    width: 100vw;
    height: 100dvh;
    max-height: 100dvh;
    border-radius: 0;
    border: 0;
  }
  .result-dialog > header,
  .result-dialog > footer {
    padding: 16px;
  }
  .result-dialog > footer {
    flex-wrap: wrap;
  }
  .result-dialog > footer .pagination {
    flex-basis: 100%;
  }
  .result-dialog-body {
    flex: 1;
    padding: 16px;
  }
}
</style>
