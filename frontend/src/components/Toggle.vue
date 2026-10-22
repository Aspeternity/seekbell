<script setup lang="ts">
defineProps<{ modelValue: boolean; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
<template>
  <button
    class="toggle"
    type="button"
    role="switch"
    :aria-label="label"
    :aria-checked="modelValue"
    :class="{ on: modelValue }"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span />
  </button>
</template>
