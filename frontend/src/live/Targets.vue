<script setup lang="ts">
import { computed, ref } from 'vue'
import Icon from '../prototype/components/Icon.vue'
import NotificationTabs from './NotificationTabs.vue'
import Toggle from '../prototype/components/Toggle.vue'
import { state, channelMeta, setTargetEnabled, confirmAction, removeTarget, notify } from './store'
import type { Target } from '../prototype/shared'
import SendDialog from './SendDialog.vue'
const emit = defineEmits<{ navigate: [path: string] }>()
const q = ref(''),
  channel = ref('all'),
  testId = ref('')
const deleting = ref(false)
const deleteError = ref('')
function remove(target: Target) {
  if (deleting.value) return
  if (state.tasks.some((task) => task.targets.includes(target.id))) {
    notify('请先在关联任务中取消选择此目标，包括暂停的任务。')
    return
  }
  if (state.settings.alertTargets.includes(target.id)) {
    notify('请先在系统告警设置中取消选择此目标。')
    return
  }
  confirmAction(
    '删除「' + target.name + '」？',
    '删除当前配置并取消等待投递，历史记录保留。在途消息可能已经发出，无法撤回。',
    async () => {
      deleting.value = true
      deleteError.value = ''
      try {
        await removeTarget(target)
      } catch (error) {
        deleteError.value = (error as Error).message
      } finally {
        deleting.value = false
      }
    },
    '删除目标',
  )
}
const targets = computed(() =>
  state.targets.filter(
    (t) =>
      t.name.toLowerCase().includes(q.value.toLowerCase()) &&
      (channel.value === 'all' || t.channel === channel.value),
  ),
)
function completed(path: string) {
  testId.value = ''
  emit('navigate', path)
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">GOOD NEWS, YOUR WAY</p>
      <h1 tabindex="-1">通知管理</h1>
      <p class="subtitle">把关心的消息，送到你习惯的地方。</p>
    </div>
    <button class="button primary" @click="emit('navigate', '/target/new')">
      <Icon name="plus" :size="18" />添加通知目标
    </button>
  </section>
  <NotificationTabs tab="targets" @navigate="emit('navigate')" />
  <div class="filter-toolbar free-toolbar">
    <label class="search-input grow"
      ><Icon name="search" :size="16" /><input
        v-model="q"
        aria-label="搜索通知目标"
        placeholder="搜索通知目标…" /></label
    ><select v-model="channel" aria-label="通知渠道筛选">
      <option value="all">全部渠道</option>
      <option v-for="(meta, id) in channelMeta" :key="id" :value="id">{{ meta.type }}</option>
    </select>
  </div>
  <p v-if="deleteError" class="form-errors" role="alert">{{ deleteError }}</p>
  <div class="target-card-grid">
    <article v-for="target in targets" :key="target.id" class="panel notification-card">
      <div class="notification-card-top">
        <span class="icon-tile" :class="target.color"><Icon :name="target.icon" :size="22" /></span
        ><Toggle
          :model-value="target.enabled"
          :label="target.name + '启用状态'"
          @update:model-value="(value) => setTargetEnabled(target, value)"
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
        <Icon name="shield" :size="15" />连接配置已隐藏 · 已加密配置
      </div>
      <div class="target-card-meta">
        <span>{{ state.tasks.filter((t) => t.targets.includes(target.id)).length }} 个任务使用</span
        ><span>{{ target.summary ? '包含摘要' : '仅标题与基础信息' }}</span>
      </div>
      <div class="notification-card-actions">
        <button class="button" @click="testId = target.id">
          <Icon name="play" :size="14" />测试</button
        ><button class="button" @click="emit('navigate', '/target/' + target.id)">编辑</button>
        <button
          class="icon-button danger-text"
          :disabled="deleting"
          :aria-label="'删除' + target.name"
          @click="remove(target)"
        >
          <Icon name="trash" :size="16" />
        </button>
      </div>
    </article>
  </div>
  <section v-if="!targets.length" class="panel empty-state">
    <Icon name="bell" :size="32" />
    <h3>没有找到通知目标</h3>
    <p>添加第一个目标，或调整筛选条件。</p>
    <button class="button" @click="emit('navigate', '/target/new')">添加通知目标</button>
  </section>
  <div class="bottom-note">
    <Icon name="shield" :size="18" />
    <p>目标独立启停。同一帖子到同一目标合并发送；恢复目标不会自动补发积压消息。</p>
  </div>
  <SendDialog
    v-if="testId"
    :key="testId"
    action="test"
    :id="testId"
    @close="testId = ''"
    @complete="completed"
  />
</template>
