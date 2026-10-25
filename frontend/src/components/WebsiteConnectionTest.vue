<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { confirmAction, formatTime, getWebsiteTest, testWebsite } from '../store'
import type { ConnectionCheck } from '../shared'
import Icon from './Icon.vue'
import WebsiteConnectionResult from './WebsiteConnectionResult.vue'

const props = defineProps<{ websiteId: string; name: string }>()
const current = ref<ConnectionCheck | null>(null)
const previous = ref<ConnectionCheck | null>(null)
const testing = ref(false)
const loading = ref(true)
const historyError = ref('')
const testError = ref('')
const now = ref(Date.now() / 1000)
let active = true
let revision = 0
let timer: ReturnType<typeof setInterval> | undefined
const latest = computed(() => current.value || previous.value)
const waiting = computed(() => (latest.value?.next_attempt_at || 0) > now.value)
const time = (value: number) => formatTime(new Date(value * 1000).toISOString())
const status = (result: ConnectionCheck) =>
  ({ success: '成功', failure: '失败', deferred: '已延后', unknown: '未完成' })[result.status]

async function loadHistory() {
  const read = ++revision
  try {
    const result = await getWebsiteTest(props.websiteId)
    if (active && read === revision) previous.value = result
  } catch (error) {
    if (active && read === revision) historyError.value = (error as Error).message
  } finally {
    if (active && read === revision) loading.value = false
  }
}
async function runTest() {
  if (!active || testing.value) return
  ++revision
  if (current.value) previous.value = current.value
  current.value = null
  testing.value = true
  loading.value = false
  testError.value = ''
  historyError.value = ''
  try {
    const result = await testWebsite(props.websiteId)
    if (active) current.value = result
  } catch (error) {
    if (active) testError.value = (error as Error).message
  } finally {
    if (active) {
      testing.value = false
      now.value = Date.now() / 1000
    }
  }
}
function test() {
  if (testing.value) return
  confirmAction(
    '测试 ' + props.name + ' 官方 RSS 连接？',
    props.websiteId === 'linuxdo'
      ? '将请求一次官方 RSS，最多每分钟一次。可提前验证连接，仍遵守站点要求的等待时间；成功后将提前安排失败采集重试。不会启用网站、保存草稿或直接创建内容与通知。'
      : '将请求一次官方 RSS；测试独立限频，并遵守来源错误退避。不会启用网站、改变采集周期、保存草稿间隔或创建帖子、命中及通知。',
    runTest,
    '确认测试连接',
  )
}
onMounted(() => {
  loadHistory()
  timer = setInterval(() => (now.value = Date.now() / 1000), 1000)
})
onBeforeUnmount(() => {
  active = false
  clearInterval(timer)
})
</script>
<template>
  <section class="drawer-section website-connection-test" aria-label="连接测试">
    <div class="drawer-section-title">
      <h3>连接测试</h3>
      <span class="small-badge neutral">不采集入库</span>
    </div>
    <p v-if="websiteId === 'linuxdo'" class="field-help">
      每 60 秒最多测试一次，可提前验证自动退避中的连接；站点要求的等待时间仍生效。
      成功后将提前安排失败采集重试，不更改启停、采集间隔、历史或基线。
    </p>
    <p v-else class="field-help">
      仅检查官方 RSS 的连接与解析。测试有独立的 2
      秒防连点间隔，不改变后台采集周期、历史、基线和去重；来源错误退避仍生效。
    </p>
    <div class="website-test-row">
      <button class="button" :disabled="testing" @click="test">
        <Icon name="refresh" :size="16" :class="{ spinning: testing }" />{{
          testing ? '测试中…' : '测试连接'
        }}
      </button>
    </div>
    <p v-if="testing" class="small-note" role="status">正在检查 RSS 连接与解析…</p>
    <p v-else-if="testError" class="form-errors" role="alert">{{ testError }}</p>
    <WebsiteConnectionResult v-else-if="current" :result="current" />
    <p v-else class="small-note">
      {{ loading ? '正在读取上次测试记录…' : '本次尚未测试，点击“测试连接”检查当前连接。' }}
    </p>
    <p v-if="!testing && waiting && latest" class="small-note connection-cooldown">
      下次可测试时间：{{ time(latest.next_attempt_at) }}
    </p>
    <p v-if="historyError" class="small-note" role="alert">
      上次测试记录读取失败：{{ historyError }}。可点击“测试连接”检查当前连接。
    </p>
    <details v-if="!testing && !current && previous" class="connection-history">
      <summary>
        <span>上次测试 · {{ status(previous) }}</span>
        <span>{{ time(previous.started_at) }}</span>
      </summary>
      <p class="small-note">仅代表当时的检查结果，不代表当前连接状态。</p>
      <WebsiteConnectionResult :result="previous" historical />
    </details>
  </section>
</template>
<style scoped>
.connection-history {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 12px;
}
.connection-history summary {
  cursor: pointer;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
}
.connection-history summary span + span {
  margin-left: 12px;
}
.connection-history .match-result {
  margin-top: 8px;
}
</style>
