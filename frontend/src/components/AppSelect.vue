<script setup lang="ts" generic="T extends string | number">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { NPopover } from 'naive-ui'
import Icon from './Icon.vue'
import { usePopup } from '../usePopup'
defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    modelValue: T
    options: readonly { value: T; label: string; disabled?: boolean; group?: string }[]
    disabled?: boolean
    placeholder?: string
  }>(),
  { placeholder: '请选择' },
)
const emit = defineEmits<{ 'update:modelValue': [value: T]; change: [value: T] }>()
const { open, trigger, panel, close } = usePopup()
const popupTarget = ref<HTMLElement>()
let dialogLayer: HTMLElement | undefined
const id = useId(),
  active = ref(0),
  width = ref(0)
const selected = computed(() => props.options.find((item) => item.value === props.modelValue))
const observer = new ResizeObserver(() => {
  width.value = trigger.value?.offsetWidth || 0
})
let typed = '',
  typedAt = 0
function focusOption(index: number, step = 1) {
  const count = props.options.length
  if (!count) return
  for (let tries = 0; tries < count; tries++, index += step) {
    const next = ((index % count) + count) % count
    if (props.options[next]?.disabled) continue
    active.value = next
    const element = panel.value?.querySelectorAll<HTMLButtonElement>('[role="option"]')[next]
    element?.focus({ preventScroll: true })
    const menu = panel.value
    if (element && menu) {
      const top = element.offsetTop,
        bottom = top + element.offsetHeight
      if (top < menu.scrollTop) menu.scrollTop = top
      else if (bottom > menu.scrollTop + menu.clientHeight)
        menu.scrollTop = bottom - menu.clientHeight
    }
    return
  }
}
async function show(last = false) {
  if (props.disabled || !props.options.length) return
  // Native modal dialogs make body portals inert; keep the menu in the
  // trigger's dialog so pointer and keyboard interaction remain available.
  const dialog = trigger.value?.closest('dialog')
  if (dialog) {
    if (!dialogLayer || dialogLayer.parentElement !== dialog) {
      dialogLayer?.remove()
      dialogLayer = document.createElement('div')
      dialogLayer.className = 'app-select-dialog-layer'
      dialog.appendChild(dialogLayer)
    }
    popupTarget.value = dialogLayer
  } else popupTarget.value = undefined
  open.value = true
  await nextTick()
  const index = props.options.findIndex((item) => item.value === props.modelValue)
  focusOption(index >= 0 ? index : last ? props.options.length - 1 : 0, last ? -1 : 1)
}
function toggle() {
  if (open.value) close()
  else void show()
}
function choose(value: T) {
  if (value !== props.modelValue) {
    emit('update:modelValue', value)
    emit('change', value)
  }
  close(true)
}
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    event.stopPropagation()
    close(true)
  } else if (event.key === 'Tab' && open.value) {
    trigger.value?.focus({ preventScroll: true })
    close()
  } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    const backwards = event.key === 'ArrowUp' || event.key === 'End'
    if (!open.value) void show(backwards)
    else
      focusOption(
        event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? props.options.length - 1
            : active.value + (backwards ? -1 : 1),
        backwards ? -1 : 1,
      )
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && event.key !== ' ') {
    event.preventDefault()
    typed = Date.now() - typedAt > 700 ? event.key : typed + event.key
    typedAt = Date.now()
    const index = props.options.findIndex(
      (item) =>
        !item.disabled && item.label.toLocaleLowerCase().startsWith(typed.toLocaleLowerCase()),
    )
    if (index >= 0) {
      if (!open.value) {
        void show().then(() => focusOption(index))
      } else focusOption(index)
    }
  }
}
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) close()
  },
)
watch(
  () => JSON.stringify(props.options),
  () => {
    if (open.value) close()
  },
)
onMounted(() => {
  if (trigger.value) {
    width.value = trigger.value.offsetWidth
    observer.observe(trigger.value)
  }
})
onBeforeUnmount(() => {
  observer.disconnect()
  dialogLayer?.remove()
})
</script>
<template>
  <NPopover
    :show="open"
    :to="popupTarget"
    trigger="manual"
    placement="bottom-start"
    :width="Math.max(width, 160)"
    :show-arrow="false"
    :animated="false"
    class="app-select-popover"
    raw
  >
    <template #trigger>
      <button
        ref="trigger"
        v-bind="$attrs"
        type="button"
        class="app-select"
        role="combobox"
        aria-haspopup="listbox"
        :aria-expanded="open"
        :aria-controls="open ? id : undefined"
        :disabled="disabled"
        :data-value="String(modelValue)"
        :title="selected?.label || placeholder"
        @click="toggle"
        @keydown="keys"
      >
        <span class="app-select-label" :class="{ placeholder: !selected }">{{
          selected?.label || placeholder
        }}</span>
        <Icon name="down" :size="14" :class="{ expanded: open }" />
      </button>
    </template>
    <div
      :id="id"
      ref="panel"
      class="app-select-menu"
      role="listbox"
      :aria-label="($attrs['aria-label'] as string) || undefined"
      :aria-labelledby="($attrs['aria-labelledby'] as string) || undefined"
      @keydown="keys"
    >
      <template v-for="(option, index) in options" :key="option.value">
        <div
          v-if="option.group && option.group !== options[index - 1]?.group"
          class="app-select-group"
          role="presentation"
        >
          {{ option.group }}
        </div>
        <button
          type="button"
          role="option"
          tabindex="-1"
          :data-value="String(option.value)"
          :aria-selected="option.value === modelValue"
          :disabled="option.disabled"
          @focus="active = index"
          @click="choose(option.value)"
        >
          <span>{{ option.label }}</span
          ><Icon v-if="option.value === modelValue" name="check" :size="14" />
        </button>
      </template>
    </div>
  </NPopover>
