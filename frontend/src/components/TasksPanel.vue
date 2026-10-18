<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  NTag,
} from 'naive-ui'
import RuleEditor from './RuleEditor.vue'
import {
  freshRule,
  getTargets,
  getTasks,
  matchLabels,
  message,
  reasonText,
  write,
} from '../management'
import type { HistoryPreview, MonitorTask, Preview, Target } from '../management'

const props = defineProps<{ csrf: string }>()
const emit = defineEmits<{ targets: [] }>()
const tasks = ref<MonitorTask[]>([])
const targets = ref<Target[]>([])
const loading = ref(false)
const busy = ref(false)
const formOpen = ref(false)
const editing = ref<MonitorTask | null>(null)
const name = ref('')
const enabled = ref(true)
const targetIds = ref<string[]>([])
const rule = ref(freshRule())
const preview = ref<Preview | null>(null)
const history = ref<HistoryPreview | null>(null)
const error = ref('')
const notice = ref('')
const title = ref('')
const summary = ref('')
const summaryPresent = ref(false)
const author = ref('')
const category = ref('')
const historyLimit = ref<number | null>(20)

const allNew = computed(
  () =>
    ![
      ...rule.value.exclude,
      ...rule.value.authors_include,
      ...rule.value.authors_exclude,
      ...rule.value.categories,
      ...rule.value.groups.flatMap((g) => [...g.all_of, ...g.any_of]),
    ].some((value) => value.trim()),
)
watch(
  rule,
  () => {
    preview.value = null
    history.value = null
  },
  { deep: true },
)

