<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import {
  state,
  channelMeta,
  deliveryLabels,
  formatTime,
  notify,
  testTarget,
  resend,
  confirmAction,
  setTargetEnabled,
  cancelTargetRetries,
} from '../store'
import type { Target, Delivery, DeliveryStatus } from '../store'
const props = withDefaults(defineProps<{ tab?: string; recordId?: string }>(), { tab: 'targets' })
const emit = defineEmits<{ navigate: [path: string] }>()
const query = ref(''),
  status = ref('all'),
  channel = ref('all'),
  targetFilter = ref('all')
const testDialog = ref<HTMLDialogElement>(),
  testing = ref(false),
  testChoice = ref<DeliveryStatus>('success'),
  testId = ref('')
const testSelected = computed(() => state.targets.find((t) => t.id === testId.value))
const selected = computed(() => state.deliveries.find((r) => r.id === props.recordId))
const targetList = computed(() =>
  state.targets.filter(
    (t) =>
      t.name.toLowerCase().includes(query.value.toLowerCase()) &&
      (channel.value === 'all' || t.channel === channel.value),
  ),
)
const records = computed(() =>
  state.deliveries.filter(
    (r) =>
      (props.tab === 'tests' ? r.test : !r.test) &&
      (status.value === 'all' || r.status === status.value) &&
      (targetFilter.value === 'all' || r.targetId === targetFilter.value) &&
      (r.title + ' ' + r.targetName).toLowerCase().includes(query.value.toLowerCase()),
  ),
)
function toggle(target: Target, value: boolean) {
  setTargetEnabled(target, value)
}
function remove(target: Target) {
  const linked = state.tasks.filter((t) => t.targets.includes(target.id))
  if (linked.length) {
    notify('此目标被 ' + linked.length + ' 个任务使用，请先在任务中取消选择。')
    return
  }
  confirmAction(
    '删除「' + target.name + '」？',
    '删除配置并保留投递历史。此操作仅影响浏览器演示。',
    () => {
      cancelTargetRetries(target.id)
      state.targets = state.targets.filter((t) => t.id !== target.id)
      state.settings.alertTargets = state.settings.alertTargets.filter((id) => id !== target.id)
      notify('目标已删除，投递历史保留。')
    },
    '删除目标',
  )
}
async function openTest(target: Target) {
  testId.value = target.id
  testChoice.value = 'success'
  await nextTick()
  testDialog.value?.showModal()
}
async function runTest() {
  const target = testSelected.value
  if (!target) return
  testing.value = true
  await new Promise((resolve) => setTimeout(resolve, 350))
  testTarget(target, testChoice.value)
  testing.value = false
  testDialog.value?.close()
}
function retry(record: Delivery) {
  confirmAction(
    '手动重发这条通知？',
    record.status === 'unknown'
      ? '接收端可能已经收到，重发可能重复。只向此目标生成一条独立的演示重发记录。'
      : '只向「' + record.targetName + '」重发，保留原始记录，不影响其他目标。',
    () => resend(record),
    '确认模拟重发',
  )
}
function canRetry(record: Delivery) {
  return !record.test && state.targets.some((t) => t.id === record.targetId && t.enabled)
}
</script>
<template>
  <template v-if="recordId"
    ><button
      class="back-link"
      @click="emit('navigate', '/notifications/' + (selected?.test ? 'tests' : 'deliveries'))"
    >
      <Icon name="back" :size="17" />返回投递记录</button
    ><template v-if="selected"
      ><section class="page-heading">
        <div>
          <p class="eyebrow">EVERY DELIVERY, ACCOUNTED FOR</p>
          <h1 tabindex="-1">投递详情</h1>
          <p class="subtitle">
            {{ selected.test ? '独立目标测试' : selected.manual ? '手动重发' : '自动通知' }} ·
            {{ formatTime(selected.time) }}
          </p>
        </div>
        <button v-if="canRetry(selected)" class="button primary" @click="retry(selected)">
          <Icon name="refresh" :size="16" />手动重发（模拟）
        </button>
      </section>
      <div class="detail-layout">
        <section class="panel reading-panel">
          <span
            class="result-pill"
            :class="
              selected.status === 'success'
                ? 'yes'
                : selected.status === 'failed'
                  ? 'no'
                  : 'unknown'
            "
            >{{
              selected.channel === 'smtp' && selected.status === 'success'
                ? '服务器已接受'
                : deliveryLabels[selected.status]
            }}</span
          >
          <h2 class="record-title">{{ selected.title }}</h2>
          <p class="article-summary">{{ selected.reason }}</p>
          <dl class="detail-grid">
            <div>
              <dt>通知目标</dt>
              <dd>{{ selected.targetName }}</dd>
            </div>
            <div>
              <dt>渠道</dt>
              <dd>{{ channelMeta[selected.channel].type }}</dd>
            </div>
            <div>
              <dt>尝试次数</dt>
              <dd>{{ selected.attempts }} 次</dd>
            </div>
            <div>
              <dt>记录类型</dt>
              <dd>{{ selected.test ? '独立测试' : selected.manual ? '手动重发' : '自动投递' }}</dd>
            </div>
            <div class="wide">
              <dt>事件标识</dt>
              <dd class="mono">{{ selected.id }}</dd>
            </div>
          </dl>
          <button
            v-if="selected.postId"
            class="button"
            @click="emit('navigate', '/content/' + selected.postId)"
          >
            查看关联内容<Icon name="arrow" :size="15" />
          </button>
          <p v-if="!canRetry(selected) && !selected.test" class="small-note">
            对应目标已暂停或删除，启用目标后才能重发。
          </p>
        </section>
        <aside class="panel support-panel">
          <h2><Icon name="clock" :size="18" />投递过程</h2>
          <ol class="delivery-timeline">
            <li>
              <strong>建立投递记录</strong>
              <p>使用命中时的目标与任务快照</p>
            </li>
            <li>
              <strong>{{ selected.test ? '运行独立测试' : '尝试发送' }}</strong>
              <p>本地模拟，无网络请求</p>
            </li>
            <li>
              <strong>{{ deliveryLabels[selected.status] }}</strong>
              <p>
                {{
                  selected.status === 'unknown'
                    ? '保留不确定性，不承诺绝对去重。'
                    : selected.status === 'retrying'
                      ? '正式服务将按有限退避策略重试。'
                      : '结果已写入浏览器演示记录。'
                }}
              </p>
            </li>
          </ol>
          <p class="small-note">SMTP 成功仅表示服务器接受；未知结果的重试可能产生重复消息。</p>
        </aside>
      </div></template
    >
    <section v-else class="panel empty-state">
      <h1 tabindex="-1">投递记录不存在</h1>
      <p>该演示记录可能已被重置。</p>
    </section></template
  >
  <template v-else
    ><section class="page-heading">
      <div>
        <p class="eyebrow">GOOD NEWS, YOUR WAY</p>
        <h1 tabindex="-1">通知管理</h1>
        <p class="subtitle">把关心的消息，送到你习惯的地方。</p>
      </div>
      <button class="button primary" @click="emit('navigate', '/target/new')">
        <Icon name="plus" :size="18" />添加通知目标
      </button>
    </section>
    <nav class="page-tabs" aria-label="通知管理分类">
      <button
        v-for="item in [
          { id: 'targets', label: '通知目标', count: state.targets.length },
          {
            id: 'deliveries',
            label: '投递记录',
            count: state.deliveries.filter((r) => !r.test).length,
          },
          { id: 'tests', label: '测试记录', count: state.deliveries.filter((r) => r.test).length },
        ]"
        :key="item.id"
        :class="{ active: tab === item.id }"
        :aria-current="tab === item.id ? 'page' : undefined"
        @click="emit('navigate', '/notifications/' + item.id)"
      >
        {{ item.label }}<span>{{ item.count }}</span>
      </button>
    </nav>
    <template v-if="tab === 'targets'"
      ><div class="filter-toolbar free-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="query"
            aria-label="搜索通知目标"
            placeholder="搜索通知目标…" /></label
        ><select v-model="channel" aria-label="通知渠道筛选">
          <option value="all">全部渠道</option>
          <option v-for="(meta, id) in channelMeta" :key="id" :value="id">{{ meta.type }}</option>
        </select>
      </div>
      <div class="target-card-grid">
        <article v-for="target in targetList" :key="target.id" class="panel notification-card">
          <div class="notification-card-top">
            <span class="icon-tile" :class="target.color"
              ><Icon :name="target.icon" :size="22" /></span
            ><Toggle
              :model-value="target.enabled"
              :label="target.name + '启用状态'"
              @update:model-value="(value) => toggle(target, value)"
            />
          </div>
          <button class="target-card-title" @click="emit('navigate', '/target/' + target.id)">
            {{ target.name }}
          </button>
          <p>
            {{ target.type }} <span class="separator">·</span>
            {{ target.enabled ? '已启用' : '已暂停' }}
          </p>
          <div class="credential-status">
            <Icon name="shield" :size="15" />连接配置已隐藏 ·
            {{ target.configured ? '演示已配置' : '未配置' }}
          </div>
          <div class="target-card-meta">
            <span
              >{{
                state.tasks.filter((t) => t.targets.includes(target.id)).length
              }}
              个任务使用</span
            ><span>{{ target.summary ? '包含摘要' : '仅标题与基础信息' }}</span>
          </div>
          <div class="notification-card-actions">
            <button class="button" @click="openTest(target)">
              <Icon name="play" :size="14" />测试</button
            ><button class="button" @click="emit('navigate', '/target/' + target.id)">编辑</button
            ><button
              class="icon-button danger-text"
              :aria-label="'删除' + target.name"
              @click="remove(target)"
            >
              <Icon name="trash" :size="16" />
            </button>
          </div>
        </article>
      </div>
      <section v-if="!targetList.length" class="panel empty-state">
        <Icon name="bell" :size="32" />
        <h3>没有找到通知目标</h3>
        <p>添加第一个目标，或调整筛选条件。</p>
        <button class="button" @click="emit('navigate', '/target/new')">添加通知目标</button>
      </section>
      <div class="bottom-note">
        <Icon name="shield" :size="18" />
        <p>目标独立启停。同一帖子到同一目标合并发送；恢复目标不会自动补发积压消息。</p>
      </div></template
    >
    <section v-else class="panel">
      <div class="filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="query"
            aria-label="搜索投递记录"
            placeholder="搜索内容或目标…" /></label
        ><select v-model="status" aria-label="投递状态筛选">
          <option value="all">全部状态</option>
          <option v-for="(label, id) in deliveryLabels" :key="id" :value="id">
            {{ label }}
          </option></select
        ><select v-model="targetFilter" aria-label="投递目标筛选">
          <option value="all">全部目标</option>
          <option v-for="t in state.targets" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>
      <article v-for="record in records" :key="record.id" class="delivery-row">
        <span class="icon-tile" :class="channelMeta[record.channel].color"
          ><Icon :name="channelMeta[record.channel].icon" :size="18"
        /></span>
        <div class="management-copy">
          <button
            class="text-link task-title"
            @click="emit('navigate', '/notifications/deliveries/' + record.id)"
          >
            {{ record.title }}
          </button>
          <p>
            {{ record.targetName }} · {{ formatTime(record.time) }} ·
            {{ record.manual ? '手动重发' : record.test ? '独立测试' : '自动通知' }}
          </p>
          <p>{{ record.reason }}</p>
        </div>
        <span
          class="result-pill"
          :class="
            record.status === 'success' ? 'yes' : record.status === 'failed' ? 'no' : 'unknown'
          "
          >{{
            record.channel === 'smtp' && record.status === 'success'
              ? '服务器已接受'
              : deliveryLabels[record.status]
          }}</span
        ><button
          class="icon-button"
          :aria-label="'查看投递' + record.id"
          @click="emit('navigate', '/notifications/deliveries/' + record.id)"
        >
          <Icon name="arrow" :size="17" />
        </button>
      </article>
      <div v-if="!records.length" class="empty-state">
        <Icon name="inbox" :size="32" />
        <h3>这里还没有记录</h3>
        <p>
          {{
            tab === 'tests'
              ? '对一个通知目标运行模拟测试，结果会显示在这里。'
              : '尝试调整状态或目标筛选。'
          }}
        </p>
      </div>
      <div class="table-footer">
        <span>{{ records.length }} 条记录</span
        ><span>{{
          tab === 'tests' ? '测试独立记录，不进入自动通知账本' : '状态与时间均来自本地演示'
        }}</span>
      </div>
    </section></template
  >
  <dialog ref="testDialog" class="dialog" @cancel.prevent="!testing && testDialog?.close()">
    <div class="dialog-top">
      <span class="dialog-icon"><Icon name="play" :size="23" /></span
      ><button
        class="icon-button"
        :disabled="testing"
        aria-label="关闭目标测试"
        @click="testDialog?.close()"
      >
        <Icon name="close" />
      </button>
    </div>
    <h2>测试通知目标</h2>
    <p>{{ testSelected?.name }} · 仅演示测试结果，不发送真实消息。暂停目标也可以手动测试。</p>
    <label class="field-label" for="target-test-result">模拟结果</label
    ><select id="target-test-result" v-model="testChoice" class="text-input">
      <option value="success">服务接受成功</option>
      <option value="failed">明确拒绝 / 配置错误</option>
      <option value="unknown">响应丢失 / 结果未知</option>
    </select>
    <div class="dialog-actions spaced">
      <button class="button" :disabled="testing" @click="testDialog?.close()">取消</button
      ><button class="button primary" :disabled="testing" @click="runTest">
        {{ testing ? '测试中…' : '运行模拟测试' }}
      </button>
    </div>
  </dialog>
</template>
