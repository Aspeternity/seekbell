<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NCard, NForm, NFormItem, NTag } from 'naive-ui'
import {
  channelNames,
  deliveryStatus,
  explicitResultText,
  getDeliveries,
  getDelivery,
  getTargets,
  localDate,
  message,
} from '../management'
import type {
  DeliveryDetail,
  DeliveryKind,
  DeliveryPage,
  DeliveryRecord,
  Target,
} from '../management'
import SendConfirmation from './SendConfirmation.vue'
defineProps<{ csrf: string }>()
const kind = ref<DeliveryKind>('automatic')
const targetId = ref('')
const status = ref('')
const offset = ref(0)
const result = ref<DeliveryPage | null>(null)
const targets = ref<Target[]>([])
const detail = ref<DeliveryDetail | null>(null)
const confirm = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let timer: ReturnType<typeof setInterval> | undefined
async function load() {
  if (loading.value || busy.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await getDeliveries(
      new URLSearchParams({
        kind: kind.value,
        offset: String(offset.value),
        limit: '20',
        ...(targetId.value ? { target_id: targetId.value } : {}),
        ...(status.value ? { status: status.value } : {}),
      }),
    )
    if (detail.value && !confirm.value)
      detail.value = await getDelivery(detail.value.id, detail.value.kind)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
async function filter() {
  offset.value = 0
  detail.value = null
  confirm.value = false
  await load()
}
async function open(value: Pick<DeliveryRecord, 'id' | 'kind'>) {
  loading.value = true
  error.value = ''
  confirm.value = false
  try {
    detail.value = await getDelivery(value.id, value.kind)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
async function prepareResend() {
  if (!detail.value) return
  await open(detail.value)
  if (detail.value && !error.value) confirm.value = true
}
function kindChanged() {
  status.value = ''
  void filter()
}
async function page(delta: number) {
  offset.value += delta * 20
  await load()
}
onMounted(async () => {
  try {
    targets.value = await getTargets()
  } catch (cause) {
    error.value = message(cause)
  }
  await load()
  timer = setInterval(() => void load(), 5000)
})
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section aria-label="投递记录" :aria-busy="loading || busy">
    <div class="panel-heading">
      <h2>投递记录</h2>
      <NButton :loading="loading" :disabled="busy || confirm" @click="load">刷新记录</NButton>
    </div>
    <p class="muted">
      渠道接受不代表已阅读；SMTP
      仅表示服务器接受。结果未知时重试可能重复。时间按系统显示时区显示，每 5 秒刷新。
    </p>
    <NAlert v-if="error" type="error" class="notice">{{ error }}</NAlert
    ><NAlert v-if="notice" type="info" class="notice">{{ notice }}</NAlert>
    <NForm @submit.prevent="filter"
      ><div class="form-grid">
        <NFormItem label="记录类别" :label-props="{ for: 'delivery-kind' }"
          ><select
            id="delivery-kind"
            v-model="kind"
            class="native-select"
            :disabled="busy || confirm"
            @change="kindChanged"
          >
            <option value="automatic">自动投递</option>
            <option value="manual">手动重发</option>
            <option value="test">目标测试</option>
          </select></NFormItem
        >
        <NFormItem label="通知目标筛选" :label-props="{ for: 'delivery-target' }"
          ><select
            id="delivery-target"
            v-model="targetId"
            class="native-select"
            :disabled="busy || confirm"
          >
            <option value="">全部目标</option>
            <option v-for="target in targets" :key="target.id" :value="target.id">
              {{ target.name }}
            </option>
          </select></NFormItem
        >
        <NFormItem label="投递状态" :label-props="{ for: 'delivery-status' }"
          ><select
            id="delivery-status"
            v-model="status"
            class="native-select"
            :disabled="busy || confirm"
          >
            <option value="">全部状态</option>
            <option
              v-for="value in kind === 'automatic'
                ? ['pending', 'retry', 'leased', 'sent', 'failed', 'cancelled']
                : ['success', 'transient_error', 'permanent_error', 'unknown']"
              :key="value"
              :value="value"
            >
              {{ deliveryStatus(value) }}
            </option>
          </select></NFormItem
        >
      </div>
      <NButton attr-type="submit" :disabled="busy || confirm" :loading="loading"
        >筛选记录</NButton
      ></NForm
    >
    <div v-if="result" class="panel-heading">
      <p>符合筛选 {{ result.total }} 条</p>
      <div class="actions">
        <NButton :disabled="loading || busy || confirm || offset === 0" @click="page(-1)"
          >上一页</NButton
        ><NButton
          :disabled="loading || busy || confirm || offset + 20 >= result.total"
          @click="page(1)"
          >下一页</NButton
        >
      </div>
    </div>
    <p v-if="result && !result.items.length" class="empty">没有符合筛选的投递记录。</p>
    <NCard v-if="detail" title="投递详情" class="editor-card">
      <p class="post-text">{{ detail.title }}</p>
      <p>
        当时目标：{{ detail.target_name }} · {{ channelNames[detail.channel] }} · 配置版本
        {{ detail.target_revision }}
      </p>
      <p>
        记录 ID：<code>{{ detail.id }}</code>
      </p>
      <p>状态：{{ deliveryStatus(detail.status) }} · 尝试 {{ detail.attempt_count }} 次</p>
      <p v-if="detail.code">结果码：{{ detail.code }}</p>
      <p>
        开始：{{ localDate(detail.started_at)
        }}<template v-if="detail.kind !== 'automatic'">
          · 完成：{{ localDate(detail.finished_at) }}</template
        >
      </p>
      <p v-if="detail.next_attempt_at">下次自动尝试：{{ localDate(detail.next_attempt_at) }}</p>
      <p v-if="detail.lease_until">租约到期：{{ localDate(detail.lease_until) }}</p>
      <NAlert v-if="detail.uncertain" type="warning" class="notice"
        >曾出现结果未知，即使后续成功仍可能重复。未完成的显式发送不会自动重试。</NAlert
      >
      <p v-for="task in detail.matched_tasks" :key="task.id + ':' + task.version">
        {{ task.name }} · 规则版本 {{ task.version }}
      </p>
      <div v-for="attempt in detail.attempts" :key="attempt.sequence" class="history-item">
        <p>
          尝试 {{ attempt.sequence }}：{{ deliveryStatus(attempt.result) }} {{ attempt.code ?? '' }}
        </p>
        <p class="muted">
          {{ localDate(attempt.started_at) }} → {{ localDate(attempt.finished_at) }}
        </p>
        <p v-if="attempt.late_result">
          迟到结果：{{ deliveryStatus(attempt.late_result) }} ·
          {{ localDate(attempt.late_finished_at) }}
        </p>
      </div>
      <div class="actions">
        <a v-if="detail.url" :href="detail.url" target="_blank" rel="noopener noreferrer"
          >打开原帖</a
        ><NButton
          v-if="detail.original_event_id"
          :disabled="busy || confirm"
          @click="open({ id: detail.original_event_id!, kind: 'automatic' })"
          >查看原自动记录</NButton
        ><NButton
          v-if="detail.kind === 'automatic'"
          :disabled="
            busy ||
            loading ||
            confirm ||
            !['sent', 'failed', 'cancelled'].includes(detail.status) ||
            !detail.current_target.enabled
          "
          @click="prepareResend"
          >手动重发 {{ detail.current_target.name }}</NButton
        ><NButton :disabled="busy || confirm" @click="detail = null">收起详情</NButton>
      </div>
      <p v-if="detail.kind === 'automatic'" class="muted">
        仅已结束的自动投递可重发，当前目标须启用；正在等待或在途的消息继续由自动队列处理。手动重发不修改原记录。
      </p>
    </NCard>
    <SendConfirmation
      v-if="confirm && detail"
      :key="detail.id"
      :csrf="csrf"
      mode="manual"
      :resource-id="detail.id"
      :target="detail.current_target"
      :title="detail.title"
      @busy="busy = $event"
      @cancel="confirm = false"
      @done="
        (value) => {
          notice = explicitResultText(value)
          confirm = false
          detail = null
          kind = 'manual'
          status = ''
          offset = 0
          busy = false
          load()
        }
      "
    />
    <NCard v-for="record in result?.items" :key="record.id" class="record-card"
      ><h3 class="post-text">{{ record.title }}</h3>
      <div class="record-meta">
        <NTag>{{
          record.kind === 'automatic'
            ? '自动投递'
            : record.kind === 'manual'
              ? '手动重发'
              : '目标测试'
        }}</NTag
        ><NTag>{{ deliveryStatus(record.status) }}</NTag
        ><NTag v-if="record.uncertain" type="warning">结果不确定</NTag>
      </div>
      <p>
        {{ record.target_name }} · {{ channelNames[record.channel] }} · 配置版本
        {{ record.target_revision }}
      </p>
      <p class="muted">{{ localDate(record.started_at) }} · 尝试 {{ record.attempt_count }} 次</p>
      <p v-if="record.code">结果码：{{ record.code }}</p>
      <NButton :disabled="loading || busy || confirm" @click="open(record)"
        >查看详情</NButton
      ></NCard
    >
  </section>
</template>