watch([title, summary, summaryPresent, author, category], () => {
  if (preview.value?.result) preview.value = null
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[tasks.value, targets.value] = await Promise.all([getTasks(), getTargets()])
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
function start(task: MonitorTask | null = null, copy = false) {
  editing.value = copy ? null : task
  name.value = task ? (copy ? task.name.slice(0, 190) + ' 副本' : task.name) : ''
  enabled.value = copy ? false : (task?.enabled ?? true)
  rule.value = task ? JSON.parse(JSON.stringify(task.rule)) : freshRule()
  targetIds.value = task ? [...task.target_ids] : []
  title.value = summary.value = author.value = category.value = ''
  summaryPresent.value = false
  preview.value = null
  history.value = null
  error.value = notice.value = ''
  formOpen.value = true
}
function cancel() {
  formOpen.value = false
  editing.value = null
  rule.value = freshRule()
}
async function save() {
  busy.value = true
  error.value = notice.value = ''
  try {
    const body = { name: name.value, rule: rule.value, target_ids: targetIds.value }
    if (editing.value) {
      await write(
        '/tasks/' + editing.value.id,
        'PUT',
        { ...body, expected_version: editing.value.version },
        props.csrf,
      )
    } else {
      await write('/tasks', 'POST', { ...body, enabled: enabled.value }, props.csrf)
    }
    cancel()
    tasks.value = await getTasks()
    notice.value = '监控任务已保存；规则变更只影响之后首次发现的帖子。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function toggle(task: MonitorTask) {
  busy.value = true
  error.value = notice.value = ''
  try {
    await write('/tasks/' + task.id + '/enabled', 'PUT', { enabled: !task.enabled }, props.csrf)
    tasks.value = await getTasks()
    notice.value = '任务状态已更新。暂停撤销尚未发送的贡献；恢复不补发已见帖子。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function remove(task: MonitorTask) {
  if (!window.confirm('删除此任务并取消其尚未发送的贡献？已有命中历史仍会保留。')) return
  busy.value = true
  error.value = notice.value = ''
  try {
    await write('/tasks/' + task.id, 'DELETE', undefined, props.csrf)
    tasks.value = await getTasks()
    notice.value = '任务已删除，历史版本保留。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function trial(sample: boolean) {
  busy.value = true
  error.value = ''
  try {
    preview.value = await write<Preview>(
      '/rules/preview',
      'POST',
      {
        rule: rule.value,
        ...(sample
          ? {
              sample: {
                title: title.value,
                summary: summaryPresent.value ? summary.value : null,
                author: author.value || null,
                category: category.value || null,
              },
            }
          : {}),
      },
      props.csrf,
    )
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function trialHistory() {
  busy.value = true
  error.value = ''
  try {
    history.value = await write<HistoryPreview>(
      '/rules/history',
      'POST',
      {
        rule: rule.value,
        limit: historyLimit.value ?? 20,
      },
      props.csrf,
    )
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
function date(value: number | null): string {
  return value === null ? '无样本' : new Date(value * 1000).toLocaleString()
}
onMounted(load)
</script>

<template>
  <section aria-label="监控任务管理" :aria-busy="loading || busy">
    <div class="panel-heading">
      <h2>监控任务</h2>
      <div class="actions">
        <NButton :loading="loading" :disabled="busy" @click="load">刷新任务</NButton>
        <NButton type="primary" :disabled="busy || loading || !targets.length" @click="start()"
          >新建监控任务</NButton
        >
      </div>
    </div>
    <p class="muted">首版仅 NodeSeek 官方 RSS，匹配标题、摘要、作者与版块。无全文与回帖采集。</p>
    <NAlert v-if="error" type="error" role="alert" class="notice">{{ error }}</NAlert>
    <NAlert v-if="notice" type="success" role="status" class="notice">{{ notice }}</NAlert>
    <NAlert v-if="!loading && !targets.length" type="info" class="notice">
      请先创建通知目标，再为任务选择接收端。<NButton text type="primary" @click="emit('targets')"
        >前往通知目标</NButton
      >
    </NAlert>
    <NCard v-if="formOpen" :title="editing ? '编辑监控任务' : '新建监控任务'" class="editor-card">
      <NForm @submit.prevent="save">
        <NFormItem label="任务名称" :label-props="{ for: 'task-name' }"
          ><NInput
            v-model:value="name"
            :disabled="busy"
            :maxlength="200"
            :input-props="{ id: 'task-name', required: true }"
        /></NFormItem>
        <fieldset class="target-choices" :disabled="busy">
          <legend>通知目标</legend>
          <NCheckbox
            v-for="target in targets"
            :key="target.id"
            :checked="targetIds.includes(target.id)"
            :disabled="busy"
            @update:checked="
              (value) =>
                (targetIds = value
                  ? [...targetIds, target.id]
                  : targetIds.filter((id) => id !== target.id))
            "
          >
            {{ target.name }}{{ target.enabled ? '' : '（已停用）' }}
          </NCheckbox>
        </fieldset>
        <NFormItem v-if="!editing" label="启用任务"
          ><NSwitch v-model:value="enabled" :disabled="busy" aria-label="启用任务"
        /></NFormItem>
        <RuleEditor v-model="rule" :disabled="busy" />
        <NAlert v-if="allNew" type="warning" class="notice"
          >当前没有筛选限制，将匹配全部新帖。</NAlert
        >
        <div class="actions">
          <NButton :disabled="busy" @click="trial(false)">校验并解释规则</NButton>
          <NButton type="primary" attr-type="submit" :loading="busy" :disabled="!targetIds.length"
            >保存监控任务</NButton
          >
          <NButton :disabled="busy" @click="cancel">取消编辑</NButton>
        </div>
      </NForm>
      <p v-if="preview" class="rule-explanation">{{ preview.explanation }}</p>

      <section class="trial-section" aria-label="规则试匹配">
        <h3>模拟试匹配</h3>
        <p class="muted">
          使用当前未保存的规则，不发送通知，不修改已见或已发状态。摘要缺失与已知空摘要分别处理。
        </p>
        <div class="form-grid">
          <NFormItem label="模拟标题" :label-props="{ for: 'sample-title' }"
            ><NInput
              v-model:value="title"
              :disabled="busy"
              :maxlength="8192"
              :input-props="{ id: 'sample-title' }"
          /></NFormItem>
          <NFormItem label="摘要已知"
            ><NSwitch v-model:value="summaryPresent" :disabled="busy" aria-label="摘要已知"
          /></NFormItem>
          <NFormItem v-if="summaryPresent" label="模拟摘要" :label-props="{ for: 'sample-summary' }"
            ><NInput
              v-model:value="summary"
              type="textarea"
              :disabled="busy"
              :maxlength="65536"
              :input-props="{ id: 'sample-summary' }"
          /></NFormItem>
          <NFormItem label="模拟作者" :label-props="{ for: 'sample-author' }"
            ><NInput
              v-model:value="author"
              :disabled="busy"
              :maxlength="500"
              :input-props="{ id: 'sample-author' }"
          /></NFormItem>
          <NFormItem label="模拟版块" :label-props="{ for: 'sample-category' }"
            ><NInput
              v-model:value="category"
              :disabled="busy"
              :maxlength="500"
              :input-props="{ id: 'sample-category' }"
          /></NFormItem>
        </div>
        <NButton :disabled="busy" @click="trial(true)">模拟试匹配</NButton>
        <NAlert
          v-if="preview?.result"
          :type="
            preview.result.status === 'match'
              ? 'success'
              : preview.result.status === 'insufficient_data'
                ? 'warning'
                : 'info'
          "
          role="status"
          class="notice"
          :title="matchLabels[preview.result.status]"
          >{{ reasonText(preview.result) }}</NAlert
        >

        <h3>本地历史试匹配</h3>
        <p class="muted">
          只读取本地已保存帖子，按首次发现时间选取最近样本。不会访问论坛，也不补发通知。
        </p>
        <NFormItem label="最多取样条数"
          ><NInputNumber
            v-model:value="historyLimit"
            :disabled="busy"
            :min="1"
            :max="100"
            :precision="0"
            aria-label="最多取样条数"
        /></NFormItem>
        <NButton :disabled="busy" @click="trialHistory">本地历史试匹配</NButton>
        <div v-if="history" aria-live="polite" class="history-results">
          <p>本次样本 {{ history.sample_count }} 条 / 本地共 {{ history.total }} 条</p>
          <p class="muted">
            样本时间：{{ date(history.oldest_at) }} — {{ date(history.newest_at) }}
          </p>
          <div v-for="item in history.items" :key="item.external_post_id" class="history-item">
            <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{
              item.title
            }}</a>
            <p v-else>{{ item.title }}</p>
            <NTag>{{ matchLabels[item.result.status] }}</NTag>
            <p>{{ reasonText(item.result) }}</p>
          </div>
        </div>
      </section>
    </NCard>

    <p v-if="!loading && !tasks.length" class="empty">还没有监控任务。</p>
    <NCard v-for="task in tasks" :key="task.id" :title="task.name" class="record-card">
      <NTag :type="task.enabled ? 'success' : 'default'">{{
        task.enabled ? '已启用' : '已暂停'
      }}</NTag>
      <p class="rule-explanation">{{ task.explanation }}</p>
      <p class="muted">
        NodeSeek · 规则版本 {{ task.version }} · {{ task.target_ids.length }} 个通知目标
      </p>
      <div class="actions">
        <NButton :disabled="busy || formOpen" @click="start(task)">编辑 {{ task.name }}</NButton>
        <NButton :disabled="busy || formOpen" @click="start(task, true)"
          >复制 {{ task.name }}</NButton
        >
        <NButton :disabled="busy || formOpen" @click="toggle(task)"
          >{{ task.enabled ? '暂停' : '恢复' }} {{ task.name }}</NButton
        >
        <NButton :disabled="busy || formOpen" type="error" secondary @click="remove(task)"
          >删除 {{ task.name }}</NButton
        >
      </div>
    </NCard>
  </section>
</template>
