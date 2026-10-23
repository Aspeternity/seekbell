<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, formatTime, request, state } from '../store'
import { useRemote, resultLabels, kindLabels } from '../history'
import type { Page } from '../history'
import Pagination from '../components/Pagination.vue'
import ReadRegion from '../components/ReadRegion.vue'
import Toggle from '../components/Toggle.vue'
interface Settings {
  enabled: boolean
  target_ids: string[]
  revision: number
}
interface Event {
  id: string
  label: string
  phase: string
  code: string | null
  at: number
  deliveries: Record<string, number>
}
interface Fault {
  component: string
  label: string
  code: string | null
  since: number
}
interface Delivery {
  id: string
  target_name: string
  kind: string
  result: string
  error_code: string | null
  started_at: number | null
  finished_at: number | null
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
watch(dirty, (value) => emit('dirty', value), { immediate: true })
const eventPage = ref(1),
  statePage = ref(1),
  selected = ref(''),
  detailPage = ref(1)
const events = useRemote(
  () => request<Page<Event>>('manage/alerts/history?page=' + eventPage.value),
  () => [eventPage.value],
  { cacheKey: () => 'alerts:events:' + eventPage.value, keepPrevious: true },
)
const faults = useRemote(
  () => request<Page<Fault>>('manage/alerts/state?page=' + statePage.value),
  () => [statePage.value],
  { cacheKey: () => 'alerts:faults:' + statePage.value, keepPrevious: true },
)
const details = useRemote(
  () =>
    selected.value
      ? request<Page<Delivery>>(
          'manage/alerts/history/' + selected.value + '?page=' + detailPage.value,
        )
      : Promise.resolve(undefined),
  () => [selected.value, detailPage.value],
  {
    cacheKey: () =>
      selected.value
        ? JSON.stringify(['alerts:detail', selected.value, detailPage.value])
        : undefined,
    keepPrevious: true,
    scope: () => selected.value,
  },
)
const labels: Record<string, string> = { ...resultLabels, pending: '等待发送', cancelled: '已取消' }
const stamp = (value: number | null) =>
  value ? formatTime(new Date(value * 1000).toISOString()) : '尚未记录'
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
        refresh()
      } catch (e) {
        error.value = (e as Error).message
      } finally {
        busy.value = false
      }
    },
    '确认保存告警',
  )
}
function refresh() {
  events.reload()
  faults.reload()
  if (selected.value) details.reload()
}
function open(id: string) {
  selected.value = selected.value === id ? '' : id
  detailPage.value = 1
}
onMounted(load)
</script>
<template>
  <div class="form-stack">
    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>系统故障与恢复告警</h2>
          <p>独立选择接收目标，每次状态变化只通知一次</p>
        </div>
      </div>
      <ReadRegion
        :loading="busy"
        :error="error"
        :has-data="!!settings"
        :min-height="380"
        @retry="load"
      >
        <form v-if="settings" class="form-content form-stack" @submit.prevent="save">
          <div class="setting-row">
            <div>
              <strong>故障与恢复通知</strong><small>默认关闭；启用后通知之后的状态变化</small>
            </div>
            <Toggle v-model="enabled" label="启用故障与恢复告警" :disabled="busy" />
          </div>
          <fieldset class="plain-fieldset">
            <legend class="field-label">告警通知目标</legend>
            <p v-if="!state.targets.length">请先在通知管理中添加已配置目标。</p>
            <label v-for="target in state.targets" :key="target.id" class="check-label">
              <input v-model="targets" type="checkbox" :value="target.id" :disabled="busy" />
              {{ target.name }} · {{ target.type }}{{ target.enabled ? '' : '（已暂停，不发送）' }}
            </label>
          </fieldset>
          <p class="small-note">
            监测正式 RSS
            采集、自动通知渠道和后台服务异常。首次失败标为故障，后续成功标为恢复；持续失败不会每轮通知。暂停不代表恢复，手动连接测试或测试消息不触发系统告警。Webhook
            系统告警使用 schema_version 2、type 为 system_alert，请选择可接收此格式的目标。
          </p>
          <p class="info-note">
            所有事件和各目标的发送结果在本页留证，全部渠道失败也可查看。未知可能已经送达，不自动重发；暂停目标恢复后不补发积压告警。
          </p>
          <div class="inline-form-footer">
            <span role="status">{{
              saved ? '系统告警设置已保存' : dirty ? '有未保存的修改' : '使用已保存的告警设置'
            }}</span>
            <button class="button primary" :disabled="busy || !dirty">
              {{ busy ? '保存中…' : '保存告警设置' }}
            </button>
          </div>
          <button class="button" type="button" :disabled="busy" @click="reload">
            重新读取告警设置
          </button>
        </form>
      </ReadRegion>
    </section>
    <section class="panel settings-card">
      <div class="panel-heading">
        <h2>当前故障</h2>
        <button class="button" @click="refresh">刷新系统事件</button>
      </div>
      <div class="form-content">
        <ReadRegion
          :loading="faults.loading.value"
          :error="faults.error.value"
          :has-data="!!faults.data.value"
          :stale="faults.stale.value"
          :min-height="160"
          @retry="faults.reload"
          ><template v-if="faults.data.value">
            <p v-if="!faults.data.value.total">当前没有已记录的故障。</p>
            <article
              v-for="fault in faults.data.value.items"
              :key="fault.component"
              class="history-evaluation"
            >
              <strong>{{ fault.label }}</strong>
              <p>{{ fault.code }} · {{ stamp(fault.since) }}</p>
            </article>
            <Pagination
              label="当前故障"
              :page="statePage"
              :page-size="20"
              :total="faults.data.value.total"
              @change="statePage = $event"
            /> </template
        ></ReadRegion>
      </div>
    </section>
    <section class="panel settings-card">
      <div class="panel-heading"><h2>系统事件与告警记录</h2></div>
      <div class="form-content">
        <ReadRegion
          :loading="events.loading.value"
          :error="events.error.value"
          :has-data="!!events.data.value"
          :stale="events.stale.value"
          :min-height="160"
          @retry="events.reload"
          ><template v-if="events.data.value">
            <p v-if="!events.data.value.total">尚无系统状态变化记录。</p>
            <article
              v-for="event in events.data.value.items"
              :key="event.id"
              class="history-evaluation system-event"
            >
              <strong>{{ event.phase === 'fault' ? '故障' : '恢复' }} · {{ event.label }}</strong>
              <p>
                {{ stamp(event.at) }} <span v-if="event.code"> · {{ event.code }}</span>
              </p>
              <p v-if="!Object.keys(event.deliveries).length">
                事件发生时未启用告警或未选择目标，未生成通知。
              </p>
              <p v-for="(count, result) in event.deliveries" :key="result">
                {{ labels[result] || result }}：{{ count }}
              </p>
              <button class="button" @click="open(event.id)">
                {{ selected === event.id ? '收起投递结果' : '查看各目标结果' }}
              </button>
              <template v-if="selected === event.id">
                <ReadRegion
                  :loading="details.loading.value"
                  :error="details.error.value"
                  :has-data="!!details.data.value"
                  :stale="details.stale.value"
                  :min-height="160"
                  @retry="details.reload"
                  ><template v-if="details.data.value">
                    <p v-if="!details.data.value.total">没有对应的告警投递。</p>
                    <article
                      v-for="item in details.data.value.items"
                      :key="item.id"
                      class="alert-delivery"
                    >
                      <strong>{{ item.target_name }} · {{ kindLabels[item.kind] }}</strong>
                      <p>
                        {{ labels[item.result] || item.result }}
                        <span v-if="item.error_code"> · {{ item.error_code }}</span>
                      </p>
                      <p>开始 {{ stamp(item.started_at) }} · 完成 {{ stamp(item.finished_at) }}</p>
                    </article>
                    <Pagination
                      label="告警投递"
                      :page="detailPage"
                      :page-size="20"
                      :total="details.data.value.total"
                      @change="detailPage = $event"
                    /> </template
                ></ReadRegion>
              </template>
            </article>
            <Pagination
              label="系统事件"
              :page="eventPage"
              :page-size="20"
              :total="events.data.value.total"
              @change="eventPage = $event"
            /> </template
        ></ReadRegion>
      </div>
    </section>
  </div>
</template>
