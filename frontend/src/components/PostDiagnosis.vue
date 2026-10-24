<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'
import ReadRegion from './ReadRegion.vue'
import EvaluationPicker from './EvaluationPicker.vue'
import ResultDialog from './ResultDialog.vue'
import TaskEvaluationCard from './TaskEvaluationCard.vue'
import { historyGet, useRemote, postLabels, resultClass } from '../history'
import type { PostRecord } from '../history'
import type {
  CurrentRuleTrial,
  DiagnosisDetail,
  EvaluationOption,
  EvaluationOptions,
} from '../diagnosis'
import { request } from '../store'
const props = withDefaults(
  defineProps<{ post: PostRecord; preferredTaskId?: string; other?: boolean }>(),
  { preferredTaskId: '', other: false },
)
const emit = defineEmits<{ navigate: [path: string]; back: [] }>()
const scopeLabels: Record<string, string> = {
  title: '仅标题',
  summary: '仅摘要',
  title_summary: '标题与摘要',
}
const query = ref(''),
  page = ref(1),
  selected = ref<EvaluationOption | null>(null),
  showDetails = ref(false)
const trial = ref<CurrentRuleTrial | null>(null),
  trialBusy = ref(false),
  trialError = ref('')
let trialGeneration = 0
const hasRecordedState = computed(
  () => !props.post.baseline && !['not_evaluated', 'unrecorded'].includes(props.post.status),
)
const title = computed(() =>
  props.other
    ? '其他任务判定'
    : props.post.baseline || props.post.status === 'not_evaluated'
      ? '未参与匹配'
      : props.post.status === 'insufficient_data'
        ? '判定信息不足'
        : props.post.status === 'unrecorded'
          ? '暂无判定记录'
          : '未命中原因',
)
watch(query, () => (page.value = 1), { flush: 'sync' })
const options = useRemote(
  () =>
    hasRecordedState.value
      ? historyGet<EvaluationOptions>('posts/' + props.post.id + '/evaluation-options', {
          group: 'other',
          q: query.value,
          page: page.value,
          page_size: 20,
          preferred_task_id: props.preferredTaskId,
        })
      : Promise.resolve(undefined),
  () => [props.post.id, hasRecordedState.value, query.value, page.value, props.preferredTaskId],
  {
    cacheKey: () =>
      JSON.stringify([
        'diagnosis:options',
        props.post.id,
        query.value,
        page.value,
        props.preferredTaskId,
      ]),
    debounce: () => query.value,
    keepPrevious: true,
    scope: () => props.post.id,
  },
)
watch(options.data, (value) => {
  if (!selected.value && value?.preferred) selected.value = value.preferred
})
const detail = useRemote(
  () =>
    selected.value
      ? historyGet<DiagnosisDetail>(
          'posts/' +
            props.post.id +
            '/evaluations/' +
            encodeURIComponent(selected.value.task_id) +
            '/' +
            selected.value.version,
        )
      : Promise.resolve(undefined),
  () => [props.post.id, selected.value?.key],
  {
    cacheKey: () =>
      selected.value
        ? JSON.stringify(['diagnosis:detail', props.post.id, selected.value.key])
        : undefined,
  },
)
watch(
  () => selected.value?.key,
  () => {
    showDetails.value = false
    trial.value = null
    trialError.value = ''
    trialBusy.value = false
    ++trialGeneration
  },
  { flush: 'sync' },
)
const pickerOptions = computed(() =>
  (options.data.value?.items || []).map((item) => ({
    value: item.key,
    label: item.name + ' · v' + item.version + (item.deleted ? ' · 已删除' : ''),
    status: postLabels[item.status],
  })),
)
const otherCount = computed(() =>
  options.data.value
    ? options.data.value.recorded_total - (options.data.value.counts.match || 0)
    : 0,
)
function choose(key: string) {
  const item = options.data.value?.items.find((item) => item.key === key)
  if (item) selected.value = item
}
async function tryCurrent() {
  if (!selected.value || trialBusy.value) return
  const generation = ++trialGeneration
  trialBusy.value = true
  trialError.value = ''
  try {
    const result = await request<CurrentRuleTrial>(
      'manage/history/posts/' + props.post.id + '/current-rule-trial',
      'POST',
      { task_id: selected.value.task_id },
    )
    if (generation === trialGeneration) trial.value = result
  } catch (error) {
    if (generation === trialGeneration) trialError.value = (error as Error).message
  } finally {
    if (generation === trialGeneration) trialBusy.value = false
  }
}
onBeforeUnmount(() => ++trialGeneration)
</script>
<template>
  <div class="post-diagnosis">
    <div class="diagnosis-title">
      <h2><Icon name="filter" :size="18" />{{ title }}</h2>
      <button v-if="other" type="button" class="text-link" @click="emit('back')">
        返回命中依据
      </button>
    </div>
    <p v-if="post.baseline" class="small-note">
      首次采集基线：只登记帖子，未执行规则匹配或生成通知。
    </p>
    <p v-else-if="post.status === 'not_evaluated'" class="small-note">
      当时没有执行规则匹配，未保存可用于解释的任务判定。
    </p>
    <p v-else-if="post.status === 'unrecorded'" class="small-note">
      没有保存当时的任务判定，无法还原原因；不会用当前规则替代历史结果。
    </p>
    <template v-else>
      <ReadRegion
        :loading="options.loading.value"
        :error="options.error.value"
        :has-data="!!options.data.value"
        :stale="options.stale.value"
        :min-height="110"
        allow-controls
        @retry="options.reload"
      >
        <template v-if="options.data.value">
          <p class="small-note diagnosis-counts">
            当时判定：未命中 {{ options.data.value.counts.no_match || 0 }} · 信息不足
            {{ options.data.value.counts.insufficient_data || 0 }}
          </p>
          <div data-read-control>
            <EvaluationPicker
              v-if="otherCount > 1"
              :model-value="selected?.key || ''"
              :label="selected ? selected.name + ' · v' + selected.version : ''"
              :options="pickerOptions"
              :loading="options.loading.value"
              :error="options.error.value"
              :page="page"
              :total="options.data.value.total"
              @choose="choose"
              @search="query = $event"
              @page="page = $event"
              @retry="options.reload"
            />
          </div>
          <p v-if="!otherCount" class="small-note">
            没有留存该帖子的未命中判定，无法确认具体原因。
          </p>
        </template>
      </ReadRegion>
      <ReadRegion
        v-if="selected"
        :loading="detail.loading.value"
        :error="detail.error.value"
        :has-data="!!detail.data.value"
        :stale="detail.stale.value"
        :min-height="200"
        @retry="detail.reload"
      >
        <template v-if="detail.data.value">
          <div class="diagnosis-task">
            <strong>{{ detail.data.value.name }}</strong>
            <span class="small-note"
              >当时配置 v{{ detail.data.value.version
              }}{{ detail.data.value.deleted ? ' · 任务已删除' : '' }}</span
            >
          </div>
          <div class="diagnosis-cause">
            <strong>{{ detail.data.value.explanation.headline }}</strong>
            <span v-if="detail.data.value.explanation.blockers.length > 1" class="small-note"
              >另有
              {{ detail.data.value.explanation.blockers.length - 1 }}
              项条件未通过，详见完整条件。</span
            >
          </div>
          <div class="diagnosis-checks">
            <p v-for="check in detail.data.value.explanation.checks" :key="check.code">
              <Icon
                :name="
                  check.state === 'passed' ? 'check' : check.state === 'blocked' ? 'close' : 'help'
                "
                :size="13"
              />
              <span>{{ check.label }}</span>
              <strong :class="check.state">{{
                check.state === 'passed'
                  ? '通过'
                  : check.state === 'blocked'
                    ? '未通过'
                    : '信息不足'
              }}</strong>
            </p>
          </div>
          <div
            v-if="
              detail.data.value.category.expected.length &&
              detail.data.value.explanation.checks.some(
                (check) => check.code === 'category' && check.state === 'blocked',
              )
            "
            class="diagnosis-values"
          >
            <p>
              规则要求：{{
                detail.data.value.category.expected.map((item) => item.label).join('、')
              }}
            </p>
            <p>帖子实际：{{ detail.data.value.category.label || '来源未提供' }}</p>
            <p v-if="detail.data.value.category.legacy_mismatch">
              历史保存值：{{
                detail.data.value.category.expected.map((item) => item.value).join('、')
              }}； 来源标识：{{ detail.data.value.category.actual }}。
            </p>
          </div>
          <div class="diagnosis-actions">
            <button type="button" class="text-link" @click="showDetails = true">
              查看完整条件
            </button>
            <button
              v-if="!detail.data.value.deleted"
              type="button"
              class="text-link"
              @click="emit('navigate', '/task/' + detail.data.value.task_id)"
            >
              编辑任务
            </button>
          </div>
          <button
            v-if="!detail.data.value.deleted"
            type="button"
            class="button diagnosis-trial"
            :disabled="trialBusy"
            @click="tryCurrent"
          >
            {{ trialBusy ? '正在试算…' : '用当前规则试算' }}
          </button>
          <p v-if="trialError" class="inline-error" role="alert">{{ trialError }}</p>
          <div v-if="trial" class="diagnosis-current" role="status">
            <strong>当前规则试算 · v{{ trial.version }}</strong>
            <span
              v-if="trial.result"
              class="result-pill"
              :class="resultClass(trial.result.status)"
              >{{ postLabels[trial.result.status] }}</span
            >
            <p>{{ trial.explanation?.headline || trial.message }}</p>
            <p class="small-note">仅使用当前已保存规则试算，不修改历史，不发送通知。</p>
          </div>
          <p class="small-note diagnosis-footnote">
            以上为当时保存的判定，修改任务不会改写这些记录。
          </p>
        </template>
      </ReadRegion>
    </template>
    <ResultDialog
      v-if="showDetails && detail.data.value"
      title="完整匹配条件"
      @close="showDetails = false"
    >
      <p class="small-note">历史判定 · 使用当时保存的任务配置。</p>
      <TaskEvaluationCard :evaluation="detail.data.value" @navigate="emit('navigate', $event)" />
      <div v-if="detail.data.value.rule" class="diagnosis-values">
        <p>匹配范围：{{ scopeLabels[detail.data.value.rule.scope] }}</p>
        <p v-if="detail.data.value.category.expected.length">
          规则版块值：{{ detail.data.value.category.expected.map((item) => item.value).join('、') }}
        </p>
        <p>
          帖子版块：{{ detail.data.value.category.label || '未提供'
          }}{{ detail.data.value.category.actual ? ' · ' + detail.data.value.category.actual : '' }}
        </p>
        <p v-if="detail.data.value.rule.authors_include.length">
          包含作者：{{ detail.data.value.rule.authors_include.join('、') }}
        </p>
        <p v-if="detail.data.value.rule.authors_exclude.length">
          排除作者：{{ detail.data.value.rule.authors_exclude.join('、') }}
        </p>
        <p
          v-if="
            detail.data.value.rule.authors_include.length ||
            detail.data.value.rule.authors_exclude.length
          "
        >
          帖子作者：{{ detail.data.value.author || '未提供' }}
        </p>
      </div>
    </ResultDialog>
  </div>
