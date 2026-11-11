<script setup lang="ts">
import AppSelect from '../components/AppSelect.vue'
import TaskEvaluationCard from '../components/TaskEvaluationCard.vue'
import PostDiagnosis from '../components/PostDiagnosis.vue'
import { computed, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import { channelMeta } from '../store'
import { state, websiteName, formatTime } from '../store'
import { historyGet, useRemote, postLabels, deliveryLabels, resultClass } from '../history'
import type { Options, PostRecord, PostPage, Page, Evaluation, DeliveryRecord } from '../history'
import Pagination from '../components/Pagination.vue'
import DateFilter from '../components/DateFilter.vue'
import { dateRangeParams, type HistoryDateRange } from '../dateRange'
import ReadRegion from '../components/ReadRegion.vue'
import { untilShown } from '../viewReady'
import { shouldOpenContentRow } from '../contentRow'
const props = defineProps<{ selectedId?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const q = ref(''),
  status = ref('all'),
  task = ref(''),
  category = ref(''),
  dateRange = ref<HistoryDateRange>(null),
  website = ref(''),
  page = ref(1)
const showOther = ref(false)
const evaluationPage = ref(1),
  deliveryPage = ref(1)
watch(
  () => props.selectedId,
  () => {
    showOther.value = false
    evaluationPage.value = 1
    deliveryPage.value = 1
  },
  { flush: 'sync' },
)
const options = useRemote(
  () => historyGet<Options>('options'),
  () => [],
  { cacheKey: () => 'content:options' },
)
watch([q, status, task, category, dateRange, website], () => (page.value = 1), { flush: 'sync' })
const listing = useRemote(
  () =>
    props.selectedId
      ? Promise.resolve(undefined)
      : historyGet<PostPage>('posts', {
          q: q.value,
          status: status.value,
          task_id: task.value,
          category: category.value,
          ...dateRangeParams(dateRange.value),
          timezone: state.settings.timezone,
          website_id: website.value,
          page: page.value,
        }),
  () => [
    props.selectedId,
    q.value,
    status.value,
    task.value,
    category.value,
    dateRange.value,
    website.value,
    page.value,
    state.settings.timezone,
  ],
  {
    cacheKey: () =>
      props.selectedId
        ? undefined
        : JSON.stringify([
            'content:posts',
            q.value,
            status.value,
            task.value,
            category.value,
            dateRange.value,
            website.value,
            page.value,
            state.settings.timezone,
          ]),
    debounce: () => q.value,
    keepPrevious: true,
  },
)
const categoryOptions = computed(() =>
  (options.data.value?.category_options || []).filter(
    (item) => !website.value || item.website_id === website.value,
  ),
)
const detail = useRemote(
  () =>
    props.selectedId
      ? historyGet<PostRecord>('posts/' + props.selectedId)
      : Promise.resolve(undefined),
  () => props.selectedId,
  { cacheKey: () => (props.selectedId ? 'content:detail:' + props.selectedId : undefined) },
)
const evaluations = useRemote(
  () =>
    props.selectedId && detail.data.value?.status === 'match'
      ? historyGet<Page<Evaluation> & { other_total: number }>(
          'posts/' + props.selectedId + '/evaluations',
          {
            page: evaluationPage.value,
            group: 'matched',
          },
        )
      : Promise.resolve(undefined),
  () => [props.selectedId, detail.data.value?.status, evaluationPage.value],
  {
    cacheKey: () =>
      props.selectedId
        ? JSON.stringify(['content:evaluations', props.selectedId, 'matched', evaluationPage.value])
        : undefined,
  },
)
const deliveries = useRemote(
  () =>
    props.selectedId
      ? historyGet<Page<DeliveryRecord>>('deliveries', {
          post_id: props.selectedId,
          page: deliveryPage.value,
        })
      : Promise.resolve(undefined),
  () => [props.selectedId, deliveryPage.value],
  {
    cacheKey: () =>
      props.selectedId
        ? JSON.stringify(['content:deliveries', props.selectedId, deliveryPage.value])
        : undefined,
  },
)
const emptyMatchMessage = computed(() => {
  const record = detail.data.value
  if (record?.baseline === true) return '基线帖子：首次采集时登记，未执行规则匹配或生成通知。'
  switch (record?.status) {
    case 'no_match':
      return '该内容未命中任何任务。'
    case 'insufficient_data':
      return '信息不足，暂无法确定是否命中。'
    case 'not_evaluated':
      return '该内容未执行规则匹配。'
    case 'unrecorded':
      return '没有可确认的历史命中记录。'
    default:
      return '暂无可展示的命中依据，请刷新后重试。'
  }
})
// The four stages a post goes through, read from what was saved at the time.
const flow = computed(() => {
  const record = detail.data.value
  const sent = deliveries.data.value
  if (!record) return []
  const judged: Record<string, string> = {
    match: '命中 ' + record.hits.length + ' 个任务',
    no_match: '没有任务命中',
    insufficient_data: '信息不足，无法判定',
    not_evaluated: '未执行规则匹配',
    unrecorded: '旧版本未记录结果',
  }
  const total = sent?.total ?? 0
  const items = sent && total <= sent.page_size ? sent.items : null
  const count = (...states: string[]) =>
    items?.filter((item) => states.includes(item.status)).length ?? 0
  const delivered = count('sent'),
    failed = count('failed'),
    waiting = count('pending', 'retry', 'leased')
  return [
    {
      key: 'collect',
      icon: 'rss',
      label: '采集',
      tone: 'ok',
      value: time(record.first_seen_at),
      note: '来源发布 ' + (record.published_at === null ? '未记录' : time(record.published_at)),
    },
    {
      key: 'judge',
      icon: 'filter',
      label: '判定',
      tone: record.baseline ? 'none' : resultClass(record.status),
      value: record.baseline ? '基线帖子' : postLabels[record.status],
      note: record.baseline ? '首次采集时登记，不匹配' : judged[record.status],
    },
    {
      key: 'queue',
      icon: 'layers',
      label: '入队',
      tone: total ? 'yes' : 'neutral',
      value: !sent ? '—' : total ? total + ' 个目标' : '未入队',
      note: total
        ? '每个目标一条投递'
        : record.baseline
          ? '基线帖子不发送'
          : record.status === 'match'
            ? '没有投递记录'
            : '未命中，不发送',
    },
    {
      key: 'send',
      icon: 'send',
      label: '发送',
      tone: !total
        ? 'neutral'
        : !items
          ? 'neutral'
          : failed
            ? 'no'
            : waiting
              ? 'unknown'
              : delivered === total
                ? 'yes'
                : 'neutral',
      value: !total
        ? '—'
        : !items
          ? '见投递记录'
          : failed
            ? '失败 ' + failed
            : waiting
              ? '等待发送 ' + waiting
              : delivered === total
                ? '全部成功'
                : '成功 ' + delivered,
      note: items ? '成功 ' + delivered + ' / ' + total : total ? '共 ' + total + ' 条' : '',
    },
  ]
})
const time = (at: number | null) =>
  at === null ? '未记录' : formatTime(new Date(at * 1000).toISOString())
function openPost(id: string) {
  if (!window.getSelection()?.toString()) emit('navigate', '/operations/content/' + id)
}
function reloadListing() {
  options.reload()
  listing.reload()
}
function clear() {
  q.value = ''
  status.value = 'all'
  task.value = ''
  category.value = ''
  dateRange.value = null
  website.value = ''
}
await untilShown(() => options.ready() && listing.ready() && detail.ready() && deliveries.ready())
</script>
<template>
  <template v-if="selectedId">
    <button class="back-link" @click="emit('navigate', '/operations/content')">
      <Icon name="back" :size="17" />返回内容列表
    </button>
    <ReadRegion
      :loading="detail.loading.value"
      :error="detail.error.value"
      :has-data="!!detail.data.value"
      :stale="detail.stale.value"
      :min-height="360"
      @retry="detail.reload"
    >
      <template v-if="detail.data.value">
        <section class="page-heading">
          <div>
            <p class="eyebrow">A SIGNAL WORTH KEEPING</p>
            <h1 tabindex="-1" class="article-heading">{{ detail.data.value.title }}</h1>
            <p class="subtitle">
              {{ websiteName(detail.data.value.website_id) }} ·
              {{ detail.data.value.author || detail.data.value.author_display_name || '作者缺失' }}
              · {{ detail.data.value.category_label || detail.data.value.category || '版块缺失' }}
            </p>
          </div>
          <span class="result-pill" :class="resultClass(detail.data.value.status)">{{
            postLabels[detail.data.value.status]
          }}</span>
        </section>
        <section class="panel post-flow-panel" aria-label="处理过程">
          <ol class="post-flow">
            <li v-for="step in flow" :key="step.key" :class="'is-' + step.tone">
              <span class="post-flow-label"
                ><span class="about-tile-icon"><Icon :name="step.icon" :size="15" /></span
                >{{ step.label }}</span
              >
              <strong>{{ step.value }}</strong>
              <small v-if="step.note">{{ step.note }}</small>
            </li>
          </ol>
        </section>
        <div class="detail-layout">
          <div class="side-stack">
            <section class="panel reading-panel">
              <h2>RSS 内容快照</h2>
              <p class="article-summary">
                {{
                  detail.data.value.summary === null
                    ? '来源未提供摘要，无法据此推断完整内容。'
                    : detail.data.value.summary || '来源提供的摘要为空。'
                }}
              </p>
              <div class="info-note">
                <Icon name="help" :size="18" />
                <p>RSS 摘要不等同全文。这里保存首次读取时的内容，原帖之后的编辑不会改写它。</p>
              </div>
              <a
                v-if="detail.data.value.original_url"
                class="button original-post-link"
                :href="detail.data.value.original_url"
                target="_blank"
                rel="noopener noreferrer"
                >打开原帖 ↗</a
              >
              <p v-else class="small-note">没有可核验的原帖链接。</p>
            </section>
            <section class="panel">
              <div class="panel-heading">
                <h2>投递记录</h2>
                <span v-if="deliveries.data.value" class="count-badge">{{
                  deliveries.data.value.total
                }}</span>
              </div>
              <ReadRegion
                :loading="deliveries.loading.value"
                :error="deliveries.error.value"
                :has-data="!!deliveries.data.value"
                :stale="deliveries.stale.value"
                :min-height="160"
                @retry="deliveries.reload"
                ><template v-if="deliveries.data.value"
                  ><div
                    v-for="record in deliveries.data.value.items"
                    :key="record.id"
                    class="compact-record"
                  >
                    <span
                      class="icon-tile"
                      :class="channelMeta[record.kind as keyof typeof channelMeta]?.color || 'blue'"
                      ><Icon
                        :name="channelMeta[record.kind as keyof typeof channelMeta]?.icon || 'send'"
                        :size="18"
                    /></span>
                    <div>
                      <strong>{{ record.target_name }}</strong>
                      <p>{{ time(record.created_at) }} · 尝试 {{ record.attempt_count }} 次</p>
                      <small v-if="record.uncertain">曾有结果未知，可能重复</small>
                    </div>
                    <button
                      class="result-pill"
                      :class="resultClass(record.status)"
                      @click="emit('navigate', '/operations/deliveries/' + record.id)"
                    >
                      {{ deliveryLabels[record.status] }}<Icon name="arrow" :size="13" />
                    </button>
                  </div>
                  <p v-if="!deliveries.data.value.total" class="empty-state">
                    此帖子没有投递记录。
                  </p>
                  <Pagination
                    :page="deliveryPage"
                    :total="deliveries.data.value.total"
                    :page-size="deliveries.data.value.page_size"
                    label="关联投递"
                    @change="(value) => (deliveryPage = value)"
                  /> </template
              ></ReadRegion>
            </section>
          </div>
          <aside class="panel support-panel">
            <template v-if="detail.data.value.status === 'match' && !showOther">
              <h2><Icon name="filter" :size="18" />命中依据</h2>
              <p v-if="detail.data.value.baseline === null" class="info-note">
                旧版本可能未保存完整判定。只展示已留存证据，不按当前规则重算历史。
              </p>
              <ReadRegion
                :loading="evaluations.loading.value"
                :error="evaluations.error.value"
                :has-data="!!evaluations.data.value"
                :stale="evaluations.stale.value"
                :min-height="160"
                @retry="evaluations.reload"
                ><template v-if="evaluations.data.value">
                  <TaskEvaluationCard
                    v-for="evaluation in evaluations.data.value.items"
                    :key="evaluation.task_id + ':' + evaluation.version"
                    :evaluation="evaluation"
                    @navigate="emit('navigate', $event)"
                  />
                  <p v-if="!evaluations.data.value.total" class="small-note" role="status">
                    {{ emptyMatchMessage }}
                  </p>
                  <Pagination
                    v-if="evaluations.data.value.total > evaluations.data.value.page_size"
                    :page="evaluationPage"
                    :total="evaluations.data.value.total"
                    :page-size="evaluations.data.value.page_size"
                    label="命中任务判定"
                    @change="(value) => (evaluationPage = value)"
                  />
                </template>
              </ReadRegion>
              <p v-if="evaluations.data.value?.total" class="small-note">
                显示保存时的名称、版本与原因；修改或删除任务不重写已有记录。
              </p>
              <button
                v-if="evaluations.data.value?.other_total"
                type="button"
                class="text-link"
                @click="showOther = true"
              >
                查看其他任务判定（{{ evaluations.data.value.other_total }}）
              </button>
            </template>
            <PostDiagnosis
              v-else
              :key="detail.data.value.id"
              :post="detail.data.value"
              :preferred-task-id="task"
              :other="showOther"
              @back="showOther = false"
              @navigate="(path) => emit('navigate', path)"
            />
          </aside>
        </div> </template></ReadRegion
  ></template>
  <template v-else>
    <div
      class="metric-strip"
      :aria-busy="listing.loading.value"
      :aria-label="listing.stale.value ? '筛选更新中，当前显示上次结果' : undefined"
    >
      <div>
        <span>当前筛选内容</span
        ><strong :style="{ visibility: listing.data.value ? undefined : 'hidden' }">{{
          listing.data.value?.total ?? '—'
        }}</strong>
      </div>
      <div>
        <span>确定命中</span
        ><strong
          class="positive-text"
          :style="{ visibility: listing.data.value ? undefined : 'hidden' }"
          >{{ listing.data.value ? listing.data.value.summary.match || 0 : '—' }}</strong
        >
      </div>
      <div>
        <span>信息不足</span
        ><strong
          class="amber-text"
          :style="{ visibility: listing.data.value ? undefined : 'hidden' }"
          >{{
            listing.data.value ? listing.data.value.summary.insufficient_data || 0 : '—'
          }}</strong
        >
      </div>
    </div>
    <section class="panel">
      <div class="filter-toolbar content-filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="q"
            aria-label="搜索内容"
            placeholder="搜索标题、摘要或作者…"
            maxlength="200"
        /></label>
        <AppSelect
          v-model="status"
          class="content-result-filter"
          aria-label="匹配结果"
          :options="[
            { value: 'all', label: '全部匹配结果' },
            ...Object.entries(postLabels).map(([value, label]) => ({ value, label })),
          ]"
        />
        <AppSelect
          v-model="task"
          class="content-task-filter"
          aria-label="关联任务"
          :options="[
            { value: '', label: '全部任务' },
            ...(options.data.value?.tasks || []).map((item) => ({
              value: item.id,
              label: item.name + (item.deleted ? ' · 已删除' : ''),
            })),
          ]"
        />
        <AppSelect
          v-model="website"
          class="content-website-filter"
          aria-label="历史网站"
          :options="[
            { value: '', label: '全部网站' },
            ...(options.data.value?.websites || []).map((item) => ({
              value: item.id,
              label: item.name,
            })),
          ]"
        />
        <AppSelect
          v-model="category"
          class="content-category-filter"
          aria-label="版块筛选"
          :options="[
            { value: '', label: '全部版块' },
            ...categoryOptions.map((item) => ({
              value: item.value,
              label: item.label || '空版块',
            })),
          ]"
        />
        <DateFilter v-model="dateRange" label="发现日期" />
      </div>
      <p v-if="task" class="small-note content-filter-note">
        匹配结果按所选任务的历史判定筛选；详情可查看其他任务。
      </p>
      <p v-if="options.data.value?.truncated" class="small-note content-filter-note">
        筛选选项较多，仅列出前 200 项；可结合内容搜索定位。
      </p>
      <ReadRegion
        :loading="listing.loading.value || options.loading.value"
        :error="[listing.error.value, options.error.value].filter(Boolean).join('；')"
        :has-data="!!listing.data.value"
        :stale="listing.stale.value"
        @retry="reloadListing"
      >
        <template v-if="listing.data.value">
          <article
            v-for="post in listing.data.value.items"
            :key="post.id"
            class="content-row"
            @click="
              (event) => {
                if (shouldOpenContentRow(event)) emit('navigate', '/operations/content/' + post.id)
              }
            "
          >
            <div class="content-row-top">
              <span class="result-pill" :class="resultClass(post.status)">{{
                postLabels[post.status]
              }}</span>
              <button class="content-title" @click="openPost(post.id)">
                {{ post.title }}
              </button>
              <time
                class="muted"
                :datetime="new Date((post.published_at ?? post.first_seen_at) * 1000).toISOString()"
                :title="
                  '首次发现：' +
                  time(post.first_seen_at) +
                  (post.published_at === null ? '；来源未提供发布时间' : '')
                "
                >{{ post.published_at === null ? '发现' : '发布' }}
                {{ time(post.published_at ?? post.first_seen_at) }}</time
              >
            </div>
            <p class="content-excerpt">
              {{ post.summary === null ? '来源未提供摘要' : post.summary || '摘要为空' }}
            </p>
            <div class="content-row-meta">
              <span
                ><Icon name="user" :size="13" />{{
                  post.author || post.author_display_name || '作者缺失'
                }}</span
              ><span>{{ post.category_label || post.category || '版块缺失' }}</span>
              <span
                v-for="hit in post.hits"
                :key="hit.task_id + ':' + hit.version"
                class="plain-chip"
                >{{ hit.name }} · v{{ hit.version }}{{ hit.deleted ? ' · 已删除' : '' }}</span
              >
            </div>
          </article>
          <div v-if="!listing.data.value.total" class="empty-state">
            <Icon name="search" :size="30" />
            <h3>没有符合条件的内容</h3>
            <p>
              当前没有已保存的记录，或筛选条件未匹配。请检查网站启停状态与运行状态中的采集结果。
            </p>
            <button class="button" @click="clear">清除筛选</button>
          </div>
          <Pagination
            :page="listing.data.value.page"
            :total="listing.data.value.total"
            :page-size="listing.data.value.page_size"
            label="内容"
            @change="(value) => (page = value)"
          />
        </template>
      </ReadRegion></section
  ></template>
