import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { confirmAction, formatTime } from './store'

// The single definition of the settings tabs: the shell renders it and the router checks it.
export const settingsTabs = [
  { value: 'preferences', label: '通用' },
  { value: 'alerts', label: '告警' },
  { value: 'data', label: '数据' },
  { value: 'backup', label: '备份' },
  { value: 'account', label: '账户' },
  { value: 'about', label: '关于' },
]

export const byteSize = (bytes: number | null) =>
  bytes == null
    ? '—'
    : bytes === 0
      ? '0 KiB'
      : bytes >= 1024 ** 3
        ? (bytes / 1024 ** 3).toFixed(2) + ' GiB'
        : bytes >= 1024 ** 2
          ? (bytes / 1024 ** 2).toFixed(2) + ' MiB'
          : (bytes / 1024).toFixed(1) + ' KiB'
export const stamp = (seconds: number) => formatTime(new Date(seconds * 1000).toISOString())

export function scrollToSection(section: string, id: string) {
  if (location.hash.includes('section=' + section))
    document.getElementById(id)?.scrollIntoView({ block: 'start' })
}

/** One editable settings resource: read it, edit a draft, save with its revision. */
export function useSettingsForm<Saved, Draft>(options: {
  /** How the resource is named in confirmations, e.g. “通用设置”. */
  name: string
  read: () => Promise<Saved>
  write: (draft: Draft, saved: Saved) => Promise<Saved>
  draftOf: (saved: Saved) => Draft
  /** Mirrors a freshly read or saved value into shared state. */
  applied?: (saved: Saved) => void
  /** A message blocks the save; nothing is sent. */
  validate?: (draft: Draft) => string
  /** Asked before saving when it returns text, e.g. for an irreversible change. */
  confirmSave?: (draft: Draft, saved: Saved) => { body: string; label: string } | undefined
  dirty: (value: boolean) => void
}) {
  const saved = ref<Saved>() as Ref<Saved | undefined>
  const draft = ref<Draft>() as Ref<Draft>
  const busy = ref(false),
    error = ref(''),
    // Only a failed read or a version conflict is fixed by reading again.
    reloadable = ref(false),
    done = ref(false)
  let active = true
  onBeforeUnmount(() => {
    active = false
  })
  const dirty = computed(
    () =>
      saved.value !== undefined &&
      JSON.stringify(draft.value) !== JSON.stringify(options.draftOf(saved.value)),
  )
  watch(
    dirty,
    (value) => {
      options.dirty(value)
      if (value) done.value = false
    },
    { immediate: true },
  )
  function apply(value: Saved) {
    saved.value = value
    draft.value = options.draftOf(value)
    options.applied?.(value)
  }
  function fail(e: unknown, reload: boolean) {
    if (!active) return
    error.value = (e as Error).message
    reloadable.value = reload
  }
  async function load() {
    if (busy.value) return
    busy.value = true
    error.value = ''
    done.value = false
    try {
      const value = await options.read()
      if (active) apply(value)
    } catch (e) {
      fail(e, true)
    } finally {
      busy.value = false
    }
  }
  function reload() {
    if (dirty.value)
      confirmAction(
        '重新读取' + options.name + '？',
        '尚未保存的修改将丢失。',
        load,
        '放弃修改并读取',
      )
    else void load()
  }
  function discard() {
    if (saved.value === undefined || busy.value) return
    confirmAction(
      '放弃本页修改？',
      '将恢复为本次读取的' + options.name + '。',
      () => {
        draft.value = options.draftOf(saved.value!)
        error.value = ''
      },
      '放弃修改',
    )
  }
  async function persist() {
    if (busy.value || saved.value === undefined) return
    busy.value = true
    error.value = ''
    done.value = false
    try {
      const value = await options.write(draft.value, saved.value)
      if (active) {
        apply(value)
        done.value = true
      }
    } catch (e) {
      fail(e, (e as { status?: number }).status === 409)
    } finally {
      busy.value = false
    }
  }
  function save() {
    if (busy.value || saved.value === undefined || !dirty.value) return
    error.value = ''
    done.value = false
    const invalid = options.validate?.(draft.value)
    if (invalid) {
      error.value = invalid
      reloadable.value = false
      return
    }
    const ask = options.confirmSave?.(draft.value, saved.value)
    if (ask) confirmAction('保存' + options.name + '？', ask.body, persist, ask.label)
    else void persist()
  }
  return { saved, draft, busy, error, reloadable, done, dirty, load, reload, discard, save }
}