</template>
<style>
.app-select {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 36px;
  min-width: 110px;
  padding: 8px 10px;
  border: 1px solid #e4e8ec;
  border-radius: 6px;
  background: #fff;
  color: #6c7886;
  font-size: 12px;
  text-align: left;
}
.app-select-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.app-select > svg,
.app-select-menu svg {
  flex-shrink: 0;
}
.app-select .placeholder {
  color: #6f7885;
}
.app-select:hover:not(:disabled) {
  border-color: #cba280;
}
.app-select:focus-visible,
.app-select[aria-expanded='true'] {
  border-color: #cba280;
  outline: 0;
  box-shadow: 0 0 0 3px #bf86521a;
}
.app-select:disabled {
  color: #6f7885;
  background: #f4f5f6;
  cursor: not-allowed;
}
.app-select-popover {
  zoom: var(--workspace-scale, 1);
}
/* Positioning uses viewport pixels. Cancel the dialog's inherited workspace
   zoom here, then apply the reading scale once on the popover above. */
.app-select-dialog-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  pointer-events: none;
  zoom: calc(1 / var(--workspace-scale, 1));
}
.app-select-menu {
  position: relative;
  padding: 4px;
  width: 100%;
  max-height: 260px;
  overflow-y: auto;
  max-width: calc(100vw / var(--workspace-scale, 1) - 16px);
  border: 1px solid #e9ebee;
  border-radius: 7px;
  background: #fff;
  box-shadow: 0 8px 28px #292e351a;
}
.app-select-group {
  padding: 8px 8px 4px;
  color: #8a93a0;
  font-size: 11px;
}
.app-select-group:not(:first-child) {
  margin-top: 4px;
  border-top: 1px solid #f0f1f3;
}
.app-select-menu > button {
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
.app-select-menu > button > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.app-select-menu > button:hover:not(:disabled),
.app-select-menu > button:focus-visible {
  background: #f7f1eb;
  outline: 0;
}
.app-select-menu > button[aria-selected='true'] {
  background: #f8ede5;
  color: var(--accent);
}
@media (max-width: 760px) {
  .app-select {
    min-height: 39px;
  }
  .app-select-menu > button {
    min-height: 44px;
    font-size: 16px;
  }
}
</style>
