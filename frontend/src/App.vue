<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import TaskEditor from './pages/TaskEditor.vue'
import TaskList from './pages/TaskList.vue'
import Websites from './pages/Websites.vue'
import TargetEditor from './pages/TargetEditor.vue'
import Auth from './pages/Auth.vue'
import Overview from './pages/Overview.vue'
import Content from './pages/Content.vue'
import Notifications from './pages/Notifications.vue'
import Settings from './pages/Settings.vue'
import { emptyTask } from './model'
import type { Task } from './model'
import {
  state,
  toast,
  notify,
  account,
  signedIn,
  setSession,
  saveTask,
  newTarget,
  confirmation,
  confirmAction,
} from './store'
function normalize(hash: string) {
  try {
    const p = decodeURIComponent(hash.replace(/^#/, '')) || '/'
    if (p === '/settings/display') return '/settings/preferences?section=timezone'
    if (p.startsWith('/settings/preferences?') && p.includes('section=overview-modules'))
      return '/settings/overview?section=overview-modules'
    return p === '/notifications'
      ? '/notifications/targets'
      : p === '/settings'
        ? '/settings/preferences'
        : p
  } catch {
    return '/404'
  }
}
const path = ref(normalize(location.hash)),
  dirty = ref(false),
  mobileMenu = ref(false),
  taskReturn = ref('/')
if (!signedIn.value && !['/login', '/setup'].includes(path.value))
  path.value = !account.created ? '/setup' : '/login'
if (!account.created) path.value = '/setup'
if (signedIn.value && path.value === '/login') path.value = '/'
history.replaceState(null, '', '#' + path.value)
const parts = computed(() => path.value.split('?')[0]!.split('/').filter(Boolean))
const page = computed(() => parts.value[0] || 'overview')
const authPage = computed(() => ['login', 'setup'].includes(page.value))
const editId = computed(() => parts.value[1] || 'new')
const editing = computed(() =>
  editId.value === 'new'
    ? { ...emptyTask(), websiteIds: state.websites.length === 1 ? [state.websites[0]!.id] : [] }
    : state.tasks.find((t) => t.id === editId.value),
)
const targetEditing = computed(() =>
  editId.value === 'new' ? newTarget() : state.targets.find((t) => t.id === editId.value),
)
const navItems = [
  { name: '概览', icon: 'grid', path: '/', key: 'overview' },
  { name: '监控网站', icon: 'globe', path: '/websites', key: 'websites' },
  { name: '通知管理', icon: 'bell', path: '/notifications/targets', key: 'notifications' },
  { name: '监控任务', icon: 'layers', path: '/tasks', key: 'tasks' },
  { name: '内容与命中', icon: 'inbox', path: '/content', key: 'content' },
]
const activeKey = computed(() =>
  page.value === 'task' ? 'tasks' : page.value === 'target' ? 'notifications' : page.value,
)
const pageTitle = computed(() =>
  page.value === 'task'
    ? '任务编辑'
    : page.value === 'target'
      ? '目标编辑'
      : page.value === 'settings'
        ? '系统设置'
        : navItems.find((n) => n.key === page.value)?.name || '页面未找到',
)
const validPage = computed(
  () =>
    [
      'overview',
      'tasks',
      'websites',
      'content',
      'notifications',
      'target',
      'task',
      'settings',
    ].includes(page.value) &&
    (page.value !== 'task' || !!editing.value) &&
    (page.value !== 'target' || !!targetEditing.value) &&
    (page.value !== 'settings' ||
      ['preferences', 'overview', 'account', 'backup', 'about', 'retention', 'alerts'].includes(
        parts.value[1] || '',
      )) &&
    (page.value !== 'notifications' ||
      ['targets', 'deliveries', 'tests', ...['manual']].includes(parts.value[1] || '')),
)
const dialog = ref<HTMLDialogElement>(),
  infoDialog = ref<HTMLDialogElement>(),
  infoTitle = ref(''),
  infoBody = ref('')
watch(confirmation, async (value) => {
  await nextTick()
  if (value) dialog.value?.showModal()
  else dialog.value?.close()
})
function accept() {
  const action = confirmation.value?.run
  confirmation.value = null
  action?.()
}
function applyRoute(next: string, push = true) {
  const sectionTabs = /^\/(notifications|settings)\/[^/]+$/
  const internalTab =
    sectionTabs.test(path.value) &&
    sectionTabs.test(next) &&
    path.value.split('/')[1] === next.split('/')[1]
  if (!signedIn.value && !['/login', '/setup'].includes(next)) next = '/login'
  if (next.startsWith('/task/') && !path.value.startsWith('/task/'))
    taskReturn.value = path.value === '/tasks' ? '/tasks' : '/'
  if (push && path.value !== next) history.pushState(null, '', '#' + next)
  else history.replaceState(null, '', '#' + next)
  path.value = next
  saveError.value = ''
  dirty.value = false
  mobileMenu.value = false
  if (!internalTab) {
    window.scrollTo(0, 0)
    nextTick(() => document.querySelector<HTMLElement>('h1')?.focus())
  }
}
function navigate(next: string) {
  next = normalize(next)
  if (next === path.value) {
    mobileMenu.value = false
    return
  }
  if (dirty.value) {
    confirmAction(
      '离开当前编辑？',
      '你有尚未保存的修改。离开后，这些修改将丢失。',
      () => {
        dirty.value = false
        applyRoute(next)
      },
      '放弃修改并离开',
      '继续编辑',
    )
    return
  }
  applyRoute(next)
}
function hashChange() {
  const next = normalize(location.hash)
  if (dirty.value) {
    history.replaceState(null, '', '#' + path.value)
    navigate(next)
  } else applyRoute(next, false)
}
const loggingOut = ref(false)
function logout() {
  if (loggingOut.value) return
  if (dirty.value) {
    confirmAction(
      '退出登录？',
      '当前有尚未保存的修改。退出后，这些修改将丢失。',
      () => void finishLogout(),
      '退出并放弃修改',
      '继续编辑',
    )
  } else void finishLogout()
}
async function finishLogout() {
  loggingOut.value = true
  try {
    await setSession(false)
    dirty.value = false
    applyRoute('/login')
  } catch (error) {
    if (!signedIn.value) {
      dirty.value = false
      applyRoute('/login')
    } else notify('退出登录失败：' + (error as Error).message)
  } finally {
    loggingOut.value = false
  }
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
  document.body.classList.remove('menu-open')
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
  const items = [...document.querySelectorAll<HTMLElement>('.sidebar a,.sidebar button')].filter(
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
const saving = ref(false),
  saveError = ref('')
async function save(task: Task) {
  if (saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    await saveTask(task)
    dirty.value = false
    applyRoute(taskReturn.value)
  } catch (error) {
    saveError.value = (error as Error).message
  } finally {
    saving.value = false
  }
}
function expired() {
  dirty.value = false
  applyRoute('/login')
}
window.addEventListener('seekbell-session-expired', expired)
onBeforeUnmount(() => window.removeEventListener('seekbell-session-expired', expired))
function focusMain() {
  document.getElementById('main-content')?.focus()
}
function showInfo() {
  infoTitle.value = '使用说明'
  infoBody.value =
    '先添加监控网站和通知目标，再创建监控任务。系统设置可管理工作空间、概览布局、告警、历史保留、备份和账户安全。关闭浏览器不影响后台监控。备份可在系统设置中直接恢复，新安装也能在初始化页从备份恢复；版本、运行状态和帮助链接见“关于与诊断”。'
  infoDialog.value?.showModal()
}
</script>
<template>
  <Auth v-if="authPage" :key="path" :setup="page === 'setup'" @navigate="navigate" />
  <template v-else
    ><a href="#main-content" class="skip-link" @click.prevent="focusMain">跳到主要内容</a>
    <div v-if="mobileMenu" class="mobile-scrim" @click="mobileMenu = false" />
    <aside
      class="sidebar"
      :class="{ expanded: mobileMenu }"
      :role="mobileMenu ? 'dialog' : undefined"
      :aria-modal="mobileMenu || undefined"
      aria-label="主导航"
      @keydown="menuKey"
    >
      <a href="#/" class="brand" @click.prevent="navigate('/')"
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
        <span class="workspace-icon" aria-hidden="true">{{
          state.settings.workspaceName === '个人工作空间'
            ? 'S'
            : Array.from(state.settings.workspaceName)[0]?.toUpperCase()
        }}</span>
        <span class="workspace-copy"
          ><strong :title="state.settings.workspaceName">{{ state.settings.workspaceName }}</strong
          ><small
            v-if="state.settings.workspaceDescription"
            :title="state.settings.workspaceDescription"
            >{{ state.settings.workspaceDescription }}</small
          ></span
        ><span class="workspace-dot" aria-hidden="true" />
      </div>
      <p class="nav-label">工作空间</p>
      <nav>
        <button
          v-for="item in navItems"
          :key="item.key"
          :class="{ selected: activeKey === item.key }"
          :aria-current="activeKey === item.key ? 'page' : undefined"
          @click="navigate(item.path)"
        >
          <Icon :name="item.icon" :size="19" /><span>{{ item.name }}</span
          ><span v-if="item.key === 'tasks'" class="nav-count">{{ state.tasks.length }}</span>
        </button>
      </nav>
      <div class="sidebar-bottom">
        <div class="quiet-card">
          <div class="quiet-symbol"><Icon name="activity" :size="21" /></div>
          <strong>好消息，安静地抵达。</strong>
          <p>你的关注，由 SeekBell 守候。</p>
        </div>
        <button
          class="sidebar-secondary"
          :class="{ selected: page === 'settings' }"
          :aria-current="page === 'settings' ? 'page' : undefined"
          @click="navigate('/settings/preferences')"
        >
          <Icon name="settings" :size="19" />系统设置
        </button>
        <div class="profile">
          <span class="avatar">{{ account.username.slice(0, 1).toUpperCase() }}</span>
          <span class="profile-copy">
            <strong :title="account.username">{{ account.username }}</strong>
            <small>管理员</small>
          </span>
          <button
            class="icon-button profile-logout"
            type="button"
            :aria-label="loggingOut ? '正在退出登录' : '退出登录'"
            :title="loggingOut ? '正在退出登录' : '退出登录'"
            :disabled="loggingOut"
            :aria-busy="loggingOut"
            @click="logout"
          >
            <Icon name="logout" :size="16" />
          </button>
        </div>
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
            ><Icon
              :name="navItems.find((n) => n.key === activeKey)?.icon || 'settings'"
              :size="17" /></span
          ><span>工作空间</span><span class="crumb-slash">/</span><strong>{{ pageTitle }}</strong>
        </div>
        <div class="topbar-right">
          <span class="data-badge"><span class="status-dot" />本地数据</span
          ><button class="icon-button help-button" aria-label="使用说明" @click="showInfo">
            <Icon name="help" :size="19" />
          </button>
        </div>
      </header>
      <main id="main-content" tabindex="-1">
        <Overview v-if="page === 'overview'" @navigate="navigate" />
        <Content
          v-else-if="page === 'content'"
          :key="path"
          :selected-id="parts[1]"
          @navigate="navigate"
        />
        <Notifications
          v-else-if="
            page === 'notifications' &&
            ['targets', 'deliveries', 'tests', 'manual'].includes(parts[1] || '')
          "
          :tab="parts[1]!"
          :record-id="parts[2]"
          @navigate="navigate"
        />
        <TaskList v-else-if="page === 'tasks'" @navigate="navigate" />
        <section v-else-if="page === 'task' && !state.websites.length" class="panel empty-state">
          <Icon name="globe" :size="36" />
          <h1 tabindex="-1">先添加一个监控网站</h1>
          <p>每个任务关联一个已添加的网站，添加后即可设置监控规则。</p>
          <button class="button primary" @click="navigate('/websites')">前往添加网站</button>
        </section>
        <TaskEditor
          v-else-if="page === 'task' && editing"
          :key="path"
          :task="editing"
          :saving="saving"
          :save-error="saveError"
          :return-label="taskReturn === '/tasks' ? '返回任务列表' : '返回概览'"
          @dirty="(value: boolean) => (dirty = value)"
          @save="save"
          @navigate="navigate"
          @cancel="navigate(taskReturn)"
        />
        <Websites
          v-else-if="page === 'websites'"
          @navigate="navigate"
          @dirty="(value: boolean) => (dirty = value)"
        />
        <TargetEditor
          v-else-if="page === 'target' && targetEditing"
          :key="path"
          :target="targetEditing"
          @dirty="(value: boolean) => (dirty = value)"
          @navigate="navigate"
        />
        <Settings
          v-else-if="page === 'settings' && validPage"
          :tab="parts[1]"
          @dirty="(value: boolean) => (dirty = value)"
          @navigate="navigate"
        />
        <section v-else class="panel not-found">
          <span class="not-found-number">404</span>
          <h1 tabindex="-1">这条线索暂时不在这里</h1>
          <p>页面可能不存在，或记录已被删除。</p>
          <button class="button primary" @click="navigate('/')">
            返回概览<Icon name="arrow" :size="16" />
          </button>
        </section>
        <footer
          v-if="page !== 'overview' && page !== 'task' && page !== 'target'"
          class="page-footer"
        >
          <span><Icon name="bell" :size="14" />SeekBell · 留意你关心的</span
          ><span>SeekBell 管理界面</span>
        </footer>
      </main>
    </div></template
  >
  <div v-if="toast" class="toast" role="status">
    <Icon name="check" :size="18" /><span>{{ toast }}</span
    ><button class="icon-button" aria-label="关闭提示" @click="toast = ''">
      <Icon name="close" :size="16" />
    </button>
  </div>
  <dialog ref="dialog" class="dialog" aria-labelledby="confirm-title" @cancel="confirmation = null">
    <template v-if="confirmation"
      ><div class="dialog-icon"><Icon name="alert" :size="24" /></div>
      <h2 id="confirm-title">{{ confirmation.title }}</h2>
      <p>{{ confirmation.body }}</p>
      <div class="dialog-actions">
        <button class="button" @click="confirmation = null">{{ confirmation.cancelLabel }}</button
        ><button class="button primary" @click="accept">{{ confirmation.label }}</button>
      </div></template
    >
  </dialog>
  <dialog ref="infoDialog" class="dialog" aria-labelledby="info-title">
    <div class="dialog-top">
      <span class="dialog-icon"><Icon name="bell" :size="24" /></span
      ><button class="icon-button" aria-label="关闭说明" @click="infoDialog?.close()">
        <Icon name="close" />
      </button>
    </div>
    <h2 id="info-title">{{ infoTitle }}</h2>
    <p>{{ infoBody }}</p>
    <div class="dialog-actions">
      <button class="button primary" @click="infoDialog?.close()">知道了</button>
    </div>
  </dialog>
</template>
