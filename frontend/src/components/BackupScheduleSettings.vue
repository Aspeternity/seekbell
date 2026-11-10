<script setup lang="ts">
import { onMounted } from 'vue'
import { request } from '../store'
import { useSettingsForm } from '../settings'
import { WEEKDAYS, clockMinute, clockText, type BackupSchedule } from '../backups'
import AppSelect from './AppSelect.vue'
import FormFeedback from './FormFeedback.vue'
import ReadRegion from './ReadRegion.vue'
import SettingsSaveBar from './SettingsSaveBar.vue'
import Toggle from './Toggle.vue'
interface Draft {
  enabled: boolean
  frequency: 'daily' | 'weekly'
  weekday: number
  time: string
  keep: number
}
const emit = defineEmits<{ dirty: [value: boolean]; saved: [] }>()
const frequencies = [
  { value: 'daily' as const, label: '每天' },
  { value: 'weekly' as const, label: '每周' },
]
const weekdays = WEEKDAYS.map((label, value) => ({ value, label }))
const form = useSettingsForm<BackupSchedule, Draft>({
  name: '自动备份设置',
  read: () => request<BackupSchedule>('manage/backups/schedule'),
  write: async (draft, saved) => {
    const value = await request<BackupSchedule>('manage/backups/schedule', 'PUT', {
      enabled: draft.enabled,
      frequency: draft.frequency,
      weekday: draft.weekday,
      minute: clockMinute(draft.time),
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
    time: clockText(saved.minute),
    keep: saved.keep,
  }),
  validate: (draft) => {
    if (Number.isNaN(clockMinute(draft.time))) return '请填写备份时间，例如 03:00。'
    if (!Number.isInteger(draft.keep) || draft.keep < 1 || draft.keep > 60)
      return '保留份数应为 1–60 之间的整数。'
    return ''
  },
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
onMounted(form.load)
</script>
<template>
  <section id="backup-schedule" class="panel settings-card" aria-labelledby="backup-schedule-title">
    <div class="panel-heading">
      <div>
        <h2 id="backup-schedule-title">自动备份</h2>
        <p>按时把当前数据备份到上面的列表，防误操作，也方便回退</p>
      </div>
    </div>
    <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="220">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <section class="settings-section" aria-labelledby="backup-plan-title">
          <div class="settings-section-heading">
            <h3 id="backup-plan-title">备份计划</h3>
          </div>
          <div class="form-stack">
            <div class="setting-row">
              <div>
                <strong>自动备份</strong>
                <small>按显示时区 {{ saved.timezone }} 运行；容器停机错过时，启动后补做一次</small>
              </div>
              <Toggle v-model="draft.enabled" label="启用自动备份" :disabled="busy" />
            </div>
            <fieldset class="plain-fieldset form-stack" :disabled="busy || !draft.enabled">
              <legend class="field-label">运行时间</legend>
              <div class="backup-schedule-when">
                <AppSelect
                  v-model="draft.frequency"
                  :options="frequencies"
                  :disabled="busy || !draft.enabled"
                  aria-label="频率"
                />
                <AppSelect
                  v-if="draft.frequency === 'weekly'"
                  v-model="draft.weekday"
                  :options="weekdays"
                  :disabled="busy || !draft.enabled"
                  aria-label="星期"
                />
                <input
                  v-model="draft.time"
                  type="time"
                  class="text-input"
                  aria-label="备份时间"
                  required
                />
              </div>
            </fieldset>
          </div>
        </section>
        <section class="settings-section" aria-labelledby="backup-keep-title">
          <div class="settings-section-heading">
            <h3 id="backup-keep-title">保留</h3>
          </div>
          <fieldset class="plain-fieldset form-stack" :disabled="busy || !draft.enabled">
            <label for="backup-keep">自动备份保留份数</label>
            <div class="unit-input">
              <input
                id="backup-keep"
                v-model.number="draft.keep"
                type="number"
                class="text-input"
                min="1"
                max="60"
                step="1"
                required
              /><span>份</span>
            </div>
            <p class="small-note">
              新的自动备份成功后才删除超出份数的旧自动备份；恢复前的备份保留 30
              天，手动备份不会自动删除。自动备份失败或超过两个周期没有备份时，运行中心和系统告警会提示。
            </p>
          </fieldset>
        </section>
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
