<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
const props = defineProps<{ error: string; retryLabel?: string }>()
const emit = defineEmits<{ retry: [] }>()
const root = ref<HTMLElement>()
watch(
  () => props.error,
  async (error) => {
    if (!error) return
    await nextTick()
    const invalid = root.value
      ?.closest('.settings-card')
      ?.querySelector<HTMLElement>('[aria-invalid="true"]')
    const target = invalid || root.value
    target?.focus({ preventScroll: true })
    target?.scrollIntoView({ block: 'nearest' })
  },
  { flush: 'post', immediate: true },
)
</script>
<template>
  <div v-if="error" ref="root" class="form-errors settings-error" role="alert" tabindex="-1">
    <p>{{ error }}</p>
    <button class="button" type="button" @click="emit('retry')">
      {{ retryLabel || '重新加载' }}
    </button>
  </div>
</template>
