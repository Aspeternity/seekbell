<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import Icon from './Icon.vue'
import Toggle from './Toggle.vue'
import { moduleNames, type OverviewModule, type OverviewModuleId } from '../overviewPreferences'
const props = defineProps<{ modelValue: OverviewModule[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: OverviewModule[]] }>()
const list = ref<HTMLElement>()
const moving = ref<OverviewModuleId | null>(null)
const offset = ref(0)
const announcement = ref('')
const easing = 'cubic-bezier(0.2, 0.8, 0.2, 1)'
let grab = 0,
  pointerY = 0
const rows = () => [...(list.value?.querySelectorAll<HTMLElement>('[data-module]') ?? [])]
const row = (id: OverviewModuleId) =>
  list.value?.querySelector<HTMLElement>('[data-module="' + id + '"]')
const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches
// FLIP: rows slide from their old position; the dragged row follows the pointer instead.
function reorder(next: OverviewModule[], skip?: OverviewModuleId) {
  const before = new Map(rows().map((el) => [el, el.getBoundingClientRect().top]))
  emit('update:modelValue', next)
  nextTick(() => {
    if (moving.value) place(moving.value)
    if (still()) return
    for (const el of rows()) {
      const top = before.get(el)
      if (top === undefined || el.dataset.module === skip) continue
      const delta = top - el.getBoundingClientRect().top
      if (Math.abs(delta) < 1) continue
      el.getAnimations().forEach((animation) => animation.cancel())
      el.animate([{ transform: 'translateY(' + delta + 'px)' }, { transform: 'none' }], {
        duration: 220,
        easing,
      })
    }
  })
}
function move(id: OverviewModuleId, target: number, focus = false) {
  if (props.disabled) return
  const next = props.modelValue.map((item) => ({ ...item }))
  const index = next.findIndex((item) => item.id === id)
  if (index < 0 || target < 0 || target >= next.length || index === target) return
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item!)
  reorder(next, moving.value ?? undefined)
  announcement.value = moduleNames[id] + '已移到第' + (target + 1) + '位'
  if (focus)
    nextTick(() =>
      row(id)?.querySelector<HTMLButtonElement>('.module-handle')?.focus({ preventScroll: true }),
    )
}
function toggle(id: OverviewModuleId, value: boolean) {
  emit(
    'update:modelValue',
    props.modelValue.map((item) => (item.id === id ? { ...item, visible: value } : { ...item })),
  )
}
function place(id: OverviewModuleId) {
  const el = row(id)
  if (el && list.value)
    offset.value = pointerY - list.value.getBoundingClientRect().top - grab - el.offsetTop
}
function pointerStart(event: PointerEvent, id: OverviewModuleId) {
  if (props.disabled || event.button !== 0 || !list.value) return
  const el = row(id)
  if (!el) return
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).focus({ preventScroll: true })
  el.getAnimations().forEach((animation) => animation.cancel())
  grab = event.clientY - list.value.getBoundingClientRect().top - el.offsetTop
  pointerY = event.clientY
  offset.value = 0
  moving.value = id
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerEnd)
  window.addEventListener('pointercancel', pointerEnd)
  window.addEventListener('blur', pointerEnd)
}
function pointerMove(event: PointerEvent) {
  const id = moving.value
  if (!id || !list.value) return
  pointerY = event.clientY
  place(id)
  // The pointer takes the slot it is over; rows share one height, so a swap never flips back.
  const y = event.clientY - list.value.getBoundingClientRect().top
  const slots = rows()
  const found = slots.findIndex((el) => y < el.offsetTop + el.offsetHeight + 4)
  const target = found < 0 ? slots.length - 1 : found
  if (target !== props.modelValue.findIndex((item) => item.id === id)) move(id, target)
}
function pointerEnd() {
  const id = moving.value
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerEnd)
  window.removeEventListener('pointercancel', pointerEnd)
  window.removeEventListener('blur', pointerEnd)
  if (!id) return
  const el = row(id)
  if (el && offset.value && !still())
    el.animate([{ transform: 'translateY(' + offset.value + 'px)' }, { transform: 'none' }], {
      duration: 180,
      easing,
    })
  moving.value = null
  offset.value = 0
}
onBeforeUnmount(pointerEnd)
</script>
<template>
  <div ref="list" class="module-list" :class="{ sorting: !!moving }">
    <div
      v-for="(item, index) in modelValue"
      :key="item.id"
      class="module-row"
      :data-module="item.id"
      :class="{ dragging: moving === item.id, hidden: !item.visible }"
      :style="moving === item.id ? { transform: 'translateY(' + offset + 'px)' } : undefined"
    >
      <button
        type="button"
        class="module-handle"
        :disabled="disabled"
        :aria-label="'拖动排序' + moduleNames[item.id]"
        :aria-pressed="moving === item.id"
        @pointerdown="pointerStart($event, item.id)"
        @keydown.up.prevent="move(item.id, index - 1, true)"
        @keydown.down.prevent="move(item.id, index + 1, true)"
      >
        <svg width="12" height="18" viewBox="0 0 12 18" aria-hidden="true">
          <circle
            v-for="dot in 6"
            :key="dot"
            :cx="dot % 2 ? 3 : 9"
            :cy="Math.ceil(dot / 2) * 6 - 3"
            r="1.6"
          />
        </svg>
      </button>
      <span class="module-name">{{ moduleNames[item.id] }}</span>
      <Toggle
        :model-value="item.visible"
        :label="'显示' + moduleNames[item.id]"
        :disabled="disabled"
        @update:model-value="toggle(item.id, $event)"
      />
      <div class="module-order">
        <button
          type="button"
          class="icon-button"
          :disabled="disabled || index === 0"
          :aria-label="'上移' + moduleNames[item.id]"
          @click="move(item.id, index - 1)"
        >
          <Icon name="down" :size="16" class="module-up" />
        </button>
        <button
          type="button"
          class="icon-button"
          :disabled="disabled || index === modelValue.length - 1"
          :aria-label="'下移' + moduleNames[item.id]"
          @click="move(item.id, index + 1)"
        >
          <Icon name="down" :size="16" />
        </button>
      </div>
    </div>
    <span class="sr-only" role="status">{{ announcement }}</span>
  </div>
</template>
<style scoped>
.module-list {
  position: relative;
  display: grid;
  gap: 8px;
}
.module-list.sorting {
  cursor: grabbing;
  user-select: none;
}
.module-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 6px 10px 6px 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  transition:
    box-shadow 0.18s,
    border-color 0.18s,
    background-color 0.18s;
}
.module-row:hover {
  border-color: #dfe2e6;
}
.module-row.dragging {
  z-index: 2;
  border-color: #ecd3c2;
  box-shadow: 0 10px 28px rgba(41, 46, 53, 0.12);
}
.module-handle {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 36px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #a7aeb7;
  fill: currentColor;
  cursor: grab;
  touch-action: none;
  transition:
    color 0.15s,
    background-color 0.15s;
}
.module-handle:hover,
.module-row.dragging .module-handle {
  color: var(--accent);
  background: #fbf3ee;
}
.module-row.dragging .module-handle {
  cursor: grabbing;
}
.module-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #2f343b;
  transition: color 0.18s;
}
.module-row.hidden .module-name {
  color: #9aa3ae;
}
.module-order {
  display: flex;
  gap: 2px;
}
.module-up {
  transform: rotate(180deg);
}
@media (max-width: 420px) {
  .module-row {
    gap: 6px;
  }
  .module-order .icon-button {
    width: 36px;
  }
}
</style>
