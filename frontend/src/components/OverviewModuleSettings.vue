<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import Icon from './Icon.vue'
import Toggle from './Toggle.vue'
import {
  defaultOverviewModules,
  moduleNames,
  type OverviewModule,
  type OverviewModuleId,
} from '../overviewPreferences'
const props = defineProps<{ modelValue: OverviewModule[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: OverviewModule[]] }>()
const root = ref<HTMLElement>()
const moving = ref<OverviewModuleId | null>(null)
const announcement = ref('')
function move(id: OverviewModuleId, target: number, focus = false) {
  if (props.disabled) return
  const rows = props.modelValue.map((row) => ({ ...row }))
  const index = rows.findIndex((row) => row.id === id)
  if (index < 0 || target < 0 || target >= rows.length || index === target) return
  const [item] = rows.splice(index, 1)
  rows.splice(target, 0, item!)
  emit('update:modelValue', rows)
  announcement.value = moduleNames[id] + '已移到第' + (target + 1) + '位'
  if (focus)
    nextTick(() =>
      root.value
        ?.querySelector<HTMLButtonElement>('[data-module="' + id + '"] .module-handle')
        ?.focus({ preventScroll: true }),
    )
}
function toggle(id: OverviewModuleId, value: boolean) {
  emit(
    'update:modelValue',
    props.modelValue.map((row) => (row.id === id ? { ...row, visible: value } : { ...row })),
  )
}
function pointerStart(event: PointerEvent, id: OverviewModuleId) {
  if (props.disabled || event.button !== 0) return
  moving.value = id
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).focus({ preventScroll: true })
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerEnd)
  window.addEventListener('pointercancel', pointerEnd)
  window.addEventListener('blur', pointerEnd)
}
function pointerEnd() {
  moving.value = null
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerEnd)
  window.removeEventListener('pointercancel', pointerEnd)
  window.removeEventListener('blur', pointerEnd)
}
onBeforeUnmount(pointerEnd)
function pointerMove(event: PointerEvent) {
  if (!moving.value) return
  const row = document
    .elementFromPoint(event.clientX, event.clientY)
    ?.closest<HTMLElement>('[data-module]')
  if (!row || !root.value?.contains(row)) return
  const target = props.modelValue.findIndex((item) => item.id === row.dataset.module)
  move(moving.value, target)
}
</script>
<template>
  <section
    id="overview-modules"
    ref="root"
    class="overview-module-settings"
    aria-label="概览显示模块"
  >
    <div class="module-settings-heading">
      <h3>概览显示模块</h3>
      <button
        type="button"
        class="text-link"
        :disabled="disabled"
        @click="emit('update:modelValue', defaultOverviewModules())"
      >
        恢复默认布局
      </button>
    </div>
    <p class="small-note">拖动手柄或使用上下按钮排序。隐藏模块不会暂停监控或删除记录。</p>
    <div
      v-for="(item, index) in modelValue"
      :key="item.id"
      class="module-setting-row"
      :data-module="item.id"
      :class="{ moving: moving === item.id }"
    >
      <button
        type="button"
        class="icon-button module-handle"
        :disabled="disabled"
        :aria-label="'拖动排序' + moduleNames[item.id]"
        :aria-pressed="moving === item.id"
        @pointerdown="pointerStart($event, item.id)"
        @keydown.up.prevent="move(item.id, index - 1, true)"
        @keydown.down.prevent="move(item.id, index + 1, true)"
      >
        <span aria-hidden="true">⠿</span>
      </button>
      <span class="module-setting-name">{{ moduleNames[item.id] }}</span>
      <Toggle
        :model-value="item.visible"
        :label="'显示' + moduleNames[item.id]"
        :disabled="disabled"
        @update:model-value="toggle(item.id, $event)"
      />
      <div class="module-order-buttons">
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
          <Icon name="down" :size="16" class="module-down" />
        </button>
      </div>
    </div>
    <span class="sr-only" role="status">{{ announcement }}</span>
  </section>
</template>
<style scoped>
.module-settings-heading,
.module-setting-row,
.module-order-buttons {
  display: flex;
  align-items: center;
  gap: 12px;
}
.module-settings-heading {
  justify-content: space-between;
  flex-wrap: wrap;
}
.module-setting-row {
  padding: 14px 0;
  border-bottom: 1px solid var(--border, #e9ebee);
  flex-wrap: wrap;
}
.module-setting-name {
  flex: 1;
  min-width: 72px;
}
.module-handle {
  touch-action: none;
  cursor: grab;
  font-size: 22px;
}
.module-setting-row.moving .module-handle {
  cursor: grabbing;
}
.module-setting-row.moving {
  background: #fdf7f2;
}
.module-order-buttons {
  gap: 4px;
}
.module-up {
  transform: rotate(180deg);
}
@media (max-width: 420px) {
  .module-setting-row {
    gap: 6px;
  }
  .module-order-buttons .icon-button {
    width: 36px;
  }
}
</style>
