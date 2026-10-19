<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import { state, formatTime, deliveryLabels } from '../store'
import { statusLabel } from '../model'
const props = defineProps<{ selectedId?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const query = ref(''),
  status = ref('all'),
  task = ref('all'),
  category = ref('all'),
  date = ref('all'),
  page = ref(1)
const selected = computed(() => state.posts.find((p) => p.id === props.selectedId))
const filtered = computed(() =>
  state.posts
    .filter(
      (p) =>
        (p.title + ' ' + (p.summary || '') + ' ' + (p.author || ''))
          .toLowerCase()
          .includes(query.value.toLowerCase()) &&
        (status.value === 'all' || p.status === status.value) &&
        (task.value === 'all' || p.taskIds.includes(task.value)) &&
        (category.value === 'all' || p.category === category.value) &&
        (date.value === 'all' ||
          new Intl.DateTimeFormat('sv-SE', {
            timeZone: state.settings.timezone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
          }).format(new Date(p.time)) === date.value),
    )
    .sort((a, b) => b.time.localeCompare(a.time)),
)
const items = computed(() => filtered.value.slice((page.value - 1) * 5, page.value * 5))
watch([query, status, task, category, date], () => (page.value = 1))
function clear() {
  query.value = ''
  status.value = 'all'
  task.value = 'all'
  category.value = 'all'
  date.value = 'all'
}
const deliveries = computed(() => state.deliveries.filter((r) => r.postId === props.selectedId))
</script>
<template>
  <template v-if="selectedId"
    ><button class="back-link" @click="emit('navigate', '/content')">
      <Icon name="back" :size="17" />返回内容列表</button
    ><template v-if="selected"
      ><section class="page-heading">
        <div>
          <p class="eyebrow">A SIGNAL WORTH KEEPING</p>
          <h1 tabindex="-1" class="article-heading">{{ selected.title }}</h1>
          <p class="subtitle">
            NodeSeek · {{ selected.author || '作者缺失' }} · {{ selected.category || '版块缺失' }} ·
            {{ formatTime(selected.time) }}
          </p>
        </div>
        <span class="result-pill" :class="selected.status">{{ statusLabel[selected.status] }}</span>
      </section>
      <div class="website-layout">
        <div class="side-stack">
          <section class="panel reading-panel">
            <h2>RSS 内容快照</h2>
            <p class="article-summary">
              {{
                selected.summary === null
                  ? '来源未提供摘要，无法据此推断完整内容。'
                  : selected.summary || '来源提供的摘要为空。'
              }}
            </p>
            <div class="info-note">
              <Icon name="help" :size="18" />
              <p>
                这是一条合成演示帖子，未配置真实原帖链接。正式版将在此提供原帖入口；RSS
                摘要不等同全文。
              </p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-heading">
              <h2>投递记录</h2>
              <span class="count-badge">{{ deliveries.length }}</span>
            </div>
            <div v-for="record in deliveries" :key="record.id" class="compact-record">
              <span class="icon-tile" :class="record.channel === 'bark' ? 'purple' : 'blue'"
                ><Icon :name="record.channel === 'bark' ? 'phone' : 'send'" :size="18"
              /></span>
              <div>
                <strong>{{ record.targetName }}</strong>
                <p>
                  {{ formatTime(record.time) }} · {{ record.manual ? '手动重发' : '自动投递' }} ·
                  尝试 {{ record.attempts }} 次
                </p>
              </div>
              <button
                class="result-pill"
                :class="
                  record.status === 'success'
                    ? 'yes'
                    : record.status === 'failed'
                      ? 'no'
                      : 'unknown'
                "
                @click="emit('navigate', '/notifications/deliveries/' + record.id)"
              >
                {{ deliveryLabels[record.status] }} <Icon name="arrow" :size="13" />
              </button>
            </div>
            <div v-if="!deliveries.length" class="empty-state">
              <Icon name="inbox" :size="28" />
              <p>此帖子没有投递记录。</p>
            </div>
          </section>
        </div>
        <aside class="panel support-panel">
          <h2><Icon name="filter" :size="18" />为什么会得到这个结果？</h2>
          <div class="match-result" :class="selected.status">
            <strong>{{ statusLabel[selected.status] }}</strong>
            <p v-for="reason in selected.reasons" :key="reason">{{ reason }}</p>
          </div>
          <h3 class="section-subtitle">命中任务快照</h3>
          <template v-if="selected.taskIds.length"
            ><div v-for="(id, i) in selected.taskIds" :key="id" class="snapshot-task">
              <Icon name="layers" :size="16" /><button
                v-if="state.tasks.some((t) => t.id === id)"
                class="text-link"
                @click="emit('navigate', '/task/' + id)"
              >
                {{ selected.taskNames[i] }}</button
              ><span v-else>{{ selected.taskNames[i] }} · 已删除</span>
            </div></template
          >
          <p v-else>没有确定命中的任务。</p>
          <p class="small-note">保留命中时的名称与原因；当前规则修改不会重写已有记录。</p>
        </aside>
      </div></template
    >
    <section v-else class="panel empty-state">
      <h1 tabindex="-1">内容不存在</h1>
      <p>该演示记录可能已被重置或清理。</p>
    </section></template
  >
  <template v-else
    ><section class="page-heading">
      <div>
        <p class="eyebrow">FROM THE FEED, TO YOUR FOCUS</p>
        <h1 tabindex="-1">内容与命中</h1>
        <p class="subtitle">留住发现的线索，也看清每一次匹配。</p>
      </div>
      <span class="small-badge neutral">{{ state.posts.length }} 条本地样本</span>
    </section>
    <div class="metric-strip">
      <div>
        <span>示例内容</span><strong>{{ state.posts.length }}</strong>
      </div>
      <div>
        <span>确定命中</span
        ><strong class="positive-text">{{
          state.posts.filter((p) => p.status === 'yes').length
        }}</strong>
      </div>
      <div>
        <span>信息不足</span
        ><strong class="amber-text">{{
          state.posts.filter((p) => p.status === 'unknown').length
        }}</strong>
      </div>
      <p>时间显示：{{ state.settings.timezone }}</p>
    </div>
    <section class="panel">
      <div class="filter-toolbar">
        <label class="search-input grow"
          ><Icon name="search" :size="16" /><input
            v-model="query"
            aria-label="搜索内容"
            placeholder="搜索标题、摘要或作者…" /></label
        ><select v-model="status" aria-label="匹配结果">
          <option value="all">全部匹配结果</option>
          <option value="yes">命中</option>
          <option value="no">不命中</option>
          <option value="unknown">信息不足</option></select
        ><select v-model="task" aria-label="关联任务">
          <option value="all">全部任务</option>
          <option v-for="t in state.tasks" :key="t.id" :value="t.id">{{ t.name }}</option></select
        ><select v-model="category" aria-label="版块筛选">
          <option value="all">全部版块</option>
          <option
            v-for="name in [...new Set(state.posts.map((p) => p.category).filter(Boolean))]"
            :key="name!"
            :value="name"
          >
            {{ name }}
          </option></select
        ><select v-model="date" aria-label="发现日期">
          <option value="all">全部日期</option>
          <option value="2026-10-19">2026/10/19</option>
          <option value="2026-10-18">2026/10/18</option>
        </select>
      </div>
      <article v-for="post in items" :key="post.id" class="content-row">
        <div class="content-row-top">
          <span class="result-pill" :class="post.status">{{ statusLabel[post.status] }}</span
          ><span class="muted">{{ formatTime(post.time) }}</span>
        </div>
        <button class="content-title" @click="emit('navigate', '/content/' + post.id)">
          {{ post.title }}<Icon name="arrow" :size="17" />
        </button>
        <p class="content-excerpt">
          {{ post.summary === null ? '来源未提供摘要' : post.summary || '摘要为空' }}
        </p>
        <div class="content-row-meta">
          <span><Icon name="user" :size="13" />{{ post.author || '作者缺失' }}</span
          ><span>{{ post.category || '版块缺失' }}</span
          ><span v-for="name in post.taskNames" :key="name" class="plain-chip">{{ name }}</span>
        </div>
      </article>
      <div v-if="!filtered.length" class="empty-state">
        <Icon name="search" :size="30" />
        <h3>没有符合条件的内容</h3>
        <p>调整筛选条件，重新发现线索。</p>
        <button class="button" @click="clear">清除筛选</button>
      </div>
      <div class="pagination">
        <span>共 {{ filtered.length }} 条 · 每页 5 条</span>
        <div>
          <button class="icon-button" :disabled="page <= 1" aria-label="上一页内容" @click="page--">
            <Icon name="back" :size="16" /></button
          ><span>{{ page }} / {{ Math.max(1, Math.ceil(filtered.length / 5)) }}</span
          ><button
            class="icon-button"
            :disabled="page >= Math.ceil(filtered.length / 5)"
            aria-label="下一页内容"
            @click="page++"
          >
            <Icon name="arrow" :size="16" />
          </button>
        </div>
      </div></section
  ></template>
</template>
