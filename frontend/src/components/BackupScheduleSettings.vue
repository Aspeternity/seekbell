<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { request } from '../store'
import { stamp, useSettingsForm } from '../settings'
import { WEEKDAYS, type BackupSchedule } from '../backups'
import AppSelect from './AppSelect.vue'
import FormFeedback from './FormFeedback.vue'
import ReadRegion from './ReadRegion.vue'
import SettingsSaveBar from './SettingsSaveBar.vue'
import Toggle from './Toggle.vue'
interface Draft {
  enabled: boolean
  frequency: 'daily' | 'weekly'
  weekday: number
  hour: number
  minute: number
  keep: number
}
const emit = defineEmits<{ dirty: [value: boolean]; saved: [] }>()
// One list for how often: daily, or weekly on a given day ("w0" is Monday). A single
// control keeps its width, so nothing beside it moves when switching.
const repeats = [
  { value: 'daily', label: '每天' },
  ...WEEKDAYS.map((label, day) => ({ value: 'w' + day, label: '每' + label })),
]
const two = (value: number) => String(value).padStart(2, '0')
const hours = Array.from({ length: 24 }, (_, value) => ({ value, label: two(value) }))
const form = useSettingsForm<BackupSchedule, Draft>({
  name: '自动备份设置',
  read: () => request<BackupSchedule>('manage/backups/schedule'),
  write: async (draft, saved) => {
    const value = await request<BackupSchedule>('manage/backups/schedule', 'PUT', {
      enabled: draft.enabled,
      frequency: draft.frequency,
      weekday: draft.weekday,
      minute: draft.hour * 60 + draft.minute,
      keep: draft.keep,
      revision: saved.revision,
    })
    emit('saved')
    return value
  },
  draftOf: (saved) => ({
    enabled: saved.enabled,
    frequency: saved.frequency,
    weekday: saved.weekday,
    hour: Math.floor(saved.minute / 60),
    minute: saved.minute % 60,
    keep: saved.keep,
  }),
  validate: (draft) => {
    if (!Number.isInteger(draft.keep) || draft.keep < 1 || draft.keep > 60)
      return '保留份数应为 1–60 之间的整数。'
    return ''
  },
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
const repeat = computed({
  get: () => (draft.value.frequency === 'daily' ? 'daily' : 'w' + draft.value.weekday),
  set: (value: string) => {
    if (value === 'daily') draft.value.frequency = 'daily'
    else Object.assign(draft.value, { frequency: 'weekly', weekday: Number(value.slice(1)) })
  },
})
// Every five minutes; a time saved off that grid stays selectable.
const minutes = computed(() => {
  const values = Array.from({ length: 12 }, (_, index) => index * 5)
  const current = draft.value?.minute
  if (current !== undefined && !values.includes(current)) values.push(current)
  return values.sort((a, b) => a - b).map((value) => ({ value, label: two(value) }))
})
// The heading shows when the saved plan runs next; the controls below show the plan itself.
const nextText = computed(() => {
  const value = saved.value
  if (!value) return ''
  if (!value.enabled) return '已关闭'
  return value.next_run_at ? '下次 ' + stamp(value.next_run_at) : ''
})
onMounted(form.load)
</script>
<template>
  <section id="backup-schedule" class="panel settings-card" aria-labelledby="backup-schedule-title">
    <div class="panel-heading">
      <div>
        <h2 id="backup-schedule-title">自动备份</h2>
        <p v-if="nextText" class="backup-next">{{ nextText }}</p>
      </div>
      <Toggle v-if="saved" v-model="draft.enabled" label="启用自动备份" :disabled="busy" />
    </div>
    <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="120">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <fieldset class="plain-fieldset backup-schedule-fields" :disabled="busy || !draft.enabled">
          <div class="form-stack">
            <label class="field-label" for="backup-frequency">频率</label>
            <div class="backup-schedule-pair">
              <AppSelect
                id="backup-frequency"
                v-model="repeat"
                :options="repeats"
                :disabled="busy || !draft.enabled"
                aria-label="频率"
              />
            </div>
          </div>
          <div class="form-stack">
            <label class="field-label" for="backup-hour">时间</label>
            <div class="backup-schedule-pair backup-clock">
              <AppSelect
                id="backup-hour"
                v-model="draft.hour"
                :options="hours"
                :disabled="busy || !draft.enabled"
                aria-label="小时"
              /><span aria-hidden="true">:</span
              ><AppSelect
                v-model="draft.minute"
                :options="minutes"
                :disabled="busy || !draft.enabled"
                aria-label="分钟"
              />
            </div>
          </div>
          <div class="form-stack">
            <label class="field-label" for="backup-keep">保留份数</label>
            <div class="unit-input backup-keep">
              <input
                id="backup-keep"
                v-model.number="draft.keep"
                type="number"
                class="text-input"
                aria-label="自动备份保留份数"
                min="1"
                max="60"
                step="1"
                required
              /><span>份</span>
            </div>
          </div>
        </fieldset>
        <SettingsSaveBar
          :dirty="dirty"
          :busy="busy"
          :done="done"
          label="保存自动备份"
          done-text="自动备份设置已保存"
          @discard="form.discard"
        />
      </form>
    </ReadRegion>
  </section>
</template>
