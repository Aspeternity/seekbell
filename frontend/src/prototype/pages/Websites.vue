<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import { state, notify, formatTime, confirmAction } from '../store'
const emit = defineEmits<{ dirty: [value: boolean] }>()
const draft = reactive({ interval: state.source.interval })
const baseline = ref(JSON.stringify(draft)),
  error = ref(''),
  testing = ref(false),
  scenario = ref('success')
const dirty = computed(() => JSON.stringify(draft) !== baseline.value)
watch(dirty, (value) => emit('dirty', value))
const testResult = ref('')
function save() {
  if (!Number.isInteger(draft.interval) || draft.interval < 10 || draft.interval > 3600) {
    error.value = '采集间隔应为 10–3600 之间的整数秒。'
    return
  }
  state.source.interval = draft.interval
  baseline.value = JSON.stringify(draft)
  error.value = ''
  notify('来源设置已保存在当前浏览器。')
}
function toggle(value: boolean) {
  const apply = () => {
    state.source.enabled = value
    notify(
      value ? '来源已在演示中恢复，将以当前条目重建基线。' : '来源已暂停，任务与历史配置保留。',
    )
  }
  if (value) apply()
  else
    confirmAction(
      '暂停 NodeSeek 采集？',
      '所有监控任务将暂停接收新帖。恢复时重建当下基线，不补发暂停期间的内容。',
      apply,
      '暂停来源',
    )
}
async function test() {
  testing.value = true
  testResult.value = ''
  await new Promise((resolve) => setTimeout(resolve, 450))
  state.source.lastTest = new Date().toISOString()
  state.source.health = scenario.value === 'success' ? 'healthy' : 'error'
  if (scenario.value === 'success') {
    state.source.lastSuccess = state.source.lastTest
    testResult.value = '模拟连接成功：RSS 格式有效，发现 20 条示例条目。'
  } else {
    testResult.value = '模拟连接失败：服务暂不可达。真实调度将退避重试，不会视为空 RSS。'
  }
  testing.value = false
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">ONE SOURCE, MANY POSSIBILITIES</p>
      <h1 tabindex="-1">监控网站</h1>
      <p class="subtitle">可靠地采集，安静地关注。</p>
    </div>
    <span class="small-badge neutral">1 个内置网站</span>
  </section>
  <div class="website-layout">
    <section class="panel website-main">
      <div class="website-brand">
        <div class="source-logo large">N<span>›</span></div>
        <div>
          <h2>NodeSeek</h2>
          <p>面向技术爱好者的交流社区</p>
          <span
            class="result-pill"
            :class="
              !state.source.enabled ? 'no' : state.source.health === 'healthy' ? 'yes' : 'unknown'
            "
            ><span class="status-dot" />{{
              !state.source.enabled
                ? '已暂停'
                : state.source.health === 'healthy'
                  ? '采集正常'
                  : '来源异常'
            }}</span
          >
        </div>
        <Toggle
          :model-value="state.source.enabled"
          label="NodeSeek 采集启用状态"
          @update:model-value="toggle"
        />
      </div>
      <div class="website-source">
        <Icon name="rss" :size="20" />
        <div>
          <strong>官方 RSS</strong>
          <p>https://rss.nodeseek.com/</p>
        </div>
        <span class="small-badge neutral">内置来源</span>
      </div>
      <div class="source-metrics">
        <div>
          <span>最近成功</span><strong>{{ formatTime(state.source.lastSuccess) }}</strong>
        </div>
        <div>
          <span>演示发现新帖</span><strong>286 <small>条</small></strong>
        </div>
        <div>
          <span>关联任务</span><strong>{{ state.tasks.length }} <small>个</small></strong>
        </div>
      </div>
      <div class="form-content">
        <h3 class="section-subtitle">采集设置</h3>
        <form @submit.prevent="save">
          <label class="field-label" for="source-interval">共享采集间隔</label>
          <div class="unit-input">
            <input
              id="source-interval"
              v-model.number="draft.interval"
              type="number"
              min="10"
              max="3600"
              step="1"
              class="text-input"
              required
            /><span>秒</span>
          </div>
          <p class="field-help">全部任务共享该频率。10 秒为候选默认值，不代表官方限频保证。</p>
          <div class="info-note">
            <Icon name="clock" :size="18" />
            <p>固定周期，不重叠请求。网络错误会退避重试；429 尊重服务端 Retry-After。</p>
          </div>
          <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
          <div class="inline-form-footer">
            <span>{{ dirty ? '有未保存的修改' : '设置已保存' }}</span
            ><button class="button primary" type="submit">保存设置</button>
          </div>
        </form>
      </div>
    </section>
    <aside class="side-stack">
      <section class="panel support-panel">
        <h2><Icon name="shield" :size="18" />来源能力</h2>
        <p>只使用 RSS 实际提供的信息。</p>
        <ul class="capability-list">
          <li
            v-for="name in ['新帖标题与摘要', '作者用户名', '版块信息', '稳定帖子标识']"
            :key="name"
          >
            <Icon name="check" :size="16" />{{ name }}
          </li>
        </ul>
        <div class="subtle-divider" />
        <p>不读取全文、回帖或网页；摘要可能缺失或截断。首次成功采集建立基线，不推送已有帖子。</p>
      </section>
      <section class="panel support-panel">
        <h2><Icon name="activity" :size="18" />连接测试</h2>
        <p>在本地切换结果，检查成功和异常状态的呈现。</p>
        <label class="field-label" for="source-scenario">模拟场景</label
        ><select id="source-scenario" v-model="scenario" class="text-input">
          <option value="success">RSS 连接成功</option>
          <option value="error">服务暂时不可用</option></select
        ><button class="button test-button" :disabled="testing" @click="test">
          <Icon name="refresh" :size="16" :class="{ spinning: testing }" />{{
            testing ? '测试中…' : '测试连接（模拟）'
          }}
        </button>
        <div
          v-if="testResult"
          class="match-result"
          :class="state.source.health === 'healthy' ? 'yes' : 'unknown'"
          role="status"
        >
          {{ testResult }}
        </div>
        <p class="small-note">
          最近测试：{{ formatTime(state.source.lastTest) }}<br />不会请求真实 RSS。
        </p>
      </section>
    </aside>
  </div>
</template>
