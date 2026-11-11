<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { channelMeta, confirmAction, request, state } from '../store'
import { ago, stamp, useSettingsForm } from '../settings'
import Icon from '../components/Icon.vue'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import { untilShown } from '../viewReady'
import SettingsSaveBar from '../components/SettingsSaveBar.vue'
import Toggle from '../components/Toggle.vue'
interface Recent {
  at: number
  phase: 'fault' | 'recovery' | 'reminder'
  label: string
  results: Record<string, number>
}
interface Settings {
  enabled: boolean
  target_ids: string[]
  delay_seconds: number
  remind_seconds: number
  revision: number
  recent: Recent | null
}
type Draft = Pick<Settings, 'enabled' | 'target_ids' | 'delay_seconds' | 'remind_seconds'>
interface TestResult {
  target_id: string
  target_name: string
  result: string
  error_code: string | null
  summary: string | null
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
const delays = [
  { value: 0, label: '立即' },
  { value: 60, label: '持续 1 分钟' },
  { value: 300, label: '持续 5 分钟' },
]
const reminders = [
  { value: 0, label: '不再提醒' },
  { value: 21600, label: '每 6 小时' },
  { value: 86400, label: '每 24 小时' },
]
const form = useSettingsForm<Settings, Draft>({
  name: '告警设置',
  read: () => request<Settings>('manage/alerts'),
  write: (draft, saved) =>
    request<Settings>('manage/alerts', 'PUT', { ...draft, revision: saved.revision }),
  draftOf: ({ enabled, target_ids, delay_seconds, remind_seconds }) => ({
    enabled,
    target_ids: [...target_ids],
    delay_seconds,
    remind_seconds,
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
const ready = computed(() =>
  state.targets.filter((target) => draft.value.target_ids.includes(target.id) && target.enabled),
)
const receivers = computed(() => ready.value.length)
// A target that fails raises an alert of its own, which it then cannot deliver either.
const oneChannel = computed(() => {
  const channels = new Set(ready.value.map((target) => target.channel))
  const others = state.targets.some((target) => target.enabled && !channels.has(target.channel))
  return channels.size === 1 && others ? ready.value[0].type : ''
})
// The status card describes what is saved, not the draft being edited.
const status = computed(() => {
  const value = saved.value
  if (!value) return null
  const receiving = state.targets.filter(
    (target) => value.target_ids.includes(target.id) && target.enabled,
  ).length
  return { enabled: value.enabled, receiving, idle: value.enabled && !receiving }
})
// Only a delivery problem is worth a line here; the details live in the problem history.
const recent = computed(() => {
  const row = saved.value?.recent
  if (!row) return null
  const failed = Object.entries(row.results)
    .filter(([result]) => result !== 'success' && result !== 'pending')
    .reduce((sum, [, value]) => sum + value, 0)
  return { at: row.at, failed }
})
const meta = (channel: string) =>
  channelMeta[channel as keyof typeof channelMeta] || { icon: 'send', color: 'blue' }
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
function outcome(row: TestResult) {
  const text = outcomes[row.result] || row.result
  if (row.result === 'cancelled' || row.result === 'success') return text
  const reason = row.summary || row.error_code
  return reason ? text + '：' + reason : text
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
  <div class="settings-stack">
    <section class="panel settings-card" aria-labelledby="alert-status-title">
      <div class="panel-heading">
        <h2 id="alert-status-title">系统告警</h2>
        <a class="text-link" href="#/operations/status">查看问题历史</a>
      </div>
      <FormFeedback v-if="!saved" :error="error" :retryable="reloadable" @retry="form.reload" />
      <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="110">
        <div v-if="saved && status" class="form-content">
          <dl class="about-tiles alert-tiles">
            <div
              class="alert-state"
              :class="status.idle ? 'warn' : status.enabled ? 'on' : 'off'"
              data-alert-state
            >
              <dt>
                <span class="about-tile-icon"><Icon name="bell" :size="16" /></span>告警
              </dt>
              <dd>
                <span class="alert-state-value"
                  ><span class="status-dot" />{{ status.enabled ? '已开启' : '已关闭' }}</span
                >
                <small v-if="status.idle">没有可接收的目标</small>
                <small v-else-if="status.enabled">{{ status.receiving }} 个目标接收</small>
                <small v-else>出现故障时不会通知</small>
              </dd>
            </div>
            <div data-alert-recent>
              <dt>
                <span class="about-tile-icon"><Icon name="clock" :size="16" /></span>最近一次告警
              </dt>
              <dd v-if="recent">
                {{ ago(recent.at) }}
                <small>{{ stamp(recent.at) }}</small>
                <small v-if="recent.failed" class="alert-failed">
                  {{ recent.failed }} 个目标未送达或结果未知
                </small>
              </dd>
              <dd v-else class="alert-empty">还没有发出过告警</dd>
            </div>
          </dl>
        </div>
      </ReadRegion>
    </section>
    <section class="panel settings-card" aria-labelledby="alert-settings-title">
      <div class="panel-heading alert-settings-heading">
        <div>
          <h2 id="alert-settings-title">告警设置</h2>
          <p>采集、通知渠道、后台服务、磁盘空间或自动备份出问题及恢复时通知你</p>
        </div>
        <Toggle v-if="saved" v-model="draft.enabled" label="启用故障与恢复告警" :disabled="busy" />
      </div>
      <FormFeedback v-if="saved" :error="error" :retryable="reloadable" @retry="form.reload" />
      <ReadRegion :loading="busy && !saved" error="" :has-data="!!saved" :min-height="380">
        <form v-if="saved" class="form-content form-stack" @submit.prevent="form.save">
          <section class="settings-section" aria-labelledby="alert-receive-title">
            <div class="settings-section-heading">
              <h3 id="alert-receive-title">接收目标</h3>
            </div>
            <div class="form-stack">
              <p v-if="!state.targets.length" class="alert-no-targets">
                还没有通知目标。<a class="text-link" href="#/notifications/targets">去添加</a>
              </p>
              <fieldset v-else class="plain-fieldset" :disabled="busy">
                <legend class="sr-only">接收目标</legend>
                <div class="alert-targets">
                  <label
                    v-for="target in state.targets"
                    :key="target.id"
                    class="alert-target"
                    :class="{
                      selected: draft.target_ids.includes(target.id),
                      paused: !target.enabled,
                    }"
                  >
                    <span class="target-icon" :class="meta(target.channel).color"
                      ><Icon :name="meta(target.channel).icon" :size="15"
                    /></span>
                    <span class="alert-target-text">
                      <strong>{{ target.name }}</strong>
                      <small
                        >{{ target.type
                        }}<span v-if="!target.enabled" class="alert-target-paused"
                          >已暂停，不发送</span
                        ></small
                      >
                    </span>
                    <input v-model="draft.target_ids" type="checkbox" :value="target.id" />
                  </label>
                </div>
              </fieldset>
              <div v-if="state.targets.length" class="alert-target-foot">
                <p class="small-note" role="status">
                  已选择 {{ draft.target_ids.length }} 个 · 可接收 {{ receivers }} 个
                </p>
                <button
                  class="button"
                  type="button"
                  title="按当前勾选发送，无需先保存"
                  :disabled="busy || testing || !receivers"
                  @click="test"
                >
                  <Icon name="send" :size="14" />{{ testing ? '正在发送…' : '发送测试告警' }}
                </button>
              </div>
              <p v-if="draft.enabled && !receivers" class="warning-note">
                当前没有可接收告警的目标，已暂停的目标不会发送。
              </p>
              <p v-else-if="oneChannel" class="warning-note alert-channel-hint">
                所选目标都走
                {{ oneChannel }}，这个渠道本身出故障时告警也发不出去，建议再选一个其他渠道的目标。
              </p>
              <p v-if="testError" class="warning-note" role="alert">{{ testError }}</p>
              <ul v-if="results" class="alert-test-results" aria-label="测试结果">
                <li v-for="row in results" :key="row.target_id" :class="row.result">
                  <Icon :name="row.result === 'success' ? 'check' : 'alert'" :size="14" />
                  <strong>{{ row.target_name }}</strong>
                  <span>{{ outcome(row) }}</span>
                </li>
              </ul>
            </div>
          </section>
          <section class="settings-section" aria-labelledby="alert-rules-title">
            <div class="settings-section-heading">
              <h3 id="alert-rules-title">通知规则</h3>
            </div>
            <div class="form-stack">
              <div class="alert-rule-fields">
                <fieldset class="plain-fieldset alert-rule" :disabled="busy">
                  <legend class="field-label">故障持续多久后通知</legend>
                  <div class="alert-choices">
                    <label
                      v-for="item in delays"
                      :key="item.value"
                      :class="{ active: draft.delay_seconds === item.value }"
                    >
                      <input v-model="draft.delay_seconds" type="radio" :value="item.value" />
                      {{ item.label }}
                    </label>
                  </div>
                  <p class="small-note">在这段时间内自行恢复的故障，故障和恢复都不通知。</p>
                </fieldset>
                <fieldset class="plain-fieldset alert-rule" :disabled="busy">
                  <legend class="field-label">故障一直未恢复时</legend>
                  <div class="alert-choices">
                    <label
                      v-for="item in reminders"
                      :key="item.value"
                      :class="{ active: draft.remind_seconds === item.value }"
                    >
                      <input v-model="draft.remind_seconds" type="radio" :value="item.value" />
                      {{ item.label }}
                    </label>
                  </div>
                  <p class="small-note">提醒和恢复通知只发给收到过这次故障通知的目标。</p>
                </fieldset>
              </div>
              <p class="alert-rule-note">
                <Icon
                  name="help"
                  :size="14"
                />每条告警对每个目标只发一次，失败或结果未知都不重发；开启告警前已经存在的故障不补发。
              </p>
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
  </div>
</template>
