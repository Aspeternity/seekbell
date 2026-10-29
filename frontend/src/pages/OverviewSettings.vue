<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, request, state } from '../store'
import { clone } from '../shared'
import type { OverviewPreferences } from '../overviewPreferences'
import OverviewModuleSettings from '../components/OverviewModuleSettings.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
const emit = defineEmits<{ dirty: [value: boolean] }>()
const saved = ref<OverviewPreferences>(),
  draft = ref(clone(state.settings.overviewModules))
const busy = ref(false),
  error = ref(''),
  done = ref(false)
let active = true
onBeforeUnmount(() => {
  active = false
})
const dirty = computed(
  () => !!saved.value && JSON.stringify(draft.value) !== JSON.stringify(saved.value.modules),
)
watch(dirty, (value) => {
  emit('dirty', value)
  if (value) done.value = false
})
function apply(value: OverviewPreferences) {
  saved.value = value
  draft.value = clone(value.modules)
  state.settings.overviewModules = clone(value.modules)
}
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  done.value = false
  try {
    const value = await request<OverviewPreferences>('manage/overview-preferences')
    if (active) apply(value)
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function reload() {
  if (dirty.value)
    confirmAction('重新读取概览布局？', '尚未保存的布局将丢失。', load, '放弃修改并读取')
  else void load()
}
function discard() {
  if (!saved.value || busy.value) return
  confirmAction(
    '放弃本页修改？',
    '将恢复本次读取的概览布局。',
    () => {
      apply(saved.value!)
      error.value = ''
    },
    '放弃修改',
  )
}
async function save() {
  if (busy.value || !saved.value || !dirty.value) return
  busy.value = true
  error.value = ''
  done.value = false
  try {
    const value = await request<OverviewPreferences>('manage/overview-preferences', 'PUT', {
      modules: draft.value,
      revision: saved.value.revision,
    })
    if (active) {
      apply(value)
      done.value = true
    }
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  await load()
  await nextTick()
  if (location.hash.includes('section=overview-modules'))
    document.getElementById('overview-modules')?.scrollIntoView({ block: 'center' })
})
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>界面与概览</h2>
        <p>选择概览内容及显示顺序</p>
      </div>
    </div>
    <FormFeedback :error="error" @retry="reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="300">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="save">
        <div class="settings-section">
          <div class="settings-section-heading">
            <h3>概览内容</h3>
            <p>保留你常看的信息，按习惯调整顺序。顶部统计与采集状态始终显示。</p>
          </div>
          <OverviewModuleSettings v-model="draft" :disabled="busy" />
        </div>
        <div class="inline-form-footer settings-savebar">
          <span role="status">{{
            done ? '概览布局已保存' : dirty ? '有未保存的修改' : '使用已保存的布局'
          }}</span>
          <div class="inline-actions">
            <button class="button" type="button" :disabled="busy || !dirty" @click="discard">
              放弃修改</button
            ><button class="button primary" :disabled="busy || !dirty">
              {{ busy ? '保存中…' : '保存概览布局' }}
            </button>
          </div>
        </div>
      </form>
    </ReadRegion>
  </section>
</template>
