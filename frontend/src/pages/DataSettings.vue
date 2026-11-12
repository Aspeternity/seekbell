<script setup lang="ts">
import { nextTick, onMounted } from 'vue'
import { scrollToSection } from '../settings'
import RetentionSettings from './RetentionSettings.vue'
const emit = defineEmits<{ dirty: [value: boolean] }>()
onMounted(async () => {
  await nextTick()
  scrollToSection('retention', 'retention-settings')
})
</script>
<template>
  <div class="settings-stack">
    <RetentionSettings @dirty="emit('dirty', $event)" />
  </div>
</template>
