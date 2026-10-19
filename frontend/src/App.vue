<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NForm,
  NFormItem,
  NInput,
  NSpin,
  NTag,
  zhCN,
} from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { ApiError, authenticate, loadAuth, loadSystemInfo, logout } from './api'
import type { AuthState } from './api'
import { browserTimezone, displayTimezone, getSettings, setDisplayTimezone } from './management'

const NotificationsPanel = defineAsyncComponent(() => import('./components/NotificationsPanel.vue'))
const TasksPanel = defineAsyncComponent(() => import('./components/TasksPanel.vue'))
const OverviewPanel = defineAsyncComponent(() => import('./components/OverviewPanel.vue'))
const SitePanel = defineAsyncComponent(() => import('./components/SitePanel.vue'))
const SettingsPanel = defineAsyncComponent(() => import('./components/SettingsPanel.vue'))
const ContentPanel = defineAsyncComponent(() => import('./components/ContentPanel.vue'))

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0f766e',
    primaryColorHover: '#0d9488',
    primaryColorPressed: '#115e59',
    primaryColorSuppl: '#0d9488',
    borderRadius: '8px',
  },
  Card: {
    borderRadius: '12px',
    paddingMedium: '18px 20px',
  },
  Button: {
    borderRadiusMedium: '8px',
    fontWeight: '600',
  },
  Tag: {
    borderRadius: '6px',
  },
}

const navItems = [
  {
    key: 'overview',
    label: '概览',
    desc: '全局运行态与投递统计',
    icon: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  },
  {
    key: 'site',
    label: '监控网站',
    desc: '站点卡片与采集配置',
    icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  },
  {
    key: 'tasks',
    label: '监控任务',
    desc: '三值规则与试匹配沙盒',
    icon: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  },
  {
    key: 'content',
    label: '内容与命中',
    desc: '本地保留新帖与命中溯源',
    icon: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  },
  {
    key: 'targets',
    label: '通知管理',
    desc: '四渠道接收端与投递记录',
    icon: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  },
  {
    key: 'status',
    label: '系统设置',
    desc: '时区、保留期与安全账号',
    icon: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  },
] as const

const validPages = new Set(['overview', 'site', 'tasks', 'content', 'targets', 'status'])
function pageFromHash(): string {
  const raw = window.location.hash.replace(/^#/, '')
  return validPages.has(raw) ? raw : 'overview'
}

const auth = ref<AuthState | null>(null)
const activePage = ref(pageFromHash())
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const notice = ref('')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const setup = computed(() => auth.value !== null && !auth.value.initialized)
const activeNav = computed(
  () => navItems.find((item) => item.key === activePage.value) ?? navItems[0],
)

function syncFromHash() {
  activePage.value = pageFromHash()
}

watch(activePage, (page) => {
  const nextHash = page === 'overview' ? '' : `#${page}`
  if (window.location.hash !== nextHash) {
    window.history.replaceState(
      null,
      '',
      nextHash || window.location.pathname + window.location.search,
    )
  }
})

function clearPasswords() {
  password.value = ''
  confirmation.value = ''
}

function readableError(cause: unknown): string {
  return cause instanceof Error ? cause.message : '无法连接服务，请稍后重试。'
}

async function refresh() {
  loading.value = true
  error.value = ''
  clearPasswords()
  try {
    auth.value = await loadAuth()
    if (auth.value.authenticated) {
      setDisplayTimezone((await getSettings()).timezone)
      await loadSystemInfo()
    }
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!auth.value || submitting.value) return
  error.value = notice.value = ''
  if (setup.value && password.value !== confirmation.value) {
    error.value = '两次输入的密码不一致。'
    return
  }
  submitting.value = true
  try {
    auth.value = await authenticate(
      setup.value ? 'setup' : 'login',
      { username: username.value, password: password.value },
      auth.value.csrf_token,
    )
    clearPasswords()
    setDisplayTimezone((await getSettings()).timezone)
    await loadSystemInfo()
  } catch (cause) {
    clearPasswords()
    if (cause instanceof ApiError && [401, 403, 409].includes(cause.status)) {
      try {
        auth.value = await loadAuth()
      } catch {
        auth.value = null
      }
    }
    error.value = readableError(cause)
  } finally {
    submitting.value = false
  }
}

async function signOut() {
  if (!auth.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    await logout(auth.value.csrf_token)
    auth.value = null
    username.value = ''
    await refresh()
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 401) {
      await refresh()
    }
    error.value = readableError(cause)
  } finally {
    submitting.value = false
  }
}

