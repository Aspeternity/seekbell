<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NPopover } from 'naive-ui'
import Icon from './Icon.vue'

const props = defineProps<{
  modelValue: string
  disabled?: boolean
  options: { value: string; label: string }[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const open = ref(false)
const root = ref<HTMLElement>()
const trigger = ref<HTMLButtonElement>()
const menu = ref<HTMLElement>()
const menuWidth = ref(0)
const activeIndex = ref(0)
const selected = computed(() => props.options.find((option) => option.value === props.modelValue))
const observer = new ResizeObserver(([entry]) => {
  if (entry) menuWidth.value = entry.contentRect.width
})
function close(focus = false) {
  open.value = false
  if (focus) nextTick(() => trigger.value?.focus())
}
function focusOption(index: number) {
  if (!props.options.length) return
  activeIndex.value = (index + props.options.length) % props.options.length
  const option =
    menu.value?.querySelectorAll<HTMLButtonElement>('[role="option"]')[activeIndex.value]
  option?.focus()
  option?.scrollIntoView({ block: 'nearest' })
}
async function openMenu(last = false) {
  if (props.disabled || !props.options.length) return
  open.value = true
  await nextTick()
  const index = props.options.findIndex((option) => option.value === props.modelValue)
  focusOption(index >= 0 ? index : last ? props.options.length - 1 : 0)
}
function toggle() {
  if (open.value) close()
  else void openMenu()
}
function choose(value: string) {
  if (value !== props.modelValue) emit('update:modelValue', value)
  close(true)
}
function triggerKey(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (open.value) focusOption(activeIndex.value + (event.key === 'ArrowUp' ? -1 : 1))
    else void openMenu(event.key === 'ArrowUp')
  } else if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    event.stopPropagation()
    close(true)
  }
}
function menuKey(event: KeyboardEvent) {
  if (event.key === 'Tab') {
    // Resume native form navigation from the trigger, not the portalled menu.
    trigger.value?.focus()
    close()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close(true)
  } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    focusOption(
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? props.options.length - 1
          : activeIndex.value + (event.key === 'ArrowUp' ? -1 : 1),
    )
  }
}
function outside(event: Event) {
  const target = event.target as Node
  if (open.value && !root.value?.contains(target) && !menu.value?.contains(target)) close()
}
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) close()
  },
)
onMounted(() => {
  if (root.value) {
    menuWidth.value = root.value.clientWidth
    observer.observe(root.value)
  }
  document.addEventListener('pointerdown', outside)
  document.addEventListener('focusin', outside)
})
onBeforeUnmount(() => {
  observer.disconnect()
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('focusin', outside)
})
</script>

<template>
  <div ref="root" class="task-website-picker">
    <NPopover
      :show="open"
      class="task-website-popover"
      trigger="manual"
      placement="bottom-start"
      :show-arrow="false"
      :width="menuWidth"
      raw
    >
      <template #trigger>
        <button
          id="task-website"
          ref="trigger"
          type="button"
          class="task-website-trigger"
          role="combobox"
          aria-labelledby="task-website-label"
          aria-haspopup="listbox"
          :aria-expanded="open"
          :aria-controls="open ? 'task-website-options' : undefined"
          :disabled="disabled"
          @click="toggle"
          @keydown="triggerKey"
        >
          <span :class="{ placeholder: !selected }">{{ selected?.label || '请选择监控网站' }}</span>
          <Icon name="down" :size="16" :class="{ expanded: open }" />
        </button>
      </template>
      <div
        id="task-website-options"
        ref="menu"
        class="task-website-menu"
        role="listbox"
        aria-labelledby="task-website-label"
        @keydown="menuKey"
      >
        <button
          v-for="(option, index) in options"
          :key="option.value"
          type="button"
          role="option"
          tabindex="-1"
          :aria-selected="option.value === modelValue"
          :class="{ 'is-selected': option.value === modelValue }"
          @focus="activeIndex = index"
          @click="choose(option.value)"
        >
          <span>{{ option.label }}</span>
          <Icon v-if="option.value === modelValue" name="check" :size="16" />
        </button>
      </div>
    </NPopover>
  </div>
</template>

<style scoped>
.task-website-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  height: 39px;
  padding: 0 11px;
  border: 1px solid #e1e5ea;
  border-radius: 6px;
  background: #fff;
  color: #4d5762;
  font: inherit;
  font-size: 12px;
  text-align: left;
}
.task-website-trigger > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-website-trigger > svg {
  flex-shrink: 0;
  color: #6f7885;
  transition: transform 0.15s;
}
.task-website-trigger .expanded {
  transform: rotate(180deg);
}
.task-website-trigger .placeholder {
  color: #6f7885;
}
.task-website-trigger:hover:not(:disabled) {
  border-color: #cba280;
}
.task-website-trigger:focus-visible,
.task-website-trigger[aria-expanded='true'] {
  border-color: #cba280;
  outline: 0;
  box-shadow: 0 0 0 3px #bf86521a;
}
.task-website-trigger:disabled {
  color: #6f7885;
  background: #f4f5f6;
  cursor: not-allowed;
}
.task-website-menu {
  padding: 4px;
  width: 100%;
  max-height: 224px;
  overflow-y: auto;
  border: 1px solid #e9ebee;
  border-radius: 7px;
  background: #fff;
  box-shadow: 0 8px 28px #292e351a;
}
.task-website-menu > button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-height: 34px;
  padding: 7px 8px;
  border: 0;
  border-radius: 5px;
  color: #4d5762;
  background: none;
  font: inherit;
  font-size: 12px;
  text-align: left;
}
.task-website-menu > button > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.task-website-menu > button > svg {
  flex-shrink: 0;
}
.task-website-menu > button:hover,
.task-website-menu > button:focus {
  background: #fdf7f2;
  outline: 0;
}
.task-website-menu > button.is-selected {
  color: #b75e32;
  background: #f9ebe2;
}
@media (max-width: 760px) {
  .task-website-trigger {
    height: 44px;
    font-size: 16px;
  }
  .task-website-menu > button {
    min-height: 44px;
    font-size: 16px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .task-website-trigger > svg {
    transition: none;
  }
}
</style>

<style>
.task-website-popover {
  zoom: var(--workspace-scale, 1);
}
</style>
