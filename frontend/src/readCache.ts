import { ref } from 'vue'

// Bounded snapshots belong to one authenticated browser session.
const entries = new Map<string, { value: unknown; revision: number }>()
const pending = new Map<string, Promise<unknown>>()
const capacity = 20
export const readCacheRevision = ref(0)
export const readSessionRevision = ref(0)
export function clearReadCache() {
  entries.clear()
  pending.clear()
  readSessionRevision.value++
  readCacheRevision.value++
}
export function invalidateReadCache() {
  // Successful writes make snapshots old, not another identity's data.
  readCacheRevision.value++
}
export function cachedRead<T>(key: string): T | undefined {
  const entry = entries.get(key)
  if (!entry) return
  entries.delete(key)
  entries.set(key, entry)
  return entry.value as T
}
export function readIsFresh(key: string) {
  return entries.get(key)?.revision === readCacheRevision.value
}
export function rememberRead(key: string, value: unknown, revision: number) {
  if (revision !== readCacheRevision.value || value === undefined) return
  entries.delete(key)
  entries.set(key, { value, revision })
  if (entries.size > capacity) entries.delete(entries.keys().next().value!)
}

// Preloads and mounted readers share a request only within the same data/session revision.
export function fetchRead<T>(key: string | undefined, loader: () => Promise<T>): Promise<T> {
  if (!key) return loader()
  const revision = readCacheRevision.value,
    session = readSessionRevision.value
  const identity = JSON.stringify([session, revision, key])
  const existing = pending.get(identity)
  if (existing) return existing as Promise<T>
  const promise = (async () => {
    const value = await loader()
    if (session === readSessionRevision.value) rememberRead(key, value, revision)
    return value
  })().finally(() => {
    if (pending.get(identity) === promise) pending.delete(identity)
  })
  pending.set(identity, promise)
  return promise
}
