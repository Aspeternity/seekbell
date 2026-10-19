<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import Overview from './Overview.vue'
import TaskEditor from './TaskEditor.vue'
import { emptyTask, initialTasks } from './model'
import type { Task } from './model'
const storageKey = 'seekbell-ui-prototype-v1'
const message = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
function focusMain() {
  document.getElementById('main-content')?.focus()
}
function notice(text: string) {
  message.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (message.value = ''), 5500)
}
function readTasks(): Task[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(storageKey) || 'null')
    if (
      Array.isArray(data) &&
      data.length &&
      data.every(
        (t) =>
          t &&
          typeof t.id === 'string' &&
          typeof t.name === 'string' &&
          typeof t.enabled === 'boolean' &&
          Array.isArray(t.groups) &&
          t.groups.every(
            (g: { all?: unknown; any?: unknown }) => Array.isArray(g.all) && Array.isArray(g.any),
          ) &&
          ['exclude', 'categories', 'authorsInclude', 'authorsExclude', 'targets'].every((key) =>
            Array.isArray(t[key]),
          ),
      )
    )
      return data as Task[]
  } catch {
    /* Unavailable or invalid browser storage falls back to the demo. */
  }
  return structuredClone(initialTasks)
}
const tasks = ref<Task[]>(readTasks())
const page = ref(location.hash.startsWith('#/task/') ? 'editor' : 'overview')
const editId = ref(decodeURIComponent(location.hash.split('/')[2] || 'deals'))
const editing = computed(() =>
  editId.value === 'new'
    ? emptyTask()
    : tasks.value.find((task) => task.id === editId.value) || tasks.value[0] || emptyTask(),
)
const dirty = ref(false),
  mobileMenu = ref(false),
  discardDialog = ref<HTMLDialogElement>(),
  infoDialog = ref<HTMLDialogElement>()
const pending = ref(''),
  currentHash = ref(location.hash || '#/')
const infoTitle = ref(''),
  infoBody = ref('')
