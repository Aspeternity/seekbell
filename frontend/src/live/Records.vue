<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import { state, formatTime } from './store'
import {
  historyGet,
  useRemote,
  deliveryLabels,
  resultLabels,
  kindLabels,
  resultClass,
} from './history'
import type { Page, Options, DeliveryRecord, DeliveryDetail, TestRecord } from './history'
import Pagination from './Pagination.vue'
import Feedback from './Feedback.vue'
const props = withDefaults(defineProps<{ tab?: string; recordId?: string }>(), {
  tab: 'deliveries',
})
const emit = defineEmits<{ navigate: [path: string] }>()
const q = ref(''),
  status = ref('all'),
  target = ref(''),
  day = ref(''),
  uncertain = ref('all'),
  page = ref(1)
const attemptPage = ref(1),
  taskPage = ref(1)
watch([q, status, target, day, uncertain], () => (page.value = 1), { flush: 'sync' })
const options = useRemote(
  () => historyGet<Options>('options'),
  () => [],
)
const listing = useRemote<Page<DeliveryRecord> | Page<TestRecord> | undefined>(
  () =>
    props.recordId
      ? Promise.resolve(undefined)
      : props.tab === 'tests'
        ? historyGet<Page<TestRecord>>('tests', {
            q: q.value,
            status: status.value,
            target_id: target.value,
            discovered_on: day.value,
            timezone: state.settings.timezone,
            page: page.value,
          })
        : historyGet<Page<DeliveryRecord>>('deliveries', {
            q: q.value,
            status: status.value,
            target_id: target.value,
            discovered_on: day.value,
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
    day.value,
    uncertain.value,
    page.value,
  ],
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
)
const testDetail = useRemote(
  () =>
    props.recordId && props.tab === 'tests'
      ? historyGet<TestRecord>('tests/' + props.recordId)
      : Promise.resolve(undefined),
  () => [props.recordId, props.tab],
)
const time = (at: number | null) =>
  at === null ? '未记录' : formatTime(new Date(at * 1000).toISOString())
const value = (row: DeliveryRecord | TestRecord) => ('status' in row ? row.status : row.result)
const label = (row: DeliveryRecord | TestRecord) =>
  'status' in row ? deliveryLabels[row.status] : resultLabels[row.result] || '历史结果未记录'
const title = (row: DeliveryRecord | TestRecord) =>
  'title' in row ? row.title : row.target_name + ' · 目标测试'
const created = (row: DeliveryRecord | TestRecord) =>
  'created_at' in row ? row.created_at : row.started_at
function clear() {
  q.value = ''
  status.value = 'all'
  target.value = ''
  day.value = ''
  uncertain.value = 'all'
}
</script>
<template>
  <template v-if="recordId">
    <button class="back-link" @click="emit('navigate', '/notifications/' + tab)">
      <Icon name="back" :size="17" />返回{{ tab === 'tests' ? '测试记录' : '投递记录' }}
    </button>
    <template v-if="tab === 'tests'">
      <Feedback
        :loading="testDetail.loading.value"
        :error="testDetail.error.value"
        @retry="testDetail.reload"
      />
      <section v-if="testDetail.data.value" class="panel reading-panel">
        <h1 tabindex="-1">目标测试详情</h1>
        <h2>{{ testDetail.data.value.target_name }}</h2>
        <span class="result-pill" :class="resultClass(testDetail.data.value.result)">{{
          resultLabels[testDetail.data.value.result] || '历史结果未记录'
        }}</span>
        <dl class="detail-grid">
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
            <dt>测试标识</dt>
            <dd class="mono">{{ testDetail.data.value.id }}</dd>
          </div>
        </dl>
        <p class="small-note">
          独立目标测试不计入帖子自动投递账本。此页面只读取已保存结果，不运行或重发测试。
        </p>
        <p
          v-if="testDetail.data.value.kind === 'smtp' && testDetail.data.value.result === 'success'"
          class="small-note"
        >
          SMTP 成功只表示服务器接受，不保证进入收件箱。
        </p>
      </section></template
    >
    <template v-else>
      <Feedback
        :loading="detail.loading.value"
        :error="detail.error.value"
        @retry="detail.reload"
      />
      <template v-if="detail.data.value">
        <section class="page-heading">
          <div>
            <p class="eyebrow">EVERY DELIVERY, ACCOUNTED FOR</p>
            <h1 tabindex="-1">投递详情</h1>
            <p class="subtitle">自动投递意图 · {{ time(detail.data.value.created_at) }}</p>
          </div>
          <span class="small-badge neutral">只读历史</span>
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
                  <dd>{{ resultLabels[detail.data.value.last_result || ''] || '尚无完成结果' }}</dd>
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
              <p class="small-note">此页面不发出通知。手动重发和运行生命周期将在后续阶段接入。</p>
            </section>
            <section class="panel reading-panel">
              <h2>消息内容快照</h2>
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
                ><span v-else>{{ task.name }} · 已删除</span><small>版本 {{ task.version }}</small>
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
              显示数据库最后保存的状态。当前没有启动后台投递；SMTP 成功仅表示服务器接受。
            </p>
          </aside>
        </div></template
      ></template
    ></template
  >
  <template v-else>
    <section class="page-heading">
      <div>
        <p class="eyebrow">GOOD NEWS, YOUR WAY</p>
        <h1 tabindex="-1">通知管理</h1>
        <p class="subtitle">看清每一次投递，保留当时的结果。</p>
      </div>
      <span class="small-badge neutral">服务端历史</span>
    </section>
    <nav class="page-tabs" aria-label="通知管理分类">
      <button
        v-for="item in [
          { id: 'targets', label: '通知目标' },
          { id: 'deliveries', label: '投递记录' },
          { id: 'tests', label: '测试记录' },
        ]"
        :key="item.id"
        :class="{ active: tab === item.id }"
        :aria-current="tab === item.id ? 'page' : undefined"
        @click="emit('navigate', '/notifications/' + item.id)"
      >
        {{ item.label }}
      </button>
    </nav>
    <p class="info-note">
      只读取持久化的{{
        tab === 'tests' ? '独立目标测试' : '自动投递'
      }}记录，不触发采集、发送或重发。
    </p>
    <section class="panel">
      <div class="filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="q"
            aria-label="搜索投递记录"
            :placeholder="tab === 'tests' ? '搜索历史目标名称…' : '搜索内容或历史目标名称…'"
            maxlength="200"
        /></label>
        <select v-model="status" aria-label="投递状态筛选">
          <option value="all">全部状态</option>
          <option
            v-for="(label, key) in tab === 'tests' ? resultLabels : deliveryLabels"
            :key="key"
            :value="key"
          >
            {{ label }}
          </option>
        </select>
        <select v-model="target" aria-label="投递目标筛选">
          <option value="">全部目标</option>
          <option v-for="item in options.data.value?.targets || []" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
        <select v-if="tab !== 'tests'" v-model="uncertain" aria-label="结果未知筛选">
          <option value="all">全部不确定性</option>
          <option value="true">曾有结果未知</option>
          <option value="false">未标记结果未知</option>
        </select>
        <label class="check-label"
          >记录日期<input v-model="day" type="date" aria-label="记录日期"
        /></label>
      </div>
      <Feedback
        :loading="options.loading.value"
        :error="options.error.value"
        @retry="options.reload"
      />
      <Feedback
        :loading="listing.loading.value"
        :error="listing.error.value"
        @retry="listing.reload"
      />
      <template v-if="listing.data.value">
        <article v-for="record in listing.data.value.items" :key="record.id" class="delivery-row">
          <span class="icon-tile blue"><Icon name="send" :size="18" /></span>
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
      </template></section
  ></template>
</template>
