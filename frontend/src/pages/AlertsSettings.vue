<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, request, state } from '../store'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import Toggle from '../components/Toggle.vue'
interface Settings {
  enabled: boolean
  target_ids: string[]
  revision: number
}
let active = true
onBeforeUnmount(() => {
  active = false
})
const emit = defineEmits<{ dirty: [value: boolean] }>()
const settings = ref<Settings | null>(null),
  enabled = ref(false),
  targets = ref<string[]>([])
const error = ref(''),
  busy = ref(false),
  saved = ref(false)
const baseline = computed(() =>
  JSON.stringify([settings.value?.enabled, settings.value?.target_ids]),
)
const dirty = computed(
  () => !!settings.value && JSON.stringify([enabled.value, targets.value]) !== baseline.value,
)
watch(
  dirty,
  (value) => {
    emit('dirty', value)
    if (value) saved.value = false
  },
  { immediate: true },
)
const receivers = computed(
  () =>
    state.targets.filter(
      (target) => targets.value.includes(target.id) && target.enabled && target.configured,
    ).length,
)
function discard() {
  if (!settings.value || busy.value) return
  confirmAction(
    '放弃本页修改？',
    '将恢复本次读取的告警设置。',
    () => {
      enabled.value = settings.value!.enabled
      targets.value = [...settings.value!.target_ids]
      error.value = ''
    },
    '放弃修改',
  )
}
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  saved.value = false
  try {
    const result = await request<Settings>('manage/alerts')
    if (!active) return
    settings.value = result
    enabled.value = settings.value.enabled
    targets.value = [...settings.value.target_ids]
    state.settings.alertTargets = [...targets.value]
    state.settings.recoveryAlerts = enabled.value
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function reload() {
  if (dirty.value)
    confirmAction('重新读取告警设置？', '尚未保存的告警修改将丢失。', load, '放弃修改并读取')
  else load()
}
function save() {
  if (busy.value || !settings.value || !dirty.value) return
  error.value = ''
  if (enabled.value && !targets.value.length) {
    error.value = '启用告警需至少选择一个通知目标。'
    return
  }
  const values = {
    enabled: enabled.value,
    target_ids: [...targets.value],
    revision: settings.value.revision,
  }
  confirmAction(
    '保存系统告警设置？',
    values.enabled
      ? '后台会向所选目标发送之后的故障与恢复通知。不会补发过去事件；每个事件、每个目标只尝试一次，失败或未知请查看记录。'
      : '停止新告警，并取消尚未开始的告警投递。在途消息可能已发出，无法撤回。',
    async () => {
      if (busy.value) return
      busy.value = true
      error.value = ''
      saved.value = false
      try {
        const result = await request<Settings>('manage/alerts', 'PUT', values)
        if (!active) return
        settings.value = result
        enabled.value = settings.value.enabled
        targets.value = [...settings.value.target_ids]
        state.settings.alertTargets = [...targets.value]
        state.settings.recoveryAlerts = enabled.value
        saved.value = true
      } catch (e) {
        error.value = (e as Error).message
      } finally {
        busy.value = false
      }
    },
    '确认保存告警',
  )
}
onMounted(load)
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>系统故障与恢复告警</h2>
        <p>独立选择接收目标，每次状态变化只通知一次</p>
      </div>
    </div>
    <FormFeedback :error="error" @retry="reload" />
    <ReadRegion
      :loading="busy && !settings"
      error=""
      :has-data="!!settings"
      :min-height="380"
      @retry="reload"
    >
      <form v-if="settings" class="form-content form-stack" @submit.prevent="save">
        <section class="settings-section" aria-labelledby="alert-switch-title">
          <div class="settings-section-heading">
            <h3 id="alert-switch-title">告警开关</h3>
            <p>首次失败标为故障，之后成功标为恢复。</p>
          </div>
          <div class="form-stack">
            <div class="setting-row">
              <div>
                <strong>故障与恢复通知</strong><small>默认关闭；启用后通知之后的状态变化</small>
              </div>
              <Toggle v-model="enabled" label="启用故障与恢复告警" :disabled="busy" />
            </div>
            <p class="small-note">
              监测正式 RSS
              采集、自动通知渠道和后台服务异常；持续失败不会每轮通知。暂停不代表恢复，手动连接测试或测试消息不触发系统告警。
            </p>
          </div>
        </section>
        <section class="settings-section" aria-labelledby="alert-targets-title">
          <div class="settings-section-heading">
            <h3 id="alert-targets-title">接收目标</h3>
            <p>从已配置的通知目标中选择。</p>
          </div>
          <div class="form-stack">
            <fieldset class="plain-fieldset alert-target-list">
              <legend class="field-label">告警通知目标</legend>
              <p v-if="!state.targets.length">请先在通知管理中添加已配置目标。</p>
              <label v-for="target in state.targets" :key="target.id" class="check-label">
                <input v-model="targets" type="checkbox" :value="target.id" :disabled="busy" />
                {{ target.name }} · {{ target.type
                }}{{ target.enabled ? '' : '（已暂停，不发送）' }}
              </label>
            </fieldset>
            <p class="small-note" role="status">
              已选择 {{ targets.length }} 个目标 · 当前可接收 {{ receivers }} 个
            </p>
            <p v-if="enabled && !receivers" class="warning-note">
              当前没有可接收告警的目标。暂停目标不会发送，也不会补发暂停期间的告警。
            </p>
            <a v-if="!state.targets.length" class="text-link" href="#/notifications/targets"
              >管理通知目标</a
            >
            <details class="settings-details">
              <summary>发送规则与 Webhook 格式</summary>
              <p class="small-note">
                每个事件、每个目标只尝试一次；结果未知可能已经送达，不自动重发；暂停目标恢复后不补发积压告警。Webhook
                系统告警使用 schema_version 2、type 为 system_alert，请选择可接收此格式的目标。
              </p>
            </details>
            <p class="info-note">
              当前故障和每次告警的发送结果可在“关于与诊断”中查看，全部渠道失败也会留证。
            </p>
          </div>
        </section>
        <div class="inline-form-footer settings-savebar">
          <span role="status">{{
            saved ? '系统告警设置已保存' : dirty ? '有未保存的修改' : '没有未保存的修改'
          }}</span>
          <div class="inline-actions">
            <button class="button" type="button" :disabled="busy || !dirty" @click="discard">
              放弃修改
            </button>
            <button class="button primary" :disabled="busy || !dirty">
              {{ busy ? '保存中…' : '保存告警设置' }}
            </button>
          </div>
        </div>
      </form>
    </ReadRegion>
  </section>
</template>
