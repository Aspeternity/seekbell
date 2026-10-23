import { ref, shallowRef } from 'vue'

export interface NotificationCounts {
  deliveries: number
  manual: number
  tests: number
}
export const notificationCounts = shallowRef<NotificationCounts>()
export const countsLoading = ref(false)
export const countsError = ref('')
export const countsRevision = ref(0)
let inFlight: { revision: number; promise: Promise<void> } | undefined

export function invalidateNotificationCounts() {
  countsRevision.value++
}
export function clearNotificationCounts() {
  notificationCounts.value = undefined
  countsLoading.value = false
  countsError.value = ''
  inFlight = undefined
  invalidateNotificationCounts()
}
export function loadNotificationCounts(loader: () => Promise<NotificationCounts>) {
  const revision = countsRevision.value
  if (inFlight?.revision === revision) return inFlight.promise
  countsLoading.value = true
  countsError.value = ''
  const promise = loader()
    .then((value) => {
      if (revision === countsRevision.value) notificationCounts.value = value
    })
    .catch((error) => {
      if (revision === countsRevision.value)
        countsError.value = error instanceof Error ? error.message : '通知数量读取失败，请重试。'
    })
    .finally(() => {
      if (revision === countsRevision.value) {
        countsLoading.value = false
        inFlight = undefined
      }
    })
  inFlight = { revision, promise }
  return promise
}
