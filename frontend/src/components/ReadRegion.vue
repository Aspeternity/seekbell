<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
const placeholderVisible = ref(false)
let placeholderTimer: ReturnType<typeof setTimeout> | undefined
import Feedback from './Feedback.vue'
const props = withDefaults(
  defineProps<{
    loading: boolean
    error: string
    hasData: boolean
    stale?: boolean
    minHeight?: number
    allowControls?: boolean
  }>(),
  { stale: false, minHeight: 220 },
)
watch(
  () => !props.hasData && props.loading,
  (waiting) => {
    clearTimeout(placeholderTimer)
    placeholderVisible.value = false
    if (waiting) placeholderTimer = setTimeout(() => (placeholderVisible.value = true), 200)
  },
  { immediate: true },
)
const emit = defineEmits<{ retry: [] }>()
const content = ref<HTMLElement>(),
  height = ref(0)
const observer = new ResizeObserver(() => {
  if (!props.loading && content.value) height.value = content.value.offsetHeight
})
watch(content, (element, previous) => {
  if (previous) observer.unobserve(previous)
  if (element) observer.observe(element)
})
onMounted(() => {
  if (content.value) observer.observe(content.value)
})
function guard(event: Event) {
  if (!props.stale || !props.allowControls) return
  const target = event.target
  if (target instanceof Element && target.closest('[data-read-control]')) return
  event.preventDefault()
  event.stopPropagation()
}
function guardKey(event: KeyboardEvent) {
  if (
    event.key === 'Tab' ||
    event.key === 'Escape' ||
    ((event.ctrlKey || event.metaKey) && ['c', 'a'].includes(event.key.toLowerCase()))
  )
    return
  guard(event)
}
onBeforeUnmount(() => {
  observer.disconnect()
  clearTimeout(placeholderTimer)
})
</script>
<template>
  <div
    class="read-region"
    :aria-busy="loading"
    :style="{ minHeight: !hasData ? Math.max(height, minHeight) + 'px' : undefined }"
  >
    <div class="read-region-feedback">
      <Feedback
        :loading="loading"
        :error="error"
        :retained="hasData"
        :delay="200"
        subtle
        :message="stale ? '正在更新，当前显示上次结果…' : ''"
        @retry="emit('retry')"
      />
    </div>
    <div v-if="!hasData && placeholderVisible" class="read-placeholder" aria-hidden="true">
      <span /><span /><span />
    </div>
    <div
      v-if="hasData"
      ref="content"
      class="read-snapshot"
      :inert="stale && !allowControls"
      @click.capture="guard"
      @keydown.capture="guardKey"
      :aria-label="stale ? '更新中，当前显示上次结果' : undefined"
    >
      <slot />
    </div>
  </div>
</template>
<style>
.read-region {
  position: relative;
}
.read-region-feedback {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 2;
  max-width: calc(100% - 24px);
  pointer-events: none;
}
.read-region-feedback > * {
  pointer-events: auto;
}
.read-region-feedback .remote-feedback {
  margin: 0;
  padding: 4px 8px;
  border-radius: 4px;
  background: #fff;
}
.read-region-feedback .form-errors {
  margin: 0;
  background: #fff8f5;
}
.read-placeholder {
  padding: 26px 22px;
}
.read-placeholder span {
  display: block;
  height: 12px;
  background: #f2f4f6;
  border-radius: 4px;
  margin-bottom: 20px;
}
.read-placeholder span:nth-child(1) {
  width: 48%;
}
.read-placeholder span:nth-child(2) {
  width: 84%;
}
.read-placeholder span:nth-child(3) {
  width: 66%;
}
</style>
