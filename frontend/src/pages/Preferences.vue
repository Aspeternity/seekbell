<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, request, state } from '../store'
import ReadRegion from '../components/ReadRegion.vue'
import FormFeedback from '../components/FormFeedback.vue'
import TimezoneField from '../components/TimezoneField.vue'
interface General {
  name: string
  description: string
  timezone: string
  available: string[]
  workspace_revision: number
  display_revision: number
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
const saved = ref<General>(),
  name = ref(''),
  description = ref(''),
  timezone = ref('')
const busy = ref(false),
  error = ref(''),
  done = ref(false),
  invalidName = ref(false)
let active = true
onBeforeUnmount(() => {
  active = false
})
const dirty = computed(
  () =>
    !!saved.value &&
    (name.value !== saved.value.name ||
      description.value !== saved.value.description ||
      timezone.value !== saved.value.timezone),
)
watch(dirty, (value) => {
  emit('dirty', value)
  if (value) done.value = false
})
function apply(value: General) {
  saved.value = value
  name.value = value.name
  description.value = value.description
  timezone.value = value.timezone
  Object.assign(state.settings, {
    workspaceName: value.name,
    workspaceDescription: value.description,
    timezone: value.timezone,
  })
}
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  done.value = false
  invalidName.value = false
  try {
    const value = await request<General>('manage/preferences')
    if (active) apply(value)
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function reload() {
  if (dirty.value)
    confirmAction('重新读取通用设置？', '尚未保存的修改将丢失。', load, '放弃修改并读取')
  else void load()
}
function discard() {
  if (!saved.value || busy.value) return
  confirmAction(
    '放弃本页修改？',
    '将恢复为本次读取的通用设置。',
    () => {
      apply(saved.value!)
      error.value = ''
      invalidName.value = false
    },
    '放弃修改',
  )
}
async function save() {
  if (busy.value || !saved.value || !dirty.value) return
  error.value = ''
  done.value = false
  invalidName.value = !name.value.trim() || name.value.trim().length > 24
  if (invalidName.value) {
    error.value = '工作空间名称应为1–24个字符。'
    return
  }
  if (description.value.trim().length > 40) {
    error.value = '工作空间说明最多40个字符。'
    return
  }
  busy.value = true
  try {
    const value = await request<General>('manage/preferences', 'PUT', {
      name: name.value.trim(),
      description: description.value.trim(),
      timezone: timezone.value,
      workspace_revision: saved.value.workspace_revision,
      display_revision: saved.value.display_revision,
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
  if (location.hash.includes('section=timezone'))
    document.getElementById('timezone-settings')?.scrollIntoView({ block: 'center' })
})
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>通用设置</h2>
      </div>
    </div>
    <FormFeedback :error="error" @retry="reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="360">
      <form v-if="saved" class="form-content form-stack" novalidate @submit.prevent="save">
        <fieldset class="plain-fieldset form-stack" :disabled="busy">
          <section class="settings-section" aria-labelledby="workspace-section-title">
            <div class="settings-section-heading">
              <h3 id="workspace-section-title">工作空间</h3>
            </div>
            <div class="form-stack">
              <div class="general-fields-grid">
                <div class="form-stack">
                  <label for="workspace-name">工作空间名称</label>
                  <input
                    id="workspace-name"
                    v-model="name"
                    class="text-input"
                    maxlength="24"
                    :aria-invalid="invalidName"
                    aria-describedby="workspace-name-help"
                  />
                  <p id="workspace-name-help" class="small-note">
                    {{ invalidName ? '请输入1–24个字符的名称。' : '显示在导航顶部' }}
                  </p>
                </div>
                <div class="form-stack">
                  <label for="workspace-description"
                    >工作空间说明 <span class="optional">选填</span></label
                  >
                  <input
                    id="workspace-description"
                    v-model="description"
                    class="text-input"
                    maxlength="40"
                  />
                </div>
              </div>
              <div class="workspace-preview-row">
                <span class="small-note">导航外观预览</span>
                <div class="workspace-preview" aria-label="工作空间外观预览">
                  <span class="workspace-icon">{{
                    name.trim() === '个人工作空间'
                      ? 'S'
                      : Array.from(name.trim())[0]?.toUpperCase() || 'S'
                  }}</span
                  ><span class="workspace-copy"
                    ><strong>{{ name.trim() || '工作空间名称' }}</strong
                    ><small>{{ description }}</small></span
                  >
                </div>
              </div>
            </div>
          </section>
          <section class="settings-section" aria-labelledby="time-section-title">
            <div class="settings-section-heading">
              <h3 id="time-section-title">时间显示</h3>
            </div>
            <TimezoneField v-model="timezone" :available="saved.available" :disabled="busy" />
          </section>
        </fieldset>
        <div class="inline-form-footer settings-savebar">
          <span role="status">{{
            done ? '通用设置已保存' : dirty ? '有未保存的修改' : '没有未保存的修改'
          }}</span>
          <div class="inline-actions">
            <button class="button" type="button" :disabled="busy || !dirty" @click="discard">
              放弃修改
            </button>
            <button class="button primary" type="submit" :disabled="busy || !dirty">
              {{ busy ? '保存中…' : '保存通用设置' }}
            </button>
          </div>
        </div>
      </form>
    </ReadRegion>
  </section>
</template>
