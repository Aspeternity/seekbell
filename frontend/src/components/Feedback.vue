<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
const props = withDefaults(
  defineProps<{
    loading: boolean
    error: string
    delay?: number
    retained?: boolean
    subtle?: boolean
    message?: string
  }>(),
  { delay: 0, retained: false, subtle: false, message: '' },
)
const emit = defineEmits<{ retry: [] }>()
const visible = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
watch(
  () => props.loading,
  (loading) => {
    clearTimeout(timer)
    visible.value = loading && !props.delay
    if (loading && props.delay) timer = setTimeout(() => (visible.value = true), props.delay)
  },
  { immediate: true },
)
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <p v-if="visible" :class="subtle ? 'small-note remote-feedback' : 'info-note'" role="status">
    {{ message || (retained ? '正在更新…' : subtle ? '加载中…' : '正在读取服务端记录…') }}
  </p>
  <div v-else-if="error" class="form-errors" role="alert">
    <p v-if="retained">刷新失败，当前显示上次结果。</p>
    <p>{{ error }}</p>
    <button class="button" @click="emit('retry')">重新加载</button>
  </div>
</template>
