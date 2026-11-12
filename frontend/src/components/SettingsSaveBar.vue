<script setup lang="ts">
// The shared footer of an editable settings form; it sits inside the form it submits.
defineProps<{ dirty: boolean; busy: boolean; done: boolean; label: string; doneText: string }>()
const emit = defineEmits<{ discard: [] }>()
</script>
<template>
  <div class="inline-form-footer settings-savebar">
    <span role="status">{{ done ? doneText : dirty ? '有未保存的修改' : '' }}</span>
    <div class="inline-actions">
      <button class="button" type="button" :disabled="busy || !dirty" @click="emit('discard')">
        放弃修改
      </button>
      <button class="button primary" type="submit" :disabled="busy || !dirty">
        {{ busy ? '保存中…' : label }}
      </button>
    </div>
  </div>
</template>
