<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { NPopover } from 'naive-ui'
import Icon from './Icon.vue'
import type { HistoryDateRange } from '../dateRange'
import { usePopup } from '../usePopup'
const props = defineProps<{ modelValue: HistoryDateRange; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: HistoryDateRange] }>()
const { open, trigger, panel: menu, close } = usePopup()
const start = ref(''),
  end = ref(''),
  error = ref('')
const first = ref<HTMLInputElement>()
const id = useId()
const caption = computed(() => {
  const range = props.modelValue
  if (!range) return '全部日期'
  const from = range[0].replaceAll('-', '/'),
    to = range[1].replaceAll('-', '/')
  return from === to ? from : from + ' – ' + to
})
async function toggle() {
  if (open.value) return close()
  start.value = props.modelValue?.[0] || ''
  end.value = props.modelValue?.[1] || ''
  error.value = ''
  open.value = true
  await nextTick()
  first.value?.focus({ preventScroll: true })
}
function apply(event: Event) {
  if (!start.value || !end.value) {
    error.value = '请选择开始日期和结束日期。'
    return
  }
  if (!(event.currentTarget as HTMLFormElement).checkValidity()) {
    error.value = '请输入有效的开始日期和结束日期。'
    return
  }
  if (start.value > end.value) {
    error.value = '开始日期不能晚于结束日期。'
    return
  }
  emit('update:modelValue', [start.value, end.value])
  close(true)
}
function clear() {
  emit('update:modelValue', null)
  close(true)
}
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close(true)
  } else if (
    event.key === 'Tab' &&
    !event.shiftKey &&
    event.target === menu.value?.querySelector('[type="submit"]')
  ) {
    // Continue document tab order from the trigger after the portalled form.
    trigger.value?.focus({ preventScroll: true })
    close()
  }
}
watch(
  () => props.modelValue,
  () => close(),
)
</script>
<template>
  <div class="history-date-filter">
    <NPopover
      :show="open"
      trigger="manual"
      placement="bottom-start"
      :show-arrow="false"
      :animated="false"
      class="history-date-popover"
      raw
    >
      <template #trigger>
        <button
          ref="trigger"
          type="button"
          class="history-date-trigger"
          :aria-label="label"
          :aria-describedby="id + '-value'"
          aria-haspopup="dialog"
          :aria-expanded="open"
          :aria-controls="open ? id : undefined"
          :title="label + '：' + caption"
          @click="toggle"
          @keydown.esc.prevent.stop="close(true)"
        >
          <span>{{ caption }}</span
          ><Icon name="down" :size="14" />
        </button>
      </template>
      <form
        :id="id"
        ref="menu"
        role="dialog"
        :aria-label="label + '范围'"
        class="history-date-menu"
        novalidate
        @submit.prevent="apply"
        @keydown="keys"
      >
        <strong>{{ label }}</strong>
        <label
          >开始日期<input
            ref="first"
            v-model="start"
            type="date"
            min="0001-01-01"
            max="9999-12-30"
            required
        /></label>
        <label
          >结束日期<input v-model="end" type="date" min="0001-01-01" max="9999-12-30" required
        /></label>
        <p v-if="error" role="alert" class="date-error">{{ error }}</p>
        <div class="date-actions">
          <button type="button" class="text-link" @click="clear">清除</button>
          <button type="button" class="button" @click="close(true)">取消</button>
          <button type="submit" class="button primary">应用</button>
        </div>
      </form>
    </NPopover>
  </div>
</template>
<style scoped>
.history-date-filter {
  width: 196px;
  max-width: 100%;
}
.history-date-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  min-height: 36px;
  padding: 8px 10px;
  border: 1px solid #e4e8ec;
  border-radius: 6px;
  background: white;
  color: #6c7886;
  font-size: 11px;
  white-space: nowrap;
}
.history-date-trigger svg {
  flex-shrink: 0;
}
.history-date-trigger:focus {
  border-color: #cba280;
  box-shadow: 0 0 0 3px #bf86521a;
}
.history-date-menu {
  width: 254px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: white;
  box-shadow: 0 8px 24px #292e3514;
  font-size: 12px;
  color: #6c7886;
}
.history-date-menu strong {
  color: #292e35;
}
.history-date-menu label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}
.history-date-menu input {
  width: 100%;
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid #e4e8ec;
  border-radius: 6px;
  background: white;
}
.history-date-menu input:focus {
  border-color: #cba280;
  box-shadow: 0 0 0 3px #bf86521a;
}
.date-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}
.date-actions .text-link {
  margin-right: auto;
}
.date-error {
  margin: 10px 0 0;
  color: #b64040;
}
@media (max-width: 760px) {
  .history-date-filter {
    flex: 1;
    min-width: min(196px, 100%);
  }
  .history-date-trigger {
    font-size: 12px;
    min-height: 39px;
  }
  .history-date-menu input {
    font-size: 16px;
    min-height: 40px;
  }
}
</style>
<style>
.history-date-popover {
  zoom: var(--workspace-scale, 1);
}
</style>