</template>

<style scoped>
.content-row {
  padding: 16px 22px;
  cursor: pointer;
  transition: background 0.15s;
}
.content-row-top {
  gap: 10px;
  margin-bottom: 4px;
}
.content-row-top > .result-pill {
  flex: none;
}
.content-title {
  display: block;
  flex: 1;
  width: auto;
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.content-row-top > time {
  flex: none;
  margin-left: 0;
  font-variant-numeric: tabular-nums;
}
.content-excerpt {
  margin: 0 0 8px;
  line-height: 1.7;
  -webkit-line-clamp: 1;
}
.metric-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 16px;
  padding: 18px 0;
}
.metric-strip > div {
  min-width: 0;
}
.metric-strip > div:last-child {
  border-right: 0;
}
.post-flow-panel {
  margin-bottom: 20px;
  padding: 16px;
}
.post-flow {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 26px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.post-flow li {
  position: relative;
  display: grid;
  align-content: start;
  gap: 6px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8f9fb;
}
.post-flow li + li::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -17px;
  width: 7px;
  height: 7px;
  border-top: 1.5px solid #c3c9d1;
  border-right: 1.5px solid #c3c9d1;
  transform: translateY(-50%) rotate(45deg);
}
.post-flow-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #808b98;
  font-size: 12px;
}
.post-flow-label .about-tile-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
}
.post-flow strong {
  font-size: 14px;
  font-weight: 550;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.post-flow small {
  color: var(--muted);
  font-size: 12px;
}
.post-flow .is-yes strong {
  color: #2f6f4f;
}
.post-flow .is-no strong {
  color: #a8324a;
}
.post-flow .is-unknown strong {
  color: #8a5a0b;
}
.post-flow .is-neutral strong,
.post-flow .is-none strong {
  color: #6f7885;
}
@media (prefers-reduced-motion: reduce) {
  .content-row {
    transition: none;
  }
}
@media (max-width: 1100px) {
  .post-flow {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .post-flow li + li::before {
    display: none;
  }
}
.content-row:hover,
.content-row:focus-within {
  background: #fafbfc;
}
.original-post-link {
  margin-top: 16px;
}
.content-filter-note {
  margin: 0;
  padding: 12px 22px;
}
@media (max-width: 760px) {
  .content-filter-note {
    padding: 12px 16px;
  }
  .content-row {
    padding: 14px 16px;
  }
  .content-row-top {
    flex-wrap: wrap;
  }
  .content-title {
    flex-basis: 100%;
    order: 3;
    white-space: normal;
  }
  .content-row-top > time {
    margin-left: auto;
  }
  .metric-strip {
    padding: 14px 0;
  }
  .metric-strip > div {
    padding: 0 14px;
  }
}
</style>
