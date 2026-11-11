import { inject, provide, watch, type InjectionKey } from 'vue'

/**
 * How long a view may hold back for its first data. Pages are rendered inside <Suspense>
 * (App, the settings shell and the operations shell), which keeps the previous view on
 * screen while the next one is pending, so a page that awaits this at the end of its
 * setup appears complete instead of as empty cards that then fill in and jump. A slow
 * read only delays it this long; the page then shows its loading state at once.
 */
const HOLD_MS = 400
const heldBack: InjectionKey<() => boolean> = Symbol('held back')

/**
 * Resolves when `work` settles (a promise) or holds (a condition), or after the hold time.
 * Call it in a component's setup, before its first await.
 */
export function untilShown(work: Promise<unknown> | (() => unknown)): Promise<void> {
  let expired = false
  provide(heldBack, () => expired)
  if (typeof work === 'function' && work()) return Promise.resolve()
  return new Promise((resolve) => {
    let stop = () => {}
    const finish = () => {
      clearTimeout(timer)
      stop()
      resolve()
    }
    const timer = setTimeout(() => {
      expired = true
      finish()
    }, HOLD_MS)
    if (typeof work === 'function') stop = watch(work, (value) => value && finish())
    else work.then(finish, finish)
  })
}

/** Whether the page holding this component already waited out the hold, so its first
 *  loading indicator has nothing left to delay. Call it in setup. */
export const shownAfterHold = () => inject(heldBack, () => false)()
