<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { NPopover } from 'naive-ui'
import Icon from './Icon.vue'
import { usePopup } from '../usePopup'
const props = defineProps<{
  modelValue: string
  label: string
  options: { value: string; label: string; status: string }[]
  loading: boolean
  error: string
  page: number
  total: number
}>()
const emit = defineEmits<{
  choose: [value: string]
  search: [value: string]
  page: [value: number]
  retry: []
}>()
const { open, trigger, panel, close } = usePopup()
const search = ref<HTMLInputElement>(),
  query = ref(''),
  width = ref(0)
const id = useId()
const observer = new ResizeObserver(() => (width.value = trigger.value?.offsetWidth || 0))
async function show() {
  if (open.value) return close()
  open.value = true
  await nextTick()
  search.value?.focus({ preventScroll: true })
}
function choose(value: string) {
  emit('choose', value)
  close(true)
}
function move(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close(true)
    return
  }
  if (event.key === 'Tab') {
    trigger.value?.focus({ preventScroll: true })
    close()
    return
  }
  if (props.loading || props.error || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key))
    return
  if (event.target === search.value && !['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  const options = [...(panel.value?.querySelectorAll<HTMLButtonElement>('[role="option"]') || [])]
  if (!options.length) return
  const current = options.indexOf(document.activeElement as HTMLButtonElement)
  const index =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? options.length - 1
        : (current + (event.key === 'ArrowUp' ? -1 : 1) + options.length) % options.length
  options[index]?.focus({ preventScroll: true })
  const item = options[index],
    menu = item?.parentElement
  if (item && menu) {
    if (item.offsetTop < menu.scrollTop) menu.scrollTop = item.offsetTop
    else if (item.offsetTop + item.offsetHeight > menu.scrollTop + menu.clientHeight)
      menu.scrollTop = item.offsetTop + item.offsetHeight - menu.clientHeight
  }
}
onMounted(() => {
  if (trigger.value) {
    width.value = trigger.value.offsetWidth
    observer.observe(trigger.value)
  }
})
onBeforeUnmount(() => observer.disconnect())
</script>
<template>
  <NPopover
    :show="open"
    trigger="manual"
    placement="bottom-start"
    :width="Math.max(width, 240)"
    :show-arrow="false"
    :animated="false"
    class="app-select-popover"
    raw
  >
    <template #trigger>
      <button
        ref="trigger"
        type="button"
        role="combobox"
        class="app-select task-picker"
        aria-label="查看任务判定"
        aria-haspopup="listbox"
        :aria-controls="open ? id : undefined"
        :aria-expanded="open"
        @click="show"
        @keydown.down.prevent="show"
        @keydown.up.prevent="show"
      >
        <span class="app-select-label">{{ label || '选择任务' }}</span
        ><Icon name="down" :size="14" />
      </button>
    </template>
    <div ref="panel" class="task-picker-panel" @keydown="move">
      <input
        ref="search"
        v-model="query"
        class="text-input"
        aria-label="搜索判定任务"
        placeholder="搜索任务名称"
        @input="emit('search', query)"
      />
      <p v-if="loading" role="status" class="small-note">正在读取任务…</p>
      <div v-else-if="error" class="inline-error" role="alert">
        {{ error }} <button type="button" class="text-link" @click="emit('retry')">重试</button>
      </div>
      <div v-else :id="id" role="listbox" aria-label="历史判定任务" class="task-picker-options">
        <button
          v-for="option in options"
          :key="option.value"
          type="button"
          role="option"
          tabindex="-1"
          :aria-selected="option.value === modelValue"
          @click="choose(option.value)"
        >
          <span>{{ option.label }}</span
          ><small>{{ option.status }}</small>
        </button>
        <p v-if="!options.length" class="small-note" role="status">没有找到对应任务。</p>
      </div>
      <div v-if="total > 20" class="task-picker-pages">
        <button
          type="button"
          class="text-link"
          :disabled="page <= 1 || loading"
          @click="emit('page', page - 1)"
        >
          上一页
        </button>
        <span>{{ page }} / {{ Math.ceil(total / 20) }}</span>
        <button
          type="button"
          class="text-link"
          :disabled="page * 20 >= total || loading"
          @click="emit('page', page + 1)"
        >
          下一页
        </button>
      </div>
    </div>
  </NPopover>
</template>
<style scoped>
.task-picker {
  width: 100%;
  min-width: 0;
  font-size: 12px;
}
.task-picker-panel {
  padding: 10px;
  border: 1px solid #e4e8ec;
  border-radius: 7px;
  background: #fff;
  box-shadow: 0 8px 28px #292e351a;
}
.task-picker-panel > input {
  width: 100%;
  margin-bottom: 8px;
}
.task-picker-options {
  position: relative;
  max-height: 220px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.task-picker-options > button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding: 8px;
  text-align: left;
  font-size: 12px;
  color: #4d5762;
  border: 0;
  border-radius: 5px;
  background: none;
}
.task-picker-options > button > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.task-picker-options small {
  flex-shrink: 0;
  color: #737e8c;
  font-size: 10px;
}
.task-picker-options > button:focus-visible,
.task-picker-options > button:hover {
  background: #f7f1eb;
  outline: none;
}
.task-picker-options > button[aria-selected='true'] {
  background: #f8ede5;
  color: var(--accent);
}
.task-picker-pages {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 10px;
  font-size: 11px;
  border-top: 1px solid #eceff2;
}
@media (max-width: 760px) {
  .task-picker-options > button {
    min-height: 44px;
  }
  .task-picker-panel > input {
    font-size: 16px;
  }
}
</style>
