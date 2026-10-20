<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import Toggle from './components/Toggle.vue'
import TagInput from './components/TagInput.vue'
import { evaluate, historySamples, statusLabel } from './model'
import type { Sample, Task } from './model'
import { state, websiteName, isLive, evaluateTask, trialHistory, formatTime } from '@workspace'
const targets = computed(() => state.targets)
const props = withDefaults(
  defineProps<{ task: Task; returnLabel?: string; saving?: boolean; saveError?: string }>(),
  {
    returnLabel: '返回概览',
  },
)
const emit = defineEmits<{
  save: [task: Task]
  cancel: []
  navigate: [path: string]
  dirty: [value: boolean]
}>()
const draft = reactive<Task>(JSON.parse(JSON.stringify(props.task)))
const baseline = JSON.stringify(draft)
const errors = ref<string[]>([])
const testing = ref(false),
  testError = ref('')
const testMode = ref('manual')
const testResult = ref<ReturnType<typeof evaluate> | null>(null)
const historyResults = ref<{ sample: Sample; result: ReturnType<typeof evaluate> }[] | null>(null)
const sample = reactive(
  isLive
    ? { title: '', summary: '', author: '', category: '' }
    : { ...historySamples[0]!, summary: historySamples[0]!.summary || '' },
)
const historyLimit = ref(20)
const historyMeta = ref<Awaited<ReturnType<typeof trialHistory>> | null>(null)
const missingSummary = ref(false)
const section = ref('basic')
const unrestricted = computed(
  () =>
    !draft.groups.some((g) => g.all.length || g.any.length) &&
    !draft.exclude.length &&
    !draft.categories.length &&
    !draft.authorsInclude.length &&
    !draft.authorsExclude.length,
)
const summary = computed(() => {
  const groups = draft.groups
    .filter((group) => group.all.length || group.any.length)
    .map((group) =>
      [
        group.all.length ? '包含「' + group.all.join('」「') + '」' : '',
        group.any.length ? '含「' + group.any.join(' / ') + '」中的任意一个' : '',
      ]
        .filter(Boolean)
        .join('，且'),
    )
  return groups.length ? groups.join('；或者，') : '不限制关键词'
})
watch(
  draft,
  () => {
    emit('dirty', JSON.stringify(draft) !== baseline)
    testResult.value = null
    historyResults.value = null
    historyMeta.value = null
  },
  { deep: true },
)
watch(
  [sample, missingSummary],
  () => {
    testResult.value = null
  },
  { deep: true },
)
function clearHistory() {
  historyResults.value = null
  historyMeta.value = null
}
function save() {
  if (props.saving) return
  errors.value = []
  if (!state.websites.some((w) => w.id === draft.websiteId))
    errors.value.push('请选择已添加的监控网站。')
  if (!draft.name.trim()) errors.value.push('请填写任务名称。')
  if (!draft.targets.length) errors.value.push('请至少选择一个通知目标。')
  if (draft.targets.some((id) => !state.targets.some((t) => t.id === id)))
    errors.value.push('通知目标已删除，请重新选择。')
  if (errors.value.length) {
    nextTick(() => document.querySelector<HTMLElement>('[data-form-errors]')?.focus())
    return
  }
  emit('save', JSON.parse(JSON.stringify(draft)))
}
function toggleCategory(category: string) {
  draft.categories = draft.categories.includes(category)
    ? draft.categories.filter((c) => c !== category)
    : [...draft.categories, category]
}
async function runTest() {
  if (testing.value) return
  testing.value = true
  testError.value = ''
  const snapshot = JSON.stringify({
    draft,
    sample,
    missingSummary: missingSummary.value,
    testMode: testMode.value,
    historyLimit: historyLimit.value,
  })
  try {
    const task = JSON.parse(JSON.stringify(draft))
    if (testMode.value === 'manual') {
      const result = await evaluateTask(task, {
        ...sample,
        summary: missingSummary.value ? null : sample.summary,
        author: sample.author || null,
        category: sample.category || null,
      })
      if (
        snapshot ===
        JSON.stringify({
          draft,
          sample,
          missingSummary: missingSummary.value,
          testMode: testMode.value,
          historyLimit: historyLimit.value,
        })
      )
        testResult.value = result
    } else {
      const batch = await trialHistory(task, historyLimit.value)
      const results = batch.items
      if (
        snapshot ===
        JSON.stringify({
          draft,
          sample,
          missingSummary: missingSummary.value,
          testMode: testMode.value,
          historyLimit: historyLimit.value,
        })
      ) {
        historyResults.value = results
        historyMeta.value = batch
      }
    }
  } catch (e) {
    testError.value = (e as Error).message
  } finally {
    testing.value = false
  }
}
function jump(id: string) {
  section.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>
<template>
  <div class="editor-heading">
    <button class="back-link" @click="emit('cancel')">
      <Icon name="back" :size="17" />{{ returnLabel }}
    </button>
    <div class="page-heading">
      <div>
        <div class="editor-title-line">
          <h1 tabindex="-1">{{ draft.id ? '编辑监控任务' : '新建监控任务' }}</h1>
          <span class="small-badge neutral">{{ websiteName(draft.websiteId) }}</span>
        </div>
        <p class="subtitle">告诉 SeekBell，你想留意什么。</p>
      </div>
      <span class="autosave-note"
        ><span class="status-dot" />{{
          JSON.stringify(draft) === baseline
            ? isLive
              ? '配置保存到服务端'
              : '仅使用模拟数据'
            : '有未保存的修改'
        }}</span
      >
    </div>
  </div>
  <nav class="editor-sections" aria-label="编辑页章节">
    <button
      v-for="(item, i) in [
        { id: 'basic', name: '基本信息' },
        { id: 'rules', name: '匹配规则' },
        { id: 'delivery', name: '通知目标' },
      ]"
      :key="item.id"
      :class="{ active: section === item.id }"
      @click="jump(item.id)"
    >
      <span>{{ String(i + 1).padStart(2, '0') }}</span
      >{{ item.name }}</button
    ><button class="test-jump" @click="jump('test-panel')">
      <Icon name="play" :size="14" />试匹配
    </button>
  </nav>
  <p v-if="saveError" class="form-errors" role="alert">{{ saveError }}</p>
  <div v-if="errors.length" data-form-errors class="form-errors" tabindex="-1" role="alert">
    <Icon name="alert" :size="20" />
    <div>
      <strong>还差一点，请检查以下内容</strong>
      <p v-for="error in errors" :key="error">{{ error }}</p>
    </div>
  </div>
  <form class="editor-layout" @submit.prevent="save">
    <div class="editor-fields">
      <section id="basic" class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">01</span>
          <div>
            <h2>基本信息</h2>
            <p>一个任务，专注一件在意的事</p>
          </div>
          <div class="enabled-field">
            <span>{{ draft.enabled ? '启用任务' : '暂停任务' }}</span
            ><Toggle v-model="draft.enabled" label="启用任务" />
          </div>
        </div>
        <div class="form-content">
          <label class="field-label" for="task-name">任务名称 <span class="required">*</span></label
          ><input
            id="task-name"
            v-model="draft.name"
            class="text-input"
            placeholder="例如：好价服务器雷达"
            maxlength="80"
            :aria-invalid="errors.length > 0 && !draft.name.trim()"
          />
          <div class="field-help">
            <span>用一个好记的名字，区分你的关注。</span><span>{{ draft.name.length }}/80</span>
          </div>
          <label class="field-label" for="task-description"
            >备注 <span class="optional">选填</span></label
          ><input
            id="task-description"
            v-model="draft.description"
            class="text-input"
            placeholder="这项任务想关注什么？"
            maxlength="160"
          />
          <label class="field-label" for="task-website">监控网站</label>
          <select
            id="task-website"
            v-model="draft.websiteId"
            class="text-input"
            :disabled="!!draft.id"
          >
            <option v-for="w in state.websites" :key="w.id" :value="w.id">
              {{ websiteName(w.id) }}{{ w.enabled ? '' : ' · 已暂停' }}
            </option>
          </select>
          <p class="field-help">
            {{
              draft.id
                ? '任务所属网站固定；如需更换，请创建新任务，避免混用历史记录。'
                : '只显示已添加的网站。采集频率在网站配置中统一设置。'
            }}
          </p>
          <p
            v-if="!state.websites.find((w) => w.id === draft.websiteId)?.enabled"
            class="warning-note"
          >
            {{
              isLive
                ? '网站已暂停，可以保存任务；启用网站后才会采集新帖。'
                : '该网站已暂停。任务可以保存，启用网站后才会采集新帖。'
            }}
          </p>
        </div>
      </section>
      <section id="rules" class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">02</span>
          <div>
            <h2>匹配规则</h2>
            <p>留下相关的，滤掉无关的</p>
          </div>
          <Icon name="filter" :size="19" />
        </div>
        <div class="form-content">
          <fieldset class="plain-fieldset">
            <legend class="field-label">匹配范围</legend>
            <div class="scope-options">
              <label
                v-for="scope in [
                  { value: 'title', name: '仅标题', detail: '信号更聚焦' },
                  { value: 'summary', name: '仅摘要', detail: '关注补充信息' },
                  { value: 'title_summary', name: '标题 + 摘要', detail: '覆盖更多线索' },
                ]"
                :key="scope.value"
                :class="{ selected: draft.scope === scope.value }"
                ><input v-model="draft.scope" type="radio" name="scope" :value="scope.value" /><span
                  ><strong>{{ scope.name }}</strong
                  ><small>{{ scope.detail }}</small></span
                ></label
              >
            </div>
            <p class="field-help">摘要可能缺失或被截断，规则不会读取全文。</p>
          </fieldset>
          <div class="label-row">
            <label class="field-label">关键词条件</label
            ><span class="micro-label">任意一组满足即可命中 <span class="logic-tag">OR</span></span>
          </div>
          <template v-for="(group, index) in draft.groups" :key="index"
            ><div v-if="index" class="or-divider"><span>或者</span></div>
            <div class="condition-group">
              <div class="group-heading">
                <strong
                  ><span class="group-dot" />条件组 {{ String(index + 1).padStart(2, '0') }}</strong
                ><span>组内同时满足 <b>AND</b></span
                ><button
                  v-if="draft.groups.length > 1"
                  class="icon-button"
                  type="button"
                  :aria-label="'删除条件组 ' + (index + 1)"
                  @click="draft.groups.splice(index, 1)"
                >
                  <Icon name="close" :size="15" />
                </button>
              </div>
              <label class="field-label">全部包含 <span class="optional">每个词都出现</span></label
              ><TagInput v-model="group.all" :label="'条件组' + (index + 1) + '全部包含'" /><label
                class="field-label"
                >至少包含一个 <span class="optional">出现任意一个词</span></label
              ><TagInput
                v-model="group.any"
                :label="'条件组' + (index + 1) + '至少包含一个'"
              /></div
          ></template>
          <button
            class="add-group"
            type="button"
            :disabled="draft.groups.length >= 16"
            @click="draft.groups.push({ all: [], any: [] })"
          >
            <Icon name="plus" :size="16" />添加条件组<span>满足更多种情况</span>
          </button>
          <p class="field-help">
            按回车或英文逗号添加关键词；短语中的空格会保留。空条件组不参与判断。
          </p>
          <div class="form-divider" />
          <label class="field-label"
            >排除关键词 <span class="small-badge rose">优先排除</span></label
          ><TagInput
            v-model="draft.exclude"
            label="排除关键词"
            tone="exclude-tags"
            placeholder="例如：求购、已出（逐个添加）"
          />
          <p class="field-help">匹配范围内出现任意排除词，即使满足条件组也不会命中。</p>
          <fieldset class="plain-fieldset">
            <legend class="field-label">版块范围</legend>
            <div class="category-options">
              <button
                type="button"
                :class="{ selected: !draft.categories.length }"
                @click="draft.categories = []"
              >
                全部版块</button
              ><button
                v-for="category in ['优惠', '技术', '测评', '交易', '日常']"
                :key="category"
                type="button"
                :aria-pressed="draft.categories.includes(category)"
                :class="{ selected: draft.categories.includes(category) }"
                @click="toggleCategory(category)"
              >
                {{ category }}
              </button>
            </div>
            <p class="field-help">
              {{
                isLive
                  ? '按RSS提供的版块名称精确匹配；没有可靠版块时建议不限制。'
                  : '演示版块；正式版使用来源提供的版块名称。'
              }}
            </p>
          </fieldset>
          <details class="advanced">
            <summary>
              <span><Icon name="settings" :size="16" />更多匹配设置</span
              ><span>作者 · 大小写 · 整词<Icon name="down" :size="14" /></span>
            </summary>
            <div class="advanced-content">
              <label class="field-label">仅包含这些作者</label
              ><TagInput
                v-model="draft.authorsInclude"
                label="包含作者"
                placeholder="输入精确用户名"
              /><label class="field-label">排除这些作者</label
              ><TagInput
                v-model="draft.authorsExclude"
                label="排除作者"
                placeholder="输入精确用户名"
              />
              <p class="field-help">按原帖用户名精确匹配；区分大小写，改名后不保证继续跟踪。</p>
              <div class="setting-row">
                <div>
                  <strong>区分英文大小写</strong><small>开启后，DMIT 与 dmit 视为不同关键词</small>
                </div>
                <Toggle v-model="draft.caseSensitive" label="区分英文大小写" />
              </div>
              <div class="setting-row">
                <div>
                  <strong>英文整词匹配</strong
                  ><small>例如 VPS 不会匹配到 myVPS；中文仍按包含匹配</small>
                </div>
                <Toggle v-model="draft.wholeWord" label="英文整词匹配" />
              </div>
            </div>
          </details>
          <div v-if="unrestricted" class="warning-note" role="status">
            <Icon name="alert" :size="18" />未设置筛选条件，此任务将匹配全部新帖。
          </div>
        </div>
      </section>
      <section id="delivery" class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">03</span>
          <div>
            <h2>通知目标 <span class="required">*</span></h2>
            <p>发现好消息时，在哪里告诉你？</p>
          </div>
          <span class="small-badge neutral">已选 {{ draft.targets.length }}</span>
        </div>
        <div class="form-content">
          <p v-if="!targets.length" class="warning-note">请先添加一个通知目标。</p>
          <button
            v-if="!targets.length"
            type="button"
            class="button"
            @click="emit('navigate', '/target/new')"
          >
            添加通知目标
          </button>
          <div class="target-options">
            <label
              v-for="target in targets"
              :key="target.id"
              :class="{ selected: draft.targets.includes(target.id) }"
              ><span class="icon-tile" :class="target.color"
                ><Icon :name="target.icon" :size="19" /></span
              ><span class="target-copy"
                ><strong>{{ target.name }}</strong
                ><small>{{ target.type }}</small></span
              ><input v-model="draft.targets" type="checkbox" :value="target.id"
            /></label>
          </div>
          <p class="field-help">
            <Icon name="help" :size="14" />同一帖子命中多个任务时，同一目标合并为一条通知。
          </p>
        </div>
      </section>
    </div>
    <aside class="editor-preview">
      <section class="panel rule-summary">
        <div class="preview-heading">
          <span class="icon-tile orange small-tile"><Icon name="spark" :size="18" /></span>
          <h2>这条规则，会做什么？</h2>
          <span class="live-label">实时</span>
        </div>
        <p>
          当 <strong>{{ websiteName(draft.websiteId) }}</strong> 出现新帖，
        </p>
        <div class="summary-quote">{{ summary }}。</div>
        <p v-if="draft.exclude.length">
          同时排除 <strong>{{ draft.exclude.join('、') }}</strong
          >。
        </p>
        <p v-if="draft.categories.length">
          限定版块：<strong>{{ draft.categories.join('、') }}</strong
          >。
        </p>
        <p v-if="draft.authorsInclude.length">
          仅限作者：<strong>{{ draft.authorsInclude.join('、') }}</strong
          >。
        </p>
        <p v-if="draft.authorsExclude.length">
          排除作者：<strong>{{ draft.authorsExclude.join('、') }}</strong
          >。
        </p>
        <div class="summary-delivery">
          <Icon name="arrow" :size="16" /><span>{{
            draft.targets.length
              ? '通过 ' +
                targets
                  .filter((t) => draft.targets.includes(t.id))
                  .map((t) => t.type)
                  .join('、') +
                ' 通知你'
              : '等待选择通知目标'
          }}</span>
        </div>
        <div class="summary-foot"><Icon name="clock" :size="15" />保存后仅对之后发现的新帖生效</div>
      </section>
      <section id="test-panel" class="panel test-panel">
        <div class="panel-heading">
          <h2><Icon name="play" :size="16" />先试试看</h2>
          <span class="small-badge neutral">不发通知</span>
        </div>
        <div class="segmented test-tabs">
          <button
            type="button"
            :class="{ active: testMode === 'manual' }"
            :aria-pressed="testMode === 'manual'"
            @click="testMode = 'manual'"
          >
            模拟输入</button
          ><button
            type="button"
            :class="{ active: testMode === 'history' }"
            :aria-pressed="testMode === 'history'"
            @click="testMode = 'history'"
          >
            历史样本
          </button>
        </div>
        <div v-if="testMode === 'manual'" class="sample-form">
          <label class="field-label" for="sample-title">帖子标题</label
          ><textarea id="sample-title" v-model="sample.title" rows="3" maxlength="500" /><label
            class="field-label"
            for="sample-summary"
            >帖子摘要</label
          ><textarea
            id="sample-summary"
            v-model="sample.summary"
            rows="2"
            :disabled="missingSummary"
            maxlength="2000"
            placeholder="可留空，与缺失字段不同"
          /><label class="check-label"
            ><input v-model="missingSummary" type="checkbox" />模拟摘要字段缺失</label
          >
          <div class="sample-extra">
            <label
              >作者<input
                v-model="sample.author"
                class="text-input"
                aria-label="样本作者"
                placeholder="缺失" /></label
            ><label
              >版块<input
                v-model="sample.category"
                class="text-input"
                aria-label="样本版块"
                placeholder="缺失"
            /></label>
          </div>
        </div>
        <div v-else-if="isLive" class="history-intro">
          <strong>本地已保存帖子</strong>
          <p>使用当前草稿，按首次发现时间选取最近样本（含基线）。不会联网补齐历史。</p>
          <label class="field-label" for="history-limit">最多试算条数</label>
          <select
            id="history-limit"
            v-model="historyLimit"
            :disabled="testing"
            @change="clearHistory"
          >
            <option :value="20">20 条</option>
            <option :value="50">50 条</option>
            <option :value="100">100 条</option>
          </select>
        </div>
        <div v-else class="history-intro">
          <span class="icon-tile purple"><Icon name="inbox" /></span
          ><strong>5 条合成历史样本</strong>
          <p>2026/10/19 · 09:00–14:30<br />包含命中、排除与字段缺失场景。</p>
        </div>
        <p v-if="testError" class="form-errors" role="alert">{{ testError }}</p>
        <button type="button" class="button test-button" :disabled="testing" @click="runTest">
          <Icon name="play" :size="15" />{{
            testMode === 'manual' ? '试匹配这条帖子' : isLive ? '试匹配本地历史' : '试匹配 5 条样本'
          }}
        </button>
        <div
          v-if="testMode === 'manual' && testResult"
          class="match-result"
          :class="testResult.status"
          role="status"
        >
          <strong
            ><Icon
              :name="
                testResult.status === 'yes'
                  ? 'check'
                  : testResult.status === 'unknown'
                    ? 'alert'
                    : 'close'
              "
              :size="17"
            />{{ statusLabel[testResult.status] }}</strong
          >
          <p v-for="reason in testResult.reasons" :key="reason">{{ reason }}</p>
        </div>
        <div v-if="testMode === 'history' && historyResults" class="history-results" role="status">
          <div class="history-result-summary">
            命中 {{ historyResults.filter((r) => r.result.status === 'yes').length }} /
            {{ historyResults.length }} 条
          </div>
          <p v-if="isLive && historyMeta">
            本地共 {{ historyMeta.available }} 条；本次 {{ historyMeta.sampleCount }} 条。
            <template v-if="historyMeta.sampleCount"
              >首次发现时间：{{ formatTime(historyMeta.fromAt) }}–{{
                formatTime(historyMeta.toAt)
              }}。</template
            >
            <template v-else>暂无本地历史样本。</template>
          </p>
          <article v-for="(item, i) in historyResults" :key="i">
            <div>
              <span class="result-pill" :class="item.result.status">{{
                statusLabel[item.result.status]
              }}</span
              ><strong>{{ item.sample.title }}</strong>
            </div>
            <p>{{ item.result.reasons.join('；') }}</p>
          </article>
        </div>
        <p class="test-footnote">
          {{
            isLive
              ? '由服务端规则引擎试算，不发送通知、不改变历史。'
              : '仅在本地试算，不发送通知、不改变历史。正式接入后由后端统一判断。'
          }}
        </p>
      </section>
      <div class="editor-tip">
        <Icon name="shield" :size="18" />
        <p>只关注新帖。修改规则不会触发历史补发，也不会改变已有投递记录。</p>
      </div>
    </aside>
    <div class="save-bar">
      <div>
        <span class="status-dot" /><span
          >{{ draft.enabled ? '保存后任务为启用状态' : '保存后任务保持暂停'
          }}<small>{{
            isLive ? '保存到服务端；后台按网站启停状态运行' : '仅保存在当前浏览器'
          }}</small></span
        >
      </div>
      <div class="save-actions">
        <button class="button" type="button" @click="emit('cancel')">取消</button
        ><button class="button primary" type="submit" :disabled="saving">
          <Icon name="check" :size="17" />保存任务
        </button>
      </div>
    </div>
  </form>
</template>
