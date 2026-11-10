<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { request, state } from '../store'
import { scrollToSection, useSettingsForm } from '../settings'
import ReadRegion from '../components/ReadRegion.vue'
import FormFeedback from '../components/FormFeedback.vue'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
import TimezoneField from '../components/TimezoneField.vue'
import OverviewSettings from './OverviewSettings.vue'
interface General {
  name: string
  description: string
  timezone: string
  available: string[]
  workspace_revision: number
  display_revision: number
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
// The page holds two independently saved forms; leaving is guarded while either has a draft.
const generalDirty = ref(false),
  overviewDirty = ref(false)
watch([generalDirty, overviewDirty], ([general, overview]) => emit('dirty', general || overview))
const invalidName = ref(false)
const form = useSettingsForm<General, { name: string; description: string; timezone: string }>({
  name: '通用设置',
  read: () => request<General>('manage/preferences'),
  write: (draft, saved) =>
    request<General>('manage/preferences', 'PUT', {
      name: draft.name.trim(),
      description: draft.description.trim(),
      timezone: draft.timezone,
      workspace_revision: saved.workspace_revision,
      display_revision: saved.display_revision,
    }),
  draftOf: ({ name, description, timezone }) => ({ name, description, timezone }),
  applied: (value) => {
    invalidName.value = false
    Object.assign(state.settings, {
      workspaceName: value.name,
      workspaceDescription: value.description,
      timezone: value.timezone,
    })
  },
  validate: (draft) => {
    invalidName.value = !draft.name.trim() || draft.name.trim().length > 24
    if (invalidName.value) return '工作空间名称应为1–24个字符。'
    return draft.description.trim().length > 40 ? '工作空间说明最多40个字符。' : ''
  },
  dirty: (value) => (generalDirty.value = value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
onMounted(async () => {
  await form.load()
  await nextTick()
  scrollToSection('timezone', 'timezone-settings')
})
</script>
<template>
  <div class="settings-stack">
    <section class="panel settings-card">
      <div class="panel-heading">
        <h2>通用设置</h2>
      </div>
      <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
      <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="300">
        <form v-if="saved" class="form-content form-stack" novalidate @submit.prevent="form.save">
          <fieldset class="plain-fieldset form-stack" :disabled="busy">
            <section class="settings-section" aria-labelledby="workspace-section-title">
              <div class="settings-section-heading">
                <h3 id="workspace-section-title">工作空间</h3>
                <p>显示在导航顶部</p>
              </div>
              <div class="general-fields-grid">
                <div class="form-stack">
                  <label for="workspace-name">工作空间名称</label>
                  <input
                    id="workspace-name"
                    v-model="draft.name"
                    class="text-input"
                    maxlength="24"
                    :aria-invalid="invalidName"
                    aria-describedby="workspace-name-help"
                  />
                  <p v-if="invalidName" id="workspace-name-help" class="small-note">
                    请输入1–24个字符的名称。
                  </p>
                </div>
                <div class="form-stack">
                  <label for="workspace-description"
                    >工作空间说明 <span class="optional">选填</span></label
                  >
                  <input
                    id="workspace-description"
                    v-model="draft.description"
                    class="text-input"
                    maxlength="40"
                  />
                </div>
              </div>
            </section>
            <section class="settings-section" aria-labelledby="time-section-title">
              <div class="settings-section-heading">
                <h3 id="time-section-title">时间显示</h3>
              </div>
              <TimezoneField
                v-model="draft.timezone"
                :available="saved.available"
                :disabled="busy"
              />
            </section>
          </fieldset>
          <SettingsSaveBar
            :dirty="dirty"
            :busy="busy"
            :done="done"
            label="保存通用设置"
            done-text="通用设置已保存"
            @discard="form.discard"
          />
        </form>
      </ReadRegion>
    </section>
    <OverviewSettings @dirty="overviewDirty = $event" />
  </div>
</template>
