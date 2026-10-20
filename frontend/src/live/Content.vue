<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import { state, websiteName, formatTime } from './store'
import {
  historyGet,
  useRemote,
  postLabels,
  deliveryLabels,
  resultClass,
  reasonText,
} from './history'
import type { Options, PostRecord, PostPage, Page, Evaluation, DeliveryRecord } from './history'
import Pagination from './Pagination.vue'
import Feedback from './Feedback.vue'
const props = defineProps<{ selectedId?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const q = ref(''),
  status = ref('all'),
  task = ref(''),
  category = ref(''),
  day = ref(''),
  website = ref(''),
  page = ref(1)
const evaluationPage = ref(1),
  deliveryPage = ref(1)
const options = useRemote(
  () => historyGet<Options>('options'),
  () => [],
)
watch([q, status, task, category, day, website], () => (page.value = 1), { flush: 'sync' })
const listing = useRemote(
  () =>
    props.selectedId
      ? Promise.resolve(undefined)
      : historyGet<PostPage>('posts', {
          q: q.value,
          status: status.value,
          task_id: task.value,
          category: category.value,
          discovered_on: day.value,
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
    day.value,
    website.value,
    page.value,
  ],
)
const detail = useRemote(
  () =>
    props.selectedId
      ? historyGet<PostRecord>('posts/' + props.selectedId)
      : Promise.resolve(undefined),
  () => props.selectedId,
)
const evaluations = useRemote(
  () =>
    props.selectedId
      ? historyGet<Page<Evaluation>>('posts/' + props.selectedId + '/evaluations', {
          page: evaluationPage.value,
        })
      : Promise.resolve(undefined),
  () => [props.selectedId, evaluationPage.value],
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
)
const time = (at: number | null) =>
  at === null ? '未记录' : formatTime(new Date(at * 1000).toISOString())
function clear() {
  q.value = ''
  status.value = 'all'
  task.value = ''
  category.value = ''
  day.value = ''
  website.value = ''
}
</script>
<template>
  <template v-if="selectedId">
    <button class="back-link" @click="emit('navigate', '/content')">
      <Icon name="back" :size="17" />返回内容列表
    </button>
    <Feedback :loading="detail.loading.value" :error="detail.error.value" @retry="detail.reload" />
    <template v-if="detail.data.value">
      <section class="page-heading">
        <div>
          <p class="eyebrow">A SIGNAL WORTH KEEPING</p>
          <h1 tabindex="-1" class="article-heading">{{ detail.data.value.title }}</h1>
          <p class="subtitle">
            {{ websiteName(detail.data.value.website_id) }} ·
            {{ detail.data.value.author || '作者缺失' }} ·
            {{ detail.data.value.category || '版块缺失' }} · 首次发现
            {{ time(detail.data.value.first_seen_at) }}
          </p>
        </div>
        <span class="result-pill" :class="resultClass(detail.data.value.status)">{{
          postLabels[detail.data.value.status]
        }}</span>
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
            <p class="small-note">RSS 摘要不等同全文。首次发现与来源发布时间分别记录。</p>
            <p class="small-note">来源发布时间：{{ time(detail.data.value.published_at) }}</p>
            <a
              v-if="detail.data.value.original_url"
              class="button"
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
            <Feedback
              :loading="deliveries.loading.value"
              :error="deliveries.error.value"
              @retry="deliveries.reload"
            />
            <template v-if="deliveries.data.value"
              ><div
                v-for="record in deliveries.data.value.items"
                :key="record.id"
                class="compact-record"
              >
                <span class="icon-tile blue"><Icon name="send" :size="18" /></span>
                <div>
                  <strong>{{ record.target_name }}</strong>
                  <p>{{ time(record.created_at) }} · 尝试 {{ record.attempt_count }} 次</p>
                  <small v-if="record.uncertain">曾有结果未知，可能重复</small>
                </div>
                <button
                  class="result-pill"
                  :class="resultClass(record.status)"
                  @click="emit('navigate', '/notifications/deliveries/' + record.id)"
                >
                  {{ deliveryLabels[record.status] }}<Icon name="arrow" :size="13" />
                </button>
              </div>
              <p v-if="!deliveries.data.value.total" class="empty-state">此帖子没有投递记录。</p>
              <Pagination
                :page="deliveryPage"
                :total="deliveries.data.value.total"
                :page-size="deliveries.data.value.page_size"
                label="关联投递"
                @change="(value) => (deliveryPage = value)"
              />
            </template>
          </section>
        </div>
        <aside class="panel support-panel">
          <h2><Icon name="filter" :size="18" />当时的规则判定</h2>
          <p v-if="detail.data.value.baseline === true" class="info-note">
            基线帖子：首次采集时登记，未执行规则匹配或生成通知。
          </p>
          <p v-else-if="detail.data.value.baseline === null" class="info-note">
            旧版本可能未保存完整判定。只展示已留存证据，不按当前规则重算历史。
          </p>
          <p v-else-if="detail.data.value.status === 'not_evaluated'" class="info-note">
            没有留存的任务判定。不会按当前规则补写历史。
          </p>
          <Feedback
            :loading="evaluations.loading.value"
            :error="evaluations.error.value"
            @retry="evaluations.reload"
          />
          <template v-if="evaluations.data.value">
            <article
              v-for="evaluation in evaluations.data.value.items"
              :key="evaluation.task_id + ':' + evaluation.version"
              class="snapshot-task history-evaluation"
            >
              <div>
                <button
                  v-if="!evaluation.deleted"
                  class="text-link"
                  @click="emit('navigate', '/task/' + evaluation.task_id)"
                >
                  {{ evaluation.name }}</button
                ><strong v-else>{{ evaluation.name }} · 已删除</strong>
                <p class="small-note">版本 {{ evaluation.version }} · {{ time(evaluation.at) }}</p>
                <span class="result-pill" :class="resultClass(evaluation.result.status)">{{
                  postLabels[evaluation.result.status]
                }}</span>
                <p v-for="(reason, i) in evaluation.result.reasons" :key="i" class="small-note">
                  {{ reasonText(reason) }}
                </p>
                <p v-if="!evaluation.result.reasons.length" class="small-note">
                  未设置筛选条件，或旧记录未留下原因。
                </p>
              </div>
            </article>
            <p v-if="!evaluations.data.value.total" class="small-note">没有可展示的任务判定。</p>
            <Pagination
              :page="evaluationPage"
              :total="evaluations.data.value.total"
              :page-size="evaluations.data.value.page_size"
              label="任务判定"
              @change="(value) => (evaluationPage = value)"
            />
          </template>
          <p class="small-note">显示保存时的名称、版本与原因；修改或删除任务不重写已有记录。</p>
        </aside>
      </div>
    </template></template
  >
  <template v-else>
    <section class="page-heading">
      <div>
        <p class="eyebrow">FROM THE FEED, TO YOUR FOCUS</p>
        <h1 tabindex="-1">内容与命中</h1>
        <p class="subtitle">留住发现的线索，也看清每一次匹配。</p>
      </div>
      <span class="small-badge neutral">服务端历史</span>
    </section>
    <div v-if="listing.data.value" class="metric-strip">
      <div>
        <span>当前筛选内容</span><strong>{{ listing.data.value.total }}</strong>
      </div>
      <div>
        <span>确定命中</span
        ><strong class="positive-text">{{ listing.data.value.summary.match || 0 }}</strong>
      </div>
      <div>
        <span>信息不足</span
        ><strong class="amber-text">{{ listing.data.value.summary.insufficient_data || 0 }}</strong>
      </div>
      <p>时间显示：{{ state.settings.timezone }}</p>
    </div>
    <section class="panel">
      <div class="filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="q"
            aria-label="搜索内容"
            placeholder="搜索标题、摘要或作者…"
            maxlength="200"
        /></label>
        <select v-model="status" aria-label="匹配结果">
          <option value="all">全部匹配结果</option>
          <option v-for="(label, key) in postLabels" :key="key" :value="key">{{ label }}</option>
        </select>
        <select v-model="task" aria-label="关联任务">
          <option value="">全部任务</option>
          <option v-for="item in options.data.value?.tasks || []" :key="item.id" :value="item.id">
            {{ item.name }}{{ item.deleted ? ' · 已删除' : '' }}
          </option>
        </select>
        <select v-model="website" aria-label="历史网站">
          <option value="">全部网站</option>
          <option
            v-for="item in options.data.value?.websites || []"
            :key="item.id"
            :value="item.id"
          >
            {{ item.name }}
          </option>
        </select>
        <select v-model="category" aria-label="版块筛选">
          <option value="">全部版块</option>
          <option v-for="name in options.data.value?.categories || []" :key="name" :value="name">
            {{ name || '空版块' }}
          </option>
        </select>
        <label class="check-label"
          >发现日期<input v-model="day" type="date" aria-label="发现日期"
        /></label>
      </div>
      <Feedback
        :loading="options.loading.value"
        :error="options.error.value"
        @retry="options.reload"
      />
      <p v-if="task" class="small-note">匹配结果按所选任务的历史判定筛选；详情可查看其他任务。</p>
      <p v-if="options.data.value?.truncated" class="small-note">
        筛选选项较多，仅列出前 200 项；可结合内容搜索定位。
      </p>
      <Feedback
        :loading="listing.loading.value"
        :error="listing.error.value"
        @retry="listing.reload"
      />
      <template v-if="listing.data.value">
        <article v-for="post in listing.data.value.items" :key="post.id" class="content-row">
          <div class="content-row-top">
            <span class="result-pill" :class="resultClass(post.status)">{{
              postLabels[post.status]
            }}</span
            ><span class="muted">{{ time(post.first_seen_at) }}</span>
          </div>
          <button class="content-title" @click="emit('navigate', '/content/' + post.id)">
            {{ post.title }}<Icon name="arrow" :size="17" />
          </button>
          <p class="content-excerpt">
            {{ post.summary === null ? '来源未提供摘要' : post.summary || '摘要为空' }}
          </p>
          <div class="content-row-meta">
            <span><Icon name="user" :size="13" />{{ post.author || '作者缺失' }}</span
            ><span>{{ post.category || '版块缺失' }}</span>
            <span v-for="hit in post.hits" :key="hit.task_id + ':' + hit.version" class="plain-chip"
              >{{ hit.name }} · v{{ hit.version }}{{ hit.deleted ? ' · 已删除' : '' }}</span
            >
          </div>
        </article>
        <div v-if="!listing.data.value.total" class="empty-state">
          <Icon name="search" :size="30" />
          <h3>没有符合条件的内容</h3>
          <p>当前没有已保存的记录，或筛选条件未匹配。采集调度尚未接入。</p>
          <button class="button" @click="clear">清除筛选</button>
        </div>
        <Pagination
          :page="page"
          :total="listing.data.value.total"
          :page-size="listing.data.value.page_size"
          label="内容"
          @change="(value) => (page = value)"
        />
      </template></section
  ></template>
</template>