</template>
<style scoped>
.diagnosis-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.diagnosis-title h2 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.diagnosis-counts {
  margin: 12px 0;
}
.diagnosis-task {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 16px 0 12px;
  overflow-wrap: anywhere;
}
.diagnosis-task .small-note {
  margin: 0;
}
.diagnosis-cause {
  padding: 12px;
  border-radius: 7px;
  background: #faf6f1;
  color: #8f633f;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.diagnosis-cause > strong {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.post-diagnosis .diagnosis-values p {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.diagnosis-cause .small-note {
  display: block;
  margin: 5px 0 0;
}
.diagnosis-checks {
  padding: 8px 0;
}
.diagnosis-checks p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 9px 0;
  font-size: 12px;
}
.diagnosis-checks strong {
  margin-left: auto;
  font-weight: 500;
  color: #75818d;
}
.diagnosis-checks .passed {
  color: #58856d;
}
.diagnosis-checks .blocked {
  color: #a5724e;
}
.diagnosis-values {
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.diagnosis-values p {
  margin: 4px 0;
}
.diagnosis-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin: 16px 0;
}
.diagnosis-trial {
  width: 100%;
}
.diagnosis-current {
  padding: 12px;
  margin-top: 14px;
  border: 1px solid #e4e8ec;
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.8;
}
.diagnosis-current .result-pill {
  margin-left: 8px;
}
.diagnosis-footnote {
  font-size: 10px;
}
</style>
