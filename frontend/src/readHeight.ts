import { ref, watch } from 'vue'
import type { Ref } from 'vue'

// Keep the old space, not another query's rows, while a new query is pending.
export function useReadHeight(loading: Ref<boolean>) {
  const element = ref<HTMLElement>()
  const height = ref(0)
  watch(
    loading,
    (pending) => {
      if (pending) {
        const scale =
          parseFloat(
            getComputedStyle(document.documentElement).getPropertyValue('--workspace-scale'),
          ) || 1
        height.value = (element.value?.getBoundingClientRect().height || 0) / scale
      }
    },
    { flush: 'sync' },
  )
  return {
    element,
    style: () => (loading.value && height.value ? { minHeight: height.value + 'px' } : undefined),
  }
}
