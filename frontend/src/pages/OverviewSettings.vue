<script setup lang="ts">
import { nextTick, onMounted } from 'vue'
import { request, state } from '../store'
import { clone } from '../shared'
import { scrollToSection, useSettingsForm } from '../settings'
import { untilShown } from '../viewReady'
import {
  defaultOverviewModules,
  type OverviewModule,
  type OverviewPreferences,
} from '../overviewPreferences'
import OverviewModuleSettings from '../components/OverviewModuleSettings.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
// The page may start the first read alongside its own, rather than after it.
const props = defineProps<{ firstRead?: Promise<OverviewPreferences> }>()
const emit = defineEmits<{ dirty: [value: boolean] }>()
let firstRead = props.firstRead
const form = useSettingsForm<OverviewPreferences, OverviewModule[]>({
  name: '概览布局',
  read: () => {
    const started = firstRead
    firstRead = undefined
    return started ?? request<OverviewPreferences>('manage/overview-preferences')
  },
  write: (modules, saved) =>
    request<OverviewPreferences>('manage/overview-preferences', 'PUT', {
      modules,
      revision: saved.revision,
    }),
  draftOf: (saved) => clone(saved.modules),
  applied: (saved) => (state.settings.overviewModules = clone(saved.modules)),
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
const loaded = form.load()
onMounted(async () => {
  await loaded
  await nextTick()
  scrollToSection('overview-modules', 'overview-modules')
})
await untilShown(loaded)
</script>
<template>
  <section
    id="overview-modules"
    class="panel settings-card"
    aria-labelledby="overview-modules-title"
  >
    <div class="panel-heading">
      <div>
        <h2 id="overview-modules-title">概览显示模块</h2>
        <p>拖动或用箭头调整顺序，顶部统计始终显示</p>
      </div>
      <button
        type="button"
        class="text-link"
        :disabled="busy || !saved"
        @click="draft = defaultOverviewModules()"
      >
        恢复默认布局
      </button>
    </div>
    <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="240">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <OverviewModuleSettings v-model="draft" :disabled="busy" />
        <SettingsSaveBar
          :dirty="dirty"
          :busy="busy"
          :done="done"
          label="保存概览布局"
          done-text="概览布局已保存"
          @discard="form.discard"
        />
      </form>
    </ReadRegion>
  </section>
</template>