async function accountUpdated() {
  auth.value = null
  activePage.value = 'overview'
  username.value = ''
  clearPasswords()
  await refresh()
  notice.value = '账号已更新，所有登录会话已退出。请使用更新后的账号登录。'
}

let recoveringSession = false
async function sessionExpired() {
  if (recoveringSession) return
  recoveringSession = true
  auth.value = null
  await refresh()
  error.value = '会话已过期，请重新登录。'
  recoveringSession = false
}
onMounted(() => {
  window.addEventListener('seekbell:session-expired', sessionExpired)
  window.addEventListener('hashchange', syncFromHash)
  void refresh()
})
onUnmounted(() => {
  window.removeEventListener('seekbell:session-expired', sessionExpired)
  window.removeEventListener('hashchange', syncFromHash)
})
</script>

<template>
  <NConfigProvider :locale="zhCN" :theme-overrides="themeOverrides">
    <!-- Authenticated Left-Sidebar Console Layout -->
    <div v-if="auth?.authenticated" class="console-layout">
      <aside class="console-sidebar">
        <div class="sidebar-brand">
          <a class="brand" href="/" aria-label="SeekBell 首页">
            <span class="bell">S</span>
            <div class="brand-text">
              <span class="brand-name">SeekBell</span>
              <span class="brand-subtitle">新帖监控与通知控制台</span>
            </div>
          </a>
        </div>

        <div class="sidebar-group-label">监控管理菜单</div>
        <nav class="sidebar-nav" aria-label="管理导航">
          <button
            v-for="item in navItems"
            :key="item.key"
            type="button"
            class="sidebar-nav-btn"
            :class="{ active: activePage === item.key }"
            @click="activePage = item.key"
          >
            <svg class="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="item.icon" fill="currentColor" />
            </svg>
            <span class="sidebar-nav-label">{{ item.label }}</span>
          </button>
        </nav>

        <footer class="sidebar-footer">
          <div class="sidebar-user">
            <span class="user-avatar">{{ (auth.username || 'A').slice(0, 1).toUpperCase() }}</span>
            <div class="user-meta">
              <span class="user-name">{{ auth.username }}</span>
              <span class="user-tz"
                >显示时区：{{ displayTimezone ?? '浏览器（' + browserTimezone + '）' }}</span
              >
            </div>
          </div>
          <NButton
            size="small"
            secondary
            class="logout-btn"
            :loading="submitting"
            :disabled="loading || submitting"
            @click="signOut"
          >
            退出登录
          </NButton>
        </footer>
      </aside>

      <div class="console-main">
        <header class="console-topbar" aria-labelledby="page-title">
          <div class="topbar-left">
            <span class="topbar-badge">{{ activeNav.label }}</span>
            <h1 id="page-title" class="topbar-greeting">欢迎回来。</h1>
            <span class="topbar-desc">{{ activeNav.desc }}</span>
          </div>
          <div class="topbar-right">
            <span class="topbar-pill">NodeSeek 官方 RSS</span>
            <span class="topbar-pill">三值规则引擎</span>
            <span class="topbar-pill">四渠道合并队列</span>
          </div>
        </header>

        <main class="console-workspace">
          <NAlert v-if="error" title="操作未完成" type="error" class="error-note" role="alert">
            {{ error }}
          </NAlert>
          <NAlert v-if="notice" type="success" class="notice">{{ notice }}</NAlert>
          <NSpin :show="loading">
            <div :aria-busy="loading" class="workspace-body">
              <OverviewPanel v-if="activePage === 'overview'" />
              <SitePanel v-else-if="activePage === 'site'" :csrf="auth.csrf_token" />
              <TasksPanel
                v-else-if="activePage === 'tasks'"
                :csrf="auth.csrf_token"
                @targets="activePage = 'targets'"
              />
              <ContentPanel v-else-if="activePage === 'content'" />
              <NotificationsPanel v-else-if="activePage === 'targets'" :csrf="auth.csrf_token" />
              <SettingsPanel v-else :csrf="auth.csrf_token" @account-updated="accountUpdated" />
            </div>
          </NSpin>
        </main>
      </div>
    </div>

    <!-- Unauthenticated Full-Screen Split Console Layout -->
    <main v-else class="auth-split-layout">
      <section class="auth-hero-pane" aria-labelledby="page-title">
        <div class="auth-hero-top">
          <a class="brand brand-light" href="/" aria-label="SeekBell 首页">
            <span class="bell">S</span>
            <div class="brand-text">
              <span class="brand-name">SeekBell</span>
              <span class="brand-subtitle">网站适配型新帖监控系统</span>
            </div>
          </a>
          <NTag type="success" :bordered="false">单容器自托管</NTag>
        </div>

        <div class="auth-hero-content">
          <p class="eyebrow">从新帖，到你关心的消息</p>
          <h1 id="page-title">
            {{ setup ? '创建你的管理员账号。' : '登录 SeekBell。' }}
          </h1>
          <p class="description">
            {{
              setup
                ? '首次使用只需创建一个管理员账号。密码仅需 6 位及以上字符，请妥善保管。'
                : '使用管理员账号登录，进入全屏监控与通知管理控制台。'
            }}
          </p>

          <div class="auth-feature-grid" aria-hidden="true">
            <div class="auth-feature-card">
              <strong>站点卡片化监控</strong>
              <span>集中管理监控站点、采集频率与基线状态，支持后续多站点扩展</span>
            </div>
            <div class="auth-feature-card">
              <strong>三值规则与实时沙盒</strong>
              <span>关键词组、排除词、作者与版块精准过滤，支持模拟与历史试匹配</span>
            </div>
            <div class="auth-feature-card">
              <strong>四渠道可靠投递</strong>
              <span>Telegram Bot / Bark / SMTP / Webhook 自动去重合并与退避重试</span>
            </div>
          </div>
        </div>

        <footer class="auth-hero-footer">
          <span>SeekBell · 本地加密存储凭据 · 零外部追踪</span>
        </footer>
      </section>

      <section class="auth-form-pane">
        <div class="auth-form-container">
          <NAlert v-if="error" title="操作未完成" type="error" class="error-note" role="alert">
            {{ error }}
          </NAlert>
          <NAlert v-if="notice" type="success" class="notice">{{ notice }}</NAlert>

          <NSpin :show="loading">
            <div :aria-busy="loading">
              <NCard
                v-if="auth && !auth.authenticated"
                :title="setup ? '创建管理员' : '管理员登录'"
                class="auth-card"
              >
                <NForm @submit.prevent="submit">
                  <NFormItem label="用户名" :label-props="{ for: 'username' }">
                    <NInput
                      v-model:value="username"
                      :input-props="{ id: 'username', autocomplete: 'username', required: true }"
                      :maxlength="64"
                      :disabled="submitting"
                      placeholder="请输入管理员用户名"
                    />
                  </NFormItem>
                  <NFormItem label="密码" :label-props="{ for: 'password' }">
                    <NInput
                      v-model:value="password"
                      type="password"
                      show-password-on="click"
                      :input-props="{
                        id: 'password',
                        autocomplete: setup ? 'new-password' : 'current-password',
                        required: true,
                      }"
                      :minlength="6"
                      :maxlength="128"
                      :disabled="submitting"
                      placeholder="至少 6 个字符（6–128 位）"
                    />
                  </NFormItem>
                  <NFormItem
                    v-if="setup"
                    label="再次输入密码"
                    :label-props="{ for: 'confirmation' }"
                  >
                    <NInput
                      v-model:value="confirmation"
                      type="password"
                      show-password-on="click"
                      :input-props="{
                        id: 'confirmation',
                        autocomplete: 'new-password',
                        required: true,
                      }"
                      :minlength="6"
                      :maxlength="128"
                      :disabled="submitting"
                      placeholder="再次输入密码确认"
                    />
                  </NFormItem>
                  <NButton
                    attr-type="submit"
                    type="primary"
                    size="large"
                    block
                    :loading="submitting"
                    :disabled="loading"
                  >
                    {{ setup ? '创建并登录' : '登录' }}
                  </NButton>
                </NForm>
              </NCard>
            </div>
          </NSpin>
        </div>
      </section>
    </main>
  </NConfigProvider>
</template>
