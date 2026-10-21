<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NSelect } from 'naive-ui'
import type { SelectProps } from 'naive-ui'

const props = defineProps<{
  modelValue: string
  disabled?: boolean
  options: { value: string; label: string }[]
}>()
const open = ref(false)
const control = ref<HTMLElement>()
const menuWidth = ref(0)
// Follower measurements include CSS zoom; menu CSS needs the unscaled width.
const observer = new ResizeObserver(([entry]) => {
  if (entry) menuWidth.value = entry.contentRect.width
})
onMounted(() => {
  if (control.value) {
    menuWidth.value = control.value.clientWidth
    observer.observe(control.value)
  }
})
onBeforeUnmount(() => observer.disconnect())
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const theme: SelectProps['themeOverrides'] = {
  menuBoxShadow: '0 8px 28px rgba(41, 46, 53, .10)',
  peers: {
    InternalSelection: {
      fontSizeMedium: 'var(--website-picker-font)',
      heightMedium: 'var(--website-picker-height)',
      borderRadius: '6px',
      textColor: '#4d5762',
      textColorDisabled: '#6f7885',
      color: '#fff',
      colorActive: '#fff',
      colorDisabled: '#f4f5f6',
      border: '1px solid #e1e5ea',
      borderHover: '1px solid #cba280',
      borderActive: '1px solid #cba280',
      borderFocus: '1px solid #cba280',
      boxShadowActive: '0 0 0 3px #bf86521a',
      boxShadowFocus: '0 0 0 3px #bf86521a',
      caretColor: '#b75e32',
      arrowColor: '#6f7885',
      paddingSingle: '0 11px',
    },
    InternalSelectMenu: {
      borderRadius: '7px',
      color: '#fff',
      optionFontSizeMedium: 'var(--website-picker-font)',
      optionTextColor: '#4d5762',
      optionTextColorActive: '#b75e32',
      optionTextColorPressed: '#b75e32',
      optionCheckColor: '#b75e32',
      optionColorPending: '#fdf7f2',
      optionColorActive: '#f9ebe2',
      optionColorActivePending: '#f9ebe2',
      height: '224px',
      paddingMedium: '4px',
    },
  },
}
const selection = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})
</script>

<template>
  <div ref="control" class="task-website-picker">
    <NSelect
      v-model:value="selection"
      v-model:show="open"
      filterable
      :options="options"
      :disabled="disabled"
      :to="false"
      :consistent-menu-width="false"
      :theme-overrides="theme"
      :input-props="{
        id: 'task-website',
        role: 'combobox',
        'aria-label': '监控网站',
        'aria-expanded': open,
        'aria-autocomplete': 'list',
        'aria-controls': open ? 'task-website-options' : undefined,
      }"
      :menu-props="{
        id: 'task-website-options',
        role: 'listbox',
        'aria-label': '已添加的网站',
        class: 'task-website-menu',
        style: { border: '1px solid #e9ebee', width: menuWidth + 'px' },
      }"
      :node-props="(option) => ({ role: 'option', 'aria-selected': option.value === selection })"
      placeholder="请选择监控网站"
    />
  </div>
</template>

<style scoped>
.task-website-picker {
  --website-picker-font: 12px;
  --website-picker-height: 39px;
}
@media (max-width: 760px) {
  .task-website-picker {
    --website-picker-font: 16px;
    --website-picker-height: 44px;
  }
}
</style>
