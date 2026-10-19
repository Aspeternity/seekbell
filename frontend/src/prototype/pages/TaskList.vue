<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import {
  state,
  isLive,
  saveTask,
  removeTask,
  clone,
  notify,
  setTaskEnabled,
  confirmAction,
  websiteName,
} from '@workspace'
import type { Task } from '../model'
const emit = defineEmits<{ navigate: [path: string] }>()
const query = ref(''),
  filter = ref('all')
const list = computed(() =>
  state.tasks.filter(
    (t) =>
      t.name.toLowerCase().includes(query.value.toLowerCase()) &&
      (filter.value === 'all' || t.enabled === (filter.value === 'active')),
  ),
)
async function copy(task: Task) {
  const next = clone(task)
  next.id = isLive ? '' : 'task-' + crypto.randomUUID()
  next.name = task.name + ' · 副本'
  next.enabled = false
  next.hits = 0
  next.lastHit = '暂无命中'
  if (isLive) {
    try {
      await saveTask(next)
      emit('navigate', '/tasks')
    } catch (e) {
      notify((e as Error).message)
    }
    return
  }
  state.tasks.push(next)
  notify('任务已复制并保持暂停，可编辑后启用。')
  emit('navigate', '/task/' + next.id)
}
function remove(task: Task) {
  confirmAction(
    '删除「' + task.name + '」？',
    '任务将从当前列表移除。已有命中与投递历史仍保留；不会撤回已经发送的通知。',
    async () => {
      try {
        await removeTask(task)
      } catch (e) {
        notify((e as Error).message)
        return
      }
      notify('任务已删除，历史记录已保留。')
    },
    '删除任务',
  )
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">A PLACE FOR EVERY INTEREST</p>
      <h1 tabindex="-1">监控任务</h1>
      <p class="subtitle">把每一种关注，交给一条恰到好处的规则。</p>
    </div>
    <button class="button primary" @click="emit('navigate', '/task/new')">
      <Icon name="plus" :size="18" />新建任务
    </button>
  </section>
  <div class="metric-strip">
    <div>
      <span>全部任务</span><strong>{{ state.tasks.length }}</strong>
    </div>
    <div>
      <span>运行中</span
      ><strong class="positive-text">{{ state.tasks.filter((t) => t.enabled).length }}</strong>
    </div>
    <div>
      <span>已暂停</span><strong>{{ state.tasks.filter((t) => !t.enabled).length }}</strong>
    </div>
    <p><Icon name="shield" :size="18" />同一网站下的任务共享采集来源</p>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <div class="segmented">
        <button
          v-for="item in [
            { id: 'all', label: '全部任务' },
            { id: 'active', label: isLive ? '配置已启用' : '运行中' },
            { id: 'paused', label: '已暂停' },
          ]"
          :key="item.id"
          :class="{ active: filter === item.id }"
          :aria-pressed="filter === item.id"
          @click="filter = item.id"
        >
          {{ item.label }}
        </button>
      </div>
      <label class="search-input"
        ><Icon name="search" :size="16" /><input
          v-model="query"
          aria-label="搜索全部任务"
          placeholder="搜索任务名称…"
      /></label>
    </div>
    <div class="management-list">
      <article v-for="task in list" :key="task.id" class="management-row">
        <span class="icon-tile" :class="task.color"><Icon :name="task.icon" /></span>
        <div class="management-copy">
          <button class="text-link task-title" @click="emit('navigate', '/task/' + task.id)">
            {{ task.name }}
          </button>
          <p>{{ task.description || websiteName(task.websiteId) + ' · 新帖监控' }}</p>
          <div class="chip-line">
            <span class="plain-chip">{{ websiteName(task.websiteId) }}</span>
            <span class="plain-chip"
              >{{ task.groups.filter((g) => g.all.length || g.any.length).length }} 个条件组</span
            ><span class="plain-chip">{{ task.targets.length }} 个通知目标</span
            ><span class="plain-chip">{{
              task.scope === 'title' ? '标题' : task.scope === 'summary' ? '摘要' : '标题 + 摘要'
            }}</span>
          </div>
        </div>
        <div v-if="!isLive" class="management-stat">
          <strong>{{ task.hits }}</strong
          ><span>历史示例命中</span>
        </div>
        <div class="task-status">
          <Toggle
            :model-value="task.enabled"
            :label="task.name + '启用状态'"
            @update:model-value="(value) => setTaskEnabled(task, value)"
          /><span>{{ task.enabled ? (isLive ? '配置已启用' : '运行中') : '已暂停' }}</span>
        </div>
        <div class="row-actions">
          <button
            class="icon-button"
            :aria-label="'编辑' + task.name"
            @click="emit('navigate', '/task/' + task.id)"
          >
            <Icon name="edit" :size="17" /></button
          ><button class="icon-button" :aria-label="'复制' + task.name" @click="copy(task)">
            <Icon name="copy" :size="17" /></button
          ><button
            class="icon-button danger-text"
            :aria-label="'删除' + task.name"
            @click="remove(task)"
          >
            <Icon name="trash" :size="17" />
          </button>
        </div>
      </article>
    </div>
    <div v-if="!list.length" class="empty-state">
      <Icon name="layers" :size="32" />
      <h3>{{ state.tasks.length ? '没有匹配的任务' : '从你的第一个关注开始' }}</h3>
      <p>
        {{
          state.tasks.length ? '换一个关键词或筛选条件。' : '添加关键词与通知目标，让消息找到你。'
        }}
      </p>
      <button
        class="button"
        @click="
          state.tasks.length ? ((query = ''), (filter = 'all')) : emit('navigate', '/task/new')
        "
      >
        {{ state.tasks.length ? '清除筛选' : '创建第一个任务' }}
      </button>
    </div>
    <div class="table-footer">
      <span>{{ list.length }} 个任务</span><span>新建或修改任务，不会补发历史帖子</span>
    </div>
  </section>
  <div class="bottom-note">
    <Icon name="help" :size="17" />
    <p>先用“试匹配”验证规则，再保存启用。暂停期间发现的帖子不会在恢复后补发。</p>
  </div>
</template>
