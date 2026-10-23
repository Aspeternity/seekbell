<script setup lang="ts">
import AppSelect from '../components/AppSelect.vue'
import { computed, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import { state, formatTime, channelMeta } from '../store'
import {
  historyGet,
  useRemote,
  deliveryLabels,
  resultLabels,
  kindLabels,
  resultClass,
} from '../history'
import type {
  Page,
  Options,
  DeliveryRecord,
  DeliveryDetail,
  TestRecord,
  ManualRecord,
} from '../history'
import Pagination from '../components/Pagination.vue'
import SendDialog from '../components/SendDialog.vue'
import DateFilter from '../components/DateFilter.vue'
import { dateRangeParams, type HistoryDateRange } from '../dateRange'
import ReadRegion from '../components/ReadRegion.vue'
const props = withDefaults(defineProps<{ tab?: string; recordId?: string }>(), {
  tab: 'deliveries',
})
const emit = defineEmits<{ navigate: [path: string] }>()
const q = ref(''),
  status = ref('all'),
  target = ref(''),
  dateRange = ref<HistoryDateRange>(null),
  uncertain = ref('all'),
  page = ref(1)
const resendOpen = ref(false)
const attemptPage = ref(1),
  taskPage = ref(1)
watch([q, status, target, dateRange, uncertain], () => (page.value = 1), { flush: 'sync' })
const options = useRemote(
  () => historyGet<Options>('options'),
  () => [],
  { cacheKey: () => 'content:options' },
)
const listing = useRemote<Page<DeliveryRecord> | Page<TestRecord> | Page<ManualRecord> | undefined>(
  () =>
    props.recordId
      ? Promise.resolve(undefined)
      : props.tab !== 'deliveries'
        ? historyGet<Page<TestRecord> | Page<ManualRecord>>(props.tab, {
            q: q.value,
            status: status.value,
            target_id: target.value,
            ...dateRangeParams(dateRange.value),
            timezone: state.settings.timezone,
            page: page.value,
          })
        : historyGet<Page<DeliveryRecord>>('deliveries', {
            q: q.value,
            status: status.value,
            target_id: target.value,
            ...dateRangeParams(dateRange.value),
            timezone: state.settings.timezone,
            page: page.value,
            uncertain: uncertain.value === 'all' ? undefined : uncertain.value === 'true',
          }),
  () => [
    props.recordId,
    props.tab,
    q.value,
    status.value,
    target.value,
    dateRange.value,
    uncertain.value,
    page.value,
    state.settings.timezone,
  ],
  {
    cacheKey: () =>
      props.recordId
        ? undefined
        : JSON.stringify([
            'records',
            props.tab,
            q.value,
            status.value,
            target.value,
            dateRange.value,
            uncertain.value,
            page.value,
            state.settings.timezone,
          ]),
    debounce: () => q.value,
    keepPrevious: true,
  },
)
const detail = useRemote(
  () =>
    props.recordId && props.tab === 'deliveries'
      ? historyGet<DeliveryDetail>('deliveries/' + props.recordId, {
          attempt_page: attemptPage.value,
          task_page: taskPage.value,
        })
      : Promise.resolve(undefined),
  () => [props.recordId, props.tab, attemptPage.value, taskPage.value],
  {
    cacheKey: () =>
      props.recordId
        ? JSON.stringify(['record:delivery', props.recordId, attemptPage.value, taskPage.value])
        : undefined,
  },
)
const testDetail = useRemote(
  () =>
    props.recordId && props.tab !== 'deliveries'
      ? historyGet<TestRecord | ManualRecord>(props.tab + '/' + props.recordId, {
          task_page: taskPage.value,
        })
      : Promise.resolve(undefined),
  () => [props.recordId, props.tab, taskPage.value],
  {
    cacheKey: () =>
      props.recordId
        ? JSON.stringify(['record:detail', props.tab, props.recordId, taskPage.value])
        : undefined,
  },
)
const detailRead = computed(() => (props.tab === 'deliveries' ? detail : testDetail))
const time = (at: number | null) =>
  at === null ? '未记录' : formatTime(new Date(at * 1000).toISOString())
const value = (row: DeliveryRecord | TestRecord | ManualRecord) =>
  'status' in row ? row.status : row.result
const label = (row: DeliveryRecord | TestRecord | ManualRecord) =>
  'status' in row ? deliveryLabels[row.status] : resultLabels[row.result] || '历史结果未记录'
const title = (row: DeliveryRecord | TestRecord | ManualRecord) =>
  'title' in row ? row.title : row.target_name + ' · 目标测试'
const created = (row: DeliveryRecord | TestRecord | ManualRecord) =>
  'created_at' in row ? row.created_at : row.started_at
const channelStyle = (kind: string) =>
  channelMeta[kind as keyof typeof channelMeta] || { icon: 'send', color: 'blue' }
function clear() {
  q.value = ''
  status.value = 'all'
  target.value = ''
  dateRange.value = null
  uncertain.value = 'all'
}
</script>
<template>
  <template v-if="recordId">
    <button class="back-link" @click="emit('navigate', '/notifications/' + tab)">
      <Icon name="back" :size="17" />返回{{
        tab === 'tests' ? '测试记录' : tab === 'manual' ? '手动重发记录' : '投递记录'
      }}
    </button>
    <ReadRegion
      :loading="detailRead.loading.value"
      :error="detailRead.error.value"
      :has-data="!!detailRead.data.value"
      :stale="detailRead.stale.value"
      :min-height="360"
      @retry="detailRead.reload"
    >
      <template v-if="tab !== 'deliveries'">
        <template v-if="testDetail.data.value">
          <section class="page-heading">
            <div>
              <p class="eyebrow">EVERY DELIVERY, ACCOUNTED FOR</p>
              <h1 tabindex="-1">{{ tab === 'manual' ? '手动重发详情' : '目标测试详情' }}</h1>
              <p class="subtitle">
                {{ testDetail.data.value.target_name }} ·
                {{ time(testDetail.data.value.started_at) }}
              </p>
            </div>
            <button class="text-link" @click="testDetail.reload">刷新记录</button>
          </section>
          <div class="detail-layout">
            <section class="panel reading-panel">
              <span class="result-pill" :class="resultClass(testDetail.data.value.result)">{{
                resultLabels[testDetail.data.value.result] || '历史结果未记录'
              }}</span>
              <dl class="detail-grid">
                <div>
                  <dt>通知目标</dt>
                  <dd>{{ testDetail.data.value.target_name }}</dd>
                </div>
                <div>
                  <dt>渠道</dt>
                  <dd>{{ kindLabels[testDetail.data.value.kind] || '历史渠道' }}</dd>
                </div>
                <div>
                  <dt>开始时间</dt>
                  <dd>{{ time(testDetail.data.value.started_at) }}</dd>
                </div>
                <div>
                  <dt>完成时间</dt>
                  <dd>{{ time(testDetail.data.value.finished_at) }}</dd>
                </div>
                <div>
                  <dt>错误代码</dt>
                  <dd>{{ testDetail.data.value.error_code || '无' }}</dd>
                </div>
                <div class="wide">
                  <dt>操作标识</dt>
                  <dd class="mono">{{ testDetail.data.value.id }}</dd>
                </div>
              </dl>
              <template v-if="'source_event_id' in testDetail.data.value">
                <h2 class="record-title">{{ testDetail.data.value.title }}</h2>
                <p class="small-note">
                  使用当前目标配置快照 · 版本
                  {{
                    testDetail.data.value.target_revision
                  }}；独立手动重发，不改变自动去重、不自动重试。
                </p>
                <p class="article-summary">
                  {{ testDetail.data.value.post.summary ?? '摘要缺失' }}
                </p>
                <p
                  v-for="(task, i) in testDetail.data.value.tasks.items"
                  :key="i"
                  class="small-note"
                >
                  {{ task.name }} · 版本 {{ task.version }}
                </p>
                <Pagination
                  :page="taskPage"
                  :total="testDetail.data.value.tasks.total"
                  :page-size="testDetail.data.value.tasks.page_size"
                  label="重发任务"
                  @change="(v) => (taskPage = v)"
                />
                <button
                  v-if="testDetail.data.value.source_exists"
                  class="button"
                  @click="
                    emit(
                      'navigate',
                      '/notifications/deliveries/' + testDetail.data.value.source_event_id,
                    )
                  "
                >
                  查看原投递
                </button>
                <p v-else class="small-note">原投递已清理，独立重发快照仍保留。</p>
              </template>
              <p v-else class="small-note">
                独立目标测试不计入帖子自动投递账本。此页面只读取已保存结果，不运行或重发测试。
              </p>
              <p
                v-if="
                  testDetail.data.value.finished_at === null ||
                  testDetail.data.value.result === 'unknown'
                "
                class="warning-note"
              >
                尝试尚未结束或结果未知，接收端可能已经收到；不会自动重试，请刷新记录查看。
              </p>
              <p
                v-if="
                  testDetail.data.value.kind === 'smtp' &&
                  testDetail.data.value.result === 'success'
                "
                class="small-note"
              >
                SMTP 成功只表示服务器接受，不保证进入收件箱。
              </p>
            </section>
            <aside class="panel support-panel">
              <h2><Icon name="clock" :size="18" />投递过程</h2>
              <ol class="delivery-timeline">
                <li>
                  <strong>建立操作记录</strong>
                  <p>{{ time(testDetail.data.value.started_at) }}</p>
                </li>
                <li>
                  <strong>{{
                    resultLabels[testDetail.data.value.result] || '尝试尚未结束'
                  }}</strong>
                  <p>{{ time(testDetail.data.value.finished_at) }}</p>
                </li>
              </ol>
              <p class="small-note">
                独立测试与手动重发分别留存，不进入自动去重账本；结果未知时接收端可能已经收到。
              </p>
            </aside>
          </div>
        </template></template
      >
      <template v-else>
        <template v-if="detail.data.value">
          <section class="page-heading">
            <div>
              <p class="eyebrow">EVERY DELIVERY, ACCOUNTED FOR</p>
              <h1 tabindex="-1">投递详情</h1>
              <p class="subtitle">自动投递意图 · {{ time(detail.data.value.created_at) }}</p>
            </div>
            <button
              v-if="['sent', 'failed', 'cancelled'].includes(detail.data.value.status)"
              class="button primary"
              @click="resendOpen = true"
            >
              <Icon name="refresh" :size="16" />手动重发</button
            ><span v-else class="small-badge neutral">原投递尚未结束</span>
          </section>
          <div class="detail-layout">
            <div class="side-stack">
              <section class="panel reading-panel">
                <span class="result-pill" :class="resultClass(detail.data.value.status)">{{
                  detail.data.value.kind === 'smtp' && detail.data.value.status === 'sent'
                    ? '服务器已接受'
                    : deliveryLabels[detail.data.value.status]
                }}</span>
                <p v-if="detail.data.value.uncertain" class="warning-note">
                  曾有结果未知，接收端可能重复收到；后续成功不会抹去这项记录。
                </p>
                <h2 class="record-title">{{ detail.data.value.title }}</h2>
                <dl class="detail-grid">
                  <div>
                    <dt>通知目标快照</dt>
                    <dd>{{ detail.data.value.target_name }}</dd>
                  </div>
                  <div>
                    <dt>渠道</dt>
                    <dd>{{ kindLabels[detail.data.value.kind] || '历史渠道' }}</dd>
                  </div>
                  <div>
                    <dt>目标配置版本</dt>
                    <dd>{{ detail.data.value.target_revision ?? '旧记录未记录' }}</dd>
                  </div>
                  <div>
                    <dt>尝试次数</dt>
                    <dd>{{ detail.data.value.attempt_count }} 次</dd>
                  </div>
                  <div>
                    <dt>最后结果</dt>
                    <dd>
                      {{ resultLabels[detail.data.value.last_result || ''] || '尚无完成结果' }}
                    </dd>
                  </div>
                  <div>
                    <dt>错误代码</dt>
                    <dd>{{ detail.data.value.error_code || '无' }}</dd>
                  </div>
                  <div>
                    <dt>下次可处理时间</dt>
                    <dd>{{ time(detail.data.value.available_at) }}</dd>
                  </div>
                  <div>
                    <dt>渠道接受回执时间</dt>
                    <dd>{{ time(detail.data.value.receipt_at) }}</dd>
                  </div>
                  <div class="wide">
                    <dt>事件标识</dt>
                    <dd class="mono">{{ detail.data.value.id }}</dd>
                  </div>
                </dl>
                <p v-if="detail.data.value.cancel_requested" class="info-note">
                  此事件已请求取消；在途请求的实际结果仍单独留证。
                </p>
                <button
                  v-if="detail.data.value.post_id"
                  class="button"
                  @click="emit('navigate', '/content/' + detail.data.value.post_id)"
                >
                  查看关联内容<Icon name="arrow" :size="15" />
                </button>
                <p v-else class="small-note">原内容记录已清理，投递快照仍保留。</p>
                <p class="small-note">读取详情不会发送通知；显式确认后才运行独立重发。</p>
                <div class="subtle-divider" />
                <h3 class="section-subtitle">消息内容快照</h3>
                <p class="article-summary">
                  {{
                    detail.data.value.post.summary === null
                      ? '摘要字段缺失'
                      : detail.data.value.post.summary || '摘要为空或旧记录未保留'
                  }}
                </p>
                <p class="small-note">
                  作者：{{ detail.data.value.post.author || '缺失' }} · 版块：{{
                    detail.data.value.post.category || '缺失'
                  }}
                </p>
                <a
                  v-if="detail.data.value.post.original_url"
                  class="button"
                  :href="detail.data.value.post.original_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  >打开原帖 ↗</a
                >
                <h3 class="section-subtitle">消息任务快照</h3>
                <div
                  v-for="task in detail.data.value.tasks.items"
                  :key="task.id + ':' + task.version"
                  class="snapshot-task"
                >
                  <Icon name="layers" :size="16" /><button
                    v-if="!task.deleted"
                    class="text-link"
                    @click="emit('navigate', '/task/' + task.id)"
                  >
                    {{ task.name }}</button
                  ><span v-else>{{ task.name }} · 已删除</span
                  ><small>版本 {{ task.version }}</small>
                </div>
                <p v-if="!detail.data.value.tasks.total" class="small-note">旧记录没有任务快照。</p>
                <Pagination
                  :page="taskPage"
                  :total="detail.data.value.tasks.total"
                  :page-size="detail.data.value.tasks.page_size"
                  label="发送任务"
                  @change="(v) => (taskPage = v)"
                />
              </section>
            </div>
            <aside class="panel support-panel">
              <h2><Icon name="clock" :size="18" />投递尝试</h2>
              <ol class="delivery-timeline">
                <li v-for="attempt in detail.data.value.attempts.items" :key="attempt.sequence">
                  <strong
                    >第 {{ attempt.sequence }} 次 ·
                    {{ resultLabels[attempt.result] || '历史结果未记录' }}</strong
                  >
                  <p>{{ time(attempt.started_at) }} → {{ time(attempt.finished_at) }}</p>
                  <p v-if="attempt.error_code">错误代码：{{ attempt.error_code }}</p>
                  <p v-if="attempt.late_result" class="warning-note">
                    迟到结果：{{ resultLabels[attempt.late_result] || '未记录' }} ·
                    {{ time(attempt.late_finished_at) }}
                  </p>
                </li>
              </ol>
              <p v-if="!detail.data.value.attempts.total" class="small-note">
                尚无实际发送尝试，等待/取消状态不等于已经发送。
              </p>
              <Pagination
                :page="attemptPage"
                :total="detail.data.value.attempts.total"
                :page-size="detail.data.value.attempts.page_size"
                label="投递尝试"
                @change="(v) => (attemptPage = v)"
              />
              <p class="small-note">
                显示数据库最后保存的状态。后台按有限退避处理自动投递；SMTP 成功仅表示服务器接受。
              </p>
            </aside>
          </div></template
        ></template
      ></ReadRegion
    >
  </template>
  <template v-else>
    <section class="panel">
      <div class="filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="q"
            aria-label="搜索投递记录"
            :placeholder="tab !== 'deliveries' ? '搜索历史目标名称…' : '搜索内容或历史目标名称…'"
            maxlength="200"
        /></label>
        <AppSelect
          v-model="status"
          class="record-result-filter"
          aria-label="投递状态筛选"
          :options="[
            { value: 'all', label: '全部状态' },
            ...Object.entries(tab === 'deliveries' ? deliveryLabels : resultLabels)
              .filter(([value]) => tab !== 'manual' || value !== 'in_progress')
              .map(([value, label]) => ({ value, label })),
          ]"
        />
        <AppSelect
          v-model="target"
          aria-label="投递目标筛选"
          :options="[
            { value: '', label: '全部目标' },
            ...(options.data.value?.targets || []).map((item) => ({
              value: item.id,
              label: item.name,
            })),
          ]"
        />
        <AppSelect
          v-if="tab === 'deliveries'"
          v-model="uncertain"
          class="record-uncertainty-filter"
          aria-label="结果未知筛选"
          :options="[
            { value: 'all', label: '全部不确定性' },
            { value: 'true', label: '曾有结果未知' },
            { value: 'false', label: '未标记结果未知' },
          ]"
        />
        <DateFilter v-model="dateRange" label="记录日期" />
      </div>
      <ReadRegion
        :loading="listing.loading.value || options.loading.value"
        :error="[listing.error.value, options.error.value].filter(Boolean).join('；')"
        :has-data="!!listing.data.value"
        :stale="listing.stale.value"
        @retry="
          () => {
            listing.reload()
            options.reload()
          }
        "
      >
        <template v-if="listing.data.value">
          <article v-for="record in listing.data.value.items" :key="record.id" class="delivery-row">
            <span class="icon-tile" :class="channelStyle(record.kind).color"
              ><Icon :name="channelStyle(record.kind).icon" :size="18"
            /></span>
            <div class="management-copy">
              <button
                class="text-link task-title"
                @click="emit('navigate', '/notifications/' + tab + '/' + record.id)"
              >
                {{ title(record) }}
              </button>
              <p>
                {{ record.target_name }} · {{ time(created(record)) }} ·
                {{ kindLabels[record.kind] || '历史渠道' }}
              </p>
              <p v-if="'uncertain' in record && record.uncertain" class="amber-text">
                曾有结果未知，可能重复
              </p>
              <p v-if="record.error_code">错误代码：{{ record.error_code }}</p>
            </div>
            <span class="result-pill" :class="resultClass(value(record))">{{
              record.kind === 'smtp' && value(record) === 'sent' ? '服务器已接受' : label(record)
            }}</span>
            <button
              class="icon-button"
              :aria-label="'查看投递' + record.id"
              @click="emit('navigate', '/notifications/' + tab + '/' + record.id)"
            >
              <Icon name="arrow" :size="17" />
            </button>
          </article>
          <div v-if="!listing.data.value.total" class="empty-state">
            <Icon name="inbox" :size="32" />
            <h3>这里还没有记录</h3>
            <p>服务端尚无记录，或筛选条件未匹配。</p>
            <button class="button" @click="clear">清除筛选</button>
          </div>
          <Pagination
            :page="page"
            :total="listing.data.value.total"
            :page-size="listing.data.value.page_size"
            label="投递记录"
            @change="(v) => (page = v)"
          />
        </template>
      </ReadRegion></section
  ></template>
  <SendDialog
    v-if="resendOpen && recordId"
    action="resend"
    :id="recordId"
    @close="resendOpen = false"
    @complete="
      (path) => {
        resendOpen = false
        emit('navigate', path)
      }
    "
  />
</template>