function showInfo(title: string, body: string) {
  infoTitle.value = title
  infoBody.value = body
  infoDialog.value?.showModal()
  mobileMenu.value = false
}
function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(tasks.value))
    return true
  } catch {
    notice('浏览器无法保存数据，本次修改仅保留到页面关闭。')
    return false
  }
}
function applyRoute(hash: string) {
  currentHash.value = hash
  history.replaceState(null, '', hash)
  editId.value = decodeURIComponent(hash.split('/')[2] || 'new')
  page.value = hash.startsWith('#/task/') ? 'editor' : 'overview'
  mobileMenu.value = false
  window.scrollTo(0, 0)
  nextTick(() => document.querySelector<HTMLElement>('h1')?.focus())
}
function navigate(hash: string) {
  if (hash === currentHash.value) {
    mobileMenu.value = false
    return
  }
  if (dirty.value) {
    pending.value = hash
    discardDialog.value?.showModal()
    return
  }
  applyRoute(hash)
}
function discard() {
  dirty.value = false
  discardDialog.value?.close()
  applyRoute(pending.value)
}
function hashChange() {
  const next = location.hash
  history.replaceState(null, '', currentHash.value)
  navigate(next)
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('hashchange', hashChange)
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  window.removeEventListener('hashchange', hashChange)
  window.removeEventListener('beforeunload', beforeUnload)
  clearTimeout(toastTimer)
})
watch(mobileMenu, async (value) => {
  document.body.classList.toggle('menu-open', value)
  await nextTick()
  document.querySelector<HTMLElement>(value ? '.menu-close' : '.menu-trigger')?.focus()
})
function menuKey(event: KeyboardEvent) {
  if (!mobileMenu.value) return
  if (event.key === 'Escape') {
    mobileMenu.value = false
    return
  }
  if (event.key !== 'Tab') return
  const items = [...document.querySelectorAll<HTMLElement>('.sidebar a, .sidebar button')].filter(
    (el) => el.offsetParent !== null,
  )
  const first = items[0],
    last = items.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
function toggle(id: string) {
  const task = tasks.value.find((t) => t.id === id)
  if (task) {
    task.enabled = !task.enabled
    if (persist()) notice(task.enabled ? '任务已在原型中恢复。' : '任务已在原型中暂停。')
  }
}
function save(task: Task) {
  const saved = structuredClone(task)
  saved.name = saved.name.trim()
  saved.groups = saved.groups.filter((group) => group.all.length || group.any.length)
  if (!saved.id) {
    saved.id = 'task-' + crypto.randomUUID()
    tasks.value.push(saved)
  } else tasks.value = tasks.value.map((t) => (t.id === saved.id ? saved : t))
  const persisted = persist()
  dirty.value = false
  applyRoute('#/')
  if (persisted) notice('任务已保存到此浏览器。原型不会采集或发送通知。')
}
const navItems = [
  { name: '概览', icon: 'grid', action: 'overview' },
  { name: '监控任务', icon: 'layers', action: 'tasks' },
  { name: '监控网站', icon: 'globe', action: 'later' },
  { name: '内容与命中', icon: 'inbox', action: 'later' },
  { name: '通知管理', icon: 'bell', action: 'later' },
]
function nav(action: string, name: string) {
  if (action === 'overview') navigate('#/')
  else if (action === 'tasks') navigate('#/task/' + (tasks.value[0]?.id || 'new'))
  else showInfo(name, '这次先确认概览与任务编辑的设计。' + name + '将在本轮原型确认后继续设计。')
}
</script>
<template>
  <a href="#main-content" class="skip-link" @click.prevent="focusMain">跳到主要内容</a>
  <div v-if="mobileMenu" class="mobile-scrim" @click="mobileMenu = false" />
  <aside
    @keydown="menuKey"
    :role="mobileMenu ? 'dialog' : undefined"
    :aria-modal="mobileMenu || undefined"
    class="sidebar"
    :class="{ expanded: mobileMenu }"
    aria-label="主导航"
  >
    <a href="#/" class="brand" @click.prevent="navigate('#/')"
      ><span class="brand-icon"><Icon name="bell" :size="23" /><i /></span
      ><span>seekbell<span class="brand-period">.</span></span></a
    ><button
      class="icon-button menu-close mobile-only"
      aria-label="关闭导航"
      @click="mobileMenu = false"
    >
      <Icon name="close" />
    </button>
    <div class="workspace-label">
      <span class="workspace-icon">S</span><span>个人工作空间<small>Administrator</small></span
      ><span class="workspace-dot" />
    </div>
    <p class="nav-label">工作空间</p>
    <nav>
      <button
        v-for="item in navItems"
        :key="item.name"
        :class="{
          selected:
            (item.action === 'overview' && page === 'overview') ||
            (item.action === 'tasks' && page === 'editor'),
        }"
        :aria-current="
          (item.action === 'overview' && page === 'overview') ||
          (item.action === 'tasks' && page === 'editor')
            ? 'page'
            : undefined
        "
        @click="nav(item.action, item.name)"
      >
        <Icon :name="item.icon" :size="19" /><span>{{ item.name }}</span
        ><span v-if="item.action === 'tasks'" class="nav-count">{{ tasks.length }}</span>
      </button>
    </nav>
    <div class="sidebar-bottom">
      <div class="quiet-card">
        <div class="quiet-symbol"><Icon name="activity" :size="21" /></div>
        <strong>好消息，安静地抵达。</strong>
        <p>你的关注，由 SeekBell 守候。</p>
        <span><i class="status-dot green-dot" />本地模拟模式</span>
      </div>
      <button
        class="sidebar-secondary"
        @click="
          showInfo(
            '系统设置',
            '系统设置将在原型确认后设计。当前使用模拟管理员，不涉及登录、凭据或后端数据。',
          )
        "
      >
        <Icon name="settings" :size="19" />系统设置</button
      ><button
        class="profile"
        @click="
          showInfo(
            '关于这个原型',
            'SeekBell 管理界面 v0.1。数据全部为合成示例，任务保存仅作用于当前浏览器。统计图和最近命中使用固定演示快照；任务修改不会改变历史统计。',
          )
        "
      >
        <span class="avatar">A</span><span><strong>管理员</strong><small>本地工作空间</small></span
        ><Icon name="down" :size="15" />
      </button>
    </div>
  </aside>
  <div class="app-main" :inert="mobileMenu">
    <header class="topbar">
      <div class="breadcrumb">
        <button
          class="icon-button menu-trigger mobile-only"
          aria-label="打开导航"
          :aria-expanded="mobileMenu"
          @click="mobileMenu = !mobileMenu"
        >
          <Icon name="menu" /></button
        ><span class="crumb-icon"
          ><Icon :name="page === 'overview' ? 'grid' : 'layers'" :size="17" /></span
        ><span>工作空间</span><span class="crumb-slash">/</span
        ><strong>{{ page === 'overview' ? '概览' : '任务编辑' }}</strong>
      </div>
      <div class="topbar-right">
        <span class="demo-badge"><span class="status-dot" />模拟数据</span
        ><button
          class="icon-button help-button"
          aria-label="原型使用说明"
          @click="
            showInfo(
              '原型使用说明',
              '从概览新建或编辑任务，调整关键词与通知目标，再用合成样本试匹配。保存后可返回概览并刷新，任务会保留在当前浏览器。所有采集与投递均为模拟；真实功能将在设计确认后接入。',
            )
          "
        >
          <Icon name="help" :size="19" /></button
        ><span class="avatar small">A</span>
      </div>
    </header>
    <main id="main-content" tabindex="-1">
      <Overview
        v-if="page === 'overview'"
        :tasks="tasks"
        @edit="(id) => navigate('#/task/' + id)"
        @create="navigate('#/task/new')"
        @toggle="toggle"
        @notice="notice"
      /><TaskEditor
        v-else
        :key="editId"
        :task="editing"
        @dirty="(value) => (dirty = value)"
        @save="save"
        @cancel="navigate('#/')"
      />
    </main>
  </div>
  <div v-if="message" class="toast" role="status">
    <Icon name="check" :size="18" /><span>{{ message }}</span
    ><button class="icon-button" aria-label="关闭提示" @click="message = ''">
      <Icon name="close" :size="16" />
    </button>
  </div>
  <dialog ref="discardDialog" class="dialog">
    <div class="dialog-icon"><Icon name="edit" :size="24" /></div>
    <h2>离开任务编辑？</h2>
    <p>你有尚未保存的修改。离开后，这些修改将丢失。</p>
    <div class="dialog-actions">
      <button class="button" @click="discardDialog?.close()">继续编辑</button
      ><button class="button primary" @click="discard">放弃修改并离开</button>
    </div>
  </dialog>
  <dialog ref="infoDialog" class="dialog">
    <div class="dialog-top">
      <span class="dialog-icon"><Icon name="bell" :size="24" /></span
      ><button class="icon-button" aria-label="关闭说明" @click="infoDialog?.close()">
        <Icon name="close" />
      </button>
    </div>
    <h2>{{ infoTitle }}</h2>
    <p>{{ infoBody }}</p>
    <div class="dialog-actions">
      <button class="button primary" @click="infoDialog?.close()">知道了</button>
    </div>
  </dialog>
</template>
