<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from './Icon.vue'
import ReadRegion from './ReadRegion.vue'
import { request } from '../store'
import { useRemote, resultLabels } from '../history'
import {
  elapsed,
  handlingBadges,
  handlingLabels,
  stageLabels,
  stamp,
  type Guide,
  type Handling,
  type Problem,
  type ProblemDetail,
} from '../operations'
const props = defineProps<{ eventId: string | null; problem?: Problem }>()
const emit = defineEmits<{ close: []; navigate: [path: string] }>()
const panel = ref<HTMLDialogElement>()
const detail = useRemote(
  () =>
    props.eventId
      ? request<ProblemDetail>('manage/operations/problems/' + props.eventId)
      : Promise.resolve(undefined),
  () => props.eventId,
)
const record = computed(() => detail.data.value)
const label = computed(() => record.value?.label ?? props.problem?.label ?? '')
const guide = computed<Guide | undefined>(() => record.value?.guide ?? props.problem?.guide)
const code = computed(() => record.value?.code ?? props.problem?.code ?? null)
const handling = computed<Handling | null>(
  () => record.value?.handling ?? (record.value ? null : (props.problem?.status ?? null)),
)
const hint = computed(() => record.value?.hint ?? props.problem?.hint ?? null)
const started = computed(() => record.value?.started_at ?? props.problem?.since ?? null)
const nextAttempt = computed(
  () => record.value?.next_attempt_at ?? props.problem?.next_attempt_at ?? null,
)
const failures = computed(() => record.value?.failures ?? props.problem?.failures ?? null)
const lasted = computed(() => {
  if (record.value?.ended_at && started.value) return elapsed(record.value.ended_at - started.value)
  return started.value ? elapsed(Date.now() / 1000 - started.value) : '—'
})
const facts = computed(() =>
  [
    { key: '开始时间', value: stamp(started.value) },
    { key: record.value?.ended_at ? '持续' : '已持续', value: lasted.value },
    { key: '恢复时间', value: record.value?.ended_at ? stamp(record.value.ended_at) : '' },
    { key: '失败次数', value: failures.value === null ? '' : failures.value + ' 次' },
    { key: '错误码', value: code.value || '' },
    {
      key: '首次错误码',
      value:
        record.value?.first_code && record.value.first_code !== code.value
          ? record.value.first_code
          : '',
    },
    { key: '下次重试', value: nextAttempt.value ? stamp(nextAttempt.value) : '' },
  ].filter((fact) => fact.value),
)
const statusText = computed(() =>
  record.value?.status === 'recovered'
    ? '已恢复'
    : record.value?.status === 'paused'
      ? '已暂停'
      : '',
)
const verifyPath = computed(() => {
  const verify = record.value?.verify
  if (verify?.kind === 'rss_test') return '/websites/' + verify.website_id
  if (verify?.kind === 'target_test') return '/target/' + verify.target_id
  return ''
})
const verifyKind = computed(() => record.value?.verify?.kind ?? guide.value?.verify ?? null)
const alertPhases: Record<string, string> = {
  fault: '故障通知',
  reminder: '仍未恢复提醒',
  recovery: '恢复通知',
}
const alertLabels: Record<string, string> = {
  ...resultLabels,
  pending: '等待发送',
  cancelled: '已取消',
}
function close() {
  panel.value?.close()
  document.body.classList.remove('website-panel-open')
  emit('close')
}
function follow(path: string) {
  close()
  emit('navigate', path)
}
onMounted(() => {
  panel.value?.showModal()
  document.body.classList.add('website-panel-open')
})
onBeforeUnmount(() => document.body.classList.remove('website-panel-open'))
</script>
<template>
  <dialog
    ref="panel"
    class="website-drawer"
    :aria-label="label + ' 问题详情'"
    @cancel.prevent="close"
    @click="
      (event) => {
        if (event.target === panel) close()
      }
    "
  >
    <div class="website-drawer-shell">
      <header class="website-drawer-header">
        <div>
          <h2>{{ label }}</h2>
          <p v-if="guide" class="problem-reason">
            {{ stageLabels[guide.stage] || guide.stage }}：{{ guide.summary }}
          </p>
        </div>
        <button class="icon-button" aria-label="关闭问题详情" @click="close">
          <Icon name="close" :size="21" />
        </button>
      </header>
      <div class="website-drawer-body">
        <p v-if="handling || statusText" class="problem-state">
          <span v-if="handling" class="small-badge" :class="handlingBadges[handling]">{{
            handlingLabels[handling]
          }}</span>
          <span v-else class="small-badge neutral">{{ statusText }}</span>
          <span v-if="hint">{{ hint }}</span>
        </p>
        <ReadRegion
          :loading="detail.loading.value"
          :error="detail.error.value"
          :has-data="!!record || !eventId"
          :min-height="280"
          @retry="detail.reload"
        >
          <dl class="problem-facts">
            <div v-for="fact in facts" :key="fact.key">
              <dt>{{ fact.key }}</dt>
              <dd>{{ fact.value }}</dd>
            </div>
          </dl>
          <section v-if="record?.crash" class="drawer-section">
            <h3>崩溃位置</h3>
            <p>
              <code>{{ record.crash.exception || '任务意外退出' }}</code>
              <template v-if="record.crash.location">
                ·
                <code>
                  {{ record.crash.location.file }}:{{ record.crash.location.line }}
                  {{ record.crash.location.function }}
                </code>
              </template>
            </p>
            <p v-if="record.crash.version" class="small-note">版本 {{ record.crash.version }}</p>
          </section>
          <section v-if="guide" class="drawer-section">
            <h3>可能原因</h3>
            <ul>
              <li v-for="cause in guide.causes" :key="cause">{{ cause }}</li>
            </ul>
          </section>
          <section v-if="guide" class="drawer-section">
            <h3>下一步</h3>
            <ol>
              <li v-for="step in guide.steps" :key="step">{{ step }}</li>
            </ol>
          </section>
          <section v-if="verifyKind" class="drawer-section">
            <h3>验证</h3>
            <button
              v-if="verifyPath"
              class="button primary problem-verify"
              @click="follow(verifyPath)"
            >
              {{ verifyKind === 'rss_test' ? '打开连接测试' : '打开目标配置' }}
            </button>
            <p class="small-note">
              <template v-if="verifyKind === 'rss_test'">
                连接测试只检查连接和解析，不入库、不发通知。修好后无需操作，下一轮采集成功时自动标记恢复。
              </template>
              <template v-else-if="verifyKind === 'target_test'">
                目标测试会真实发送一条消息。测试通过后显示“等待验证”，下次真实发送成功时自动标记恢复。
              </template>
              <template v-else>重启容器后，后台服务恢复运行即标记恢复。</template>
            </p>
          </section>
          <section v-if="record?.recent.length" class="drawer-section">
            <h3>{{ record.kind === 'source' ? '最近采集记录' : '最近投递尝试' }}</h3>
            <div v-for="row in record.recent" :key="row.at + row.label" class="problem-log">
              <span>{{ stamp(row.at) }}</span>
              <strong :class="'tone-' + row.tone">{{ row.label }}</strong>
              <span>{{ row.text }}</span>
            </div>
          </section>
          <section v-if="record" class="drawer-section">
            <h3>系统告警发送结果</h3>
            <div
              v-for="row in record.alerts"
              :key="row.phase + row.target_name + row.finished_at"
              class="problem-log"
            >
              <span>{{ alertPhases[row.phase] || row.phase }} · {{ row.target_name }}</span>
              <strong>{{ alertLabels[row.result] || row.result }}</strong>
              <span>{{
                [stamp(row.finished_at), row.error_code].filter(Boolean).join(' · ')
              }}</span>
            </div>
            <p v-if="!record.alerts.length" class="small-note">这次问题没有发送系统告警。</p>
          </section>
        </ReadRegion>
      </div>
    </div>
  </dialog>
</template>
<style scoped>
.problem-reason {
  margin: 2px 0 0;
}
.problem-state {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
}
.problem-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin: 0 0 20px;
  padding: 14px 16px;
  background: #fdfbf8;
  border: 1px solid #ede3d8;
  border-radius: 10px;
}
.problem-facts dt {
  font-size: 12px;
  color: #5d6673;
}
.problem-facts dd {
  margin: 0;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.drawer-section h3 {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
}
.drawer-section ul,
.drawer-section ol {
  margin: 0;
  padding-left: 18px;
}
.problem-verify {
  margin-bottom: 8px;
}
.problem-log {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) 90px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 0;
  border-top: 1px solid #f0f1f3;
  overflow-wrap: anywhere;
}
.tone-ok {
  color: #2f6f4f;
}
.tone-fail {
  color: #a8324a;
}
.tone-warn,
.tone-wait {
  color: #8a5a0b;
}
</style>
