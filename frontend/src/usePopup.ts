import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

// A trigger and its portalled panel form one interaction boundary.
export function usePopup() {
  const open = ref(false)
  const trigger = ref<HTMLButtonElement>()
  const panel = ref<HTMLElement>()
  function close(focus = false) {
    open.value = false
    if (focus) nextTick(() => trigger.value?.focus({ preventScroll: true }))
  }
  function outside(event: Event) {
    const target = event.target
    if (
      open.value &&
      target instanceof Node &&
      !trigger.value?.contains(target) &&
      !panel.value?.contains(target)
    )
      close()
  }
  onMounted(() => {
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('focusin', outside)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', outside, true)
    document.removeEventListener('focusin', outside)
  })
  return { open, trigger, panel, close }
}
