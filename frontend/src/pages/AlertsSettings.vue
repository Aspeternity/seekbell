<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { confirmAction, request, state } from '../store'
import { useSettingsForm } from '../settings'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { untilShown } from '../viewReady'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
import Toggle from '../components/Toggle.vue'
interface Settings {
  enabled: boolean
  target_ids: string[]
  delay_seconds: number
  revision: number
}
interface TestResult {
  target_id: string
  target_name: string
  result: string
  error_code: string | null
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
const delays = [
  { value: 0, label: '立即', note: '故障一出现就通知' },
  { value: 60, label: '持续 1 分钟', note: '1 分钟内自行恢复的故障不通知' },
  { value: 300, label: '持续 5 分钟', note: '5 分钟内自行恢复的故障不通知' },
]
const form = useSettingsForm<Settings, Omit<Settings, 'revision'>>({
  name: '告警设置',
  read: () => request<Settings>('manage/alerts'),
  write: (draft, saved) =>
    request<Settings>('manage/alerts', 'PUT', { ...draft, revision: saved.revision }),
  draftOf: ({ enabled, target_ids, delay_seconds }) => ({
    enabled,
    target_ids: [...target_ids],
    delay_seconds,
  }),
  validate: (draft) =>
    draft.enabled && !draft.target_ids.length ? '启用告警需至少选择一个通知目标。' : '',
  // Turning alerts off cancels what is still waiting to be sent, which cannot be undone.
  confirmSave: (draft, saved) =>
    saved.enabled && !draft.enabled
      ? {
          body: '停止新告警，并取消尚未开始的告警发送。已在发送途中的消息无法撤回。',
          label: '关闭告警',
        }
      : undefined,
  dirty: (value) => emit('dirty', value),
})
const { saved, draft, busy, error, reloadable, done, dirty } = form
const receivers = computed(
  () =>
    state.targets.filter((target) => draft.value.target_ids.includes(target.id) && target.enabled)
      .length,
)
const testing = ref(false),
  testError = ref(''),
  results = ref<TestResult[]>()
let active = true
onBeforeUnmount(() => {
  active = false
})
const outcomes: Record<string, string> = {
  success: '已送达',
  cancelled: '目标已暂停，未发送',
  unknown: '结果未知，请到接收端确认',
  transient_error: '暂时失败',
  permanent_error: '被拒绝',
}
function test() {
  if (testing.value || !receivers.value) return
  const target_ids = [...draft.value.target_ids]
  confirmAction(
    '发送测试告警？',
    '将向所选的 ' +
      receivers.value +
      ' 个可接收目标各真实发送一条标明为测试的消息，不写入问题历史。',
    async () => {
      testing.value = true
      testError.value = ''
      results.value = undefined
      try {
        const value = await request<{ items: TestResult[] }>('manage/alerts/test', 'POST', {
          target_ids,
        })
        if (active) results.value = value.items
      } catch (e) {
        if (active) testError.value = (e as Error).message
      } finally {
        testing.value = false
      }
    },
    '发送测试',
  )
}
await untilShown(form.load())
</script>
<template>
  <section class="panel settings-card">
    <div class="panel-heading">
      <div>
        <h2>系统告警</h2>
        <p>采集、通知渠道、后台服务或磁盘空间出问题及恢复时通知你</p>
      </div>
      <a class="text-link" href="#/operations/status">查看问题历史</a>
    </div>
    <FormFeedback :error="error" :retryable="reloadable" @retry="form.reload" />
    <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="380">
      <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
        <section class="settings-section" aria-labelledby="alert-switch-title">
          <div class="settings-section-heading">
            <h3 id="alert-switch-title">告警开关</h3>
          </div>
          <div class="setting-row">
            <div><strong>故障与恢复通知</strong><small>每次状态变化只通知一次</small></div>
            <Toggle v-model="draft.enabled" label="启用故障与恢复告警" :disabled="busy" />
          </div>
        </section>
        <section class="settings-section" aria-labelledby="alert-delay-title">
          <div class="settings-section-heading">
            <h3 id="alert-delay-title">通知时机</h3>
          </div>
          <fieldset class="plain-fieldset form-stack" :disabled="busy">
            <legend class="field-label">故障持续多久后通知</legend>
            <div class="alert-delay-options">
              <label v-for="item in delays" :key="item.value" class="check-label">
                <input v-model="draft.delay_seconds" type="radio" :value="item.value" />
                {{ item.label }}
              </label>
            </div>
            <p class="small-note" role="status">
              {{ delays.find((item) => item.value === draft.delay_seconds)?.note }}
            </p>
          </fieldset>
        </section>
        <section class="settings-section" aria-labelledby="alert-targets-title">
          <div class="settings-section-heading">
            <h3 id="alert-targets-title">接收目标</h3>
          </div>
          <div class="form-stack">
            <fieldset class="plain-fieldset alert-target-list">
              <legend class="field-label">告警通知目标</legend>
              <p v-if="!state.targets.length">
                还没有通知目标。<a class="text-link" href="#/notifications/targets">去添加</a>
              </p>
              <label v-for="target in state.targets" :key="target.id" class="check-label">
                <input
                  v-model="draft.target_ids"
                  type="checkbox"
                  :value="target.id"
                  :disabled="busy"
                />
                {{ target.name }} · {{ target.type
                }}{{ target.enabled ? '' : '（已暂停，不发送）' }}
              </label>
            </fieldset>
            <p class="small-note" role="status">
              已选择 {{ draft.target_ids.length }} 个目标 · 当前可接收 {{ receivers }} 个
            </p>
            <p v-if="draft.enabled && !receivers" class="warning-note">
              当前没有可接收告警的目标，已暂停的目标不会发送。
            </p>
            <div class="alert-test">
              <button
                class="button"
                type="button"
                :disabled="busy || testing || !receivers"
                @click="test"
              >
                {{ testing ? '正在发送…' : '发送测试告警' }}
              </button>
              <span class="small-note">按当前勾选发送，无需先保存</span>
            </div>
            <p v-if="testError" class="warning-note" role="alert">{{ testError }}</p>
            <ul v-if="results" class="alert-test-results" aria-label="测试结果">
              <li v-for="row in results" :key="row.target_id" :class="row.result">
                <strong>{{ row.target_name }}</strong>
                <span
                  >{{ outcomes[row.result] || row.result
                  }}{{
                    row.error_code && row.result !== 'cancelled' ? '（' + row.error_code + '）' : ''
                  }}</span
                >
              </li>
            </ul>
            <details class="settings-details">
              <summary>发送规则与 Webhook 格式</summary>
              <p class="small-note">
                每个事件、每个目标只尝试一次；结果未知可能已经送达，不自动重发；暂停目标恢复后不补发积压告警；开启后不补发此前的事件。Webhook
                系统告警使用 schema_version 2、type 为 system_alert，alert.phase 为 fault、recovery
                或 test，请选择可接收此格式的目标。
              </p>
            </details>
          </div>
        </section>
        <SettingsSaveBar
          :dirty="dirty"
          :busy="busy"
          :done="done"
          label="保存告警设置"
          done-text="系统告警设置已保存"
          @discard="form.discard"
        />
      </form>
    </ReadRegion>
  </section>
</template>
