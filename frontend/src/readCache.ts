import { ref } from 'vue'

// Session memory only. A bounded LRU keeps filters from accumulating full pages.
const entries = new Map<string, unknown>()
const capacity = 20
export const readCacheRevision = ref(0)
export function clearReadCache() {
  entries.clear()
  readCacheRevision.value++
}
export function cachedRead<T>(key: string): T | undefined {
  if (!entries.has(key)) return
  const value = entries.get(key)
  entries.delete(key)
  entries.set(key, value)
  return value as T
}
export function rememberRead(key: string, value: unknown, revision: number) {
  if (revision !== readCacheRevision.value || value === undefined) return
  entries.delete(key)
  entries.set(key, value)
  if (entries.size > capacity) entries.delete(entries.keys().next().value!)
}
