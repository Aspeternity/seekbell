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
    primaryColor: '#15665c',
    primaryColorHover: '#1d7c70',
    primaryColorPressed: '#0e4740',
    primaryColorSuppl: '#1d7c70',
    borderRadius: '8px',
  },
  Card: {
    borderRadius: '16px',
    paddingMedium: '20px 22px',
  },
  Button: {
    borderRadiusMedium: '8px',
    fontWeight: '600',
  },
  Tag: {
    borderRadius: '6px',
  },
}

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
    <main class="shell" :class="{ 'shell-unauth': !auth?.authenticated }">
      <header class="header">
        <a class="brand" href="/" aria-label="SeekBell 首页">
          <span class="bell">S</span>
          <span>SeekBell</span>
          <span class="brand-subtitle">NodeSeek 新帖监控中心</span>
        </a>
        <div v-if="auth?.authenticated" class="account">
          <span class="user-pill">
            <span class="user-dot" aria-hidden="true"></span>
            <span>{{ auth.username }}</span>
          </span>
          <NButton
            secondary
            :loading="submitting"
            :disabled="loading || submitting"
            @click="signOut"
          >
            退出登录
          </NButton>
        </div>
        <NTag v-else type="success" :bordered="false">新帖监控与通知</NTag>
      </header>

      <section
        class="intro"
        :class="{ 'intro-compact': auth?.authenticated }"
        aria-labelledby="page-title"
      >
        <div>
          <p class="eyebrow">从新帖，到你关心的消息</p>
          <h1 id="page-title">
            {{
              auth?.authenticated
                ? '欢迎回来。'
                : setup
                  ? '创建你的管理员账号。'
                  : '登录 SeekBell。'
            }}
          </h1>
          <p class="description">
            {{
              auth?.authenticated
                ? '查看服务运行信息，管理你的 NodeSeek 新帖监控。'
                : setup
                  ? '首次使用只需创建一个管理员账号。请保存好用户名和密码。'
                  : '使用管理员账号登录，继续管理你的监控。'
            }}
          </p>
          <div v-if="!auth?.authenticated" class="feature-pills" aria-hidden="true">
            <span class="feature-pill">NodeSeek 官方 RSS</span>
            <span class="feature-pill">三值规则匹配</span>
            <span class="feature-pill">四渠道合并投递</span>
          </div>
        </div>
      </section>

      <NAlert v-if="error" title="操作未完成" type="error" class="error-note" role="alert">
        {{ error }}
      </NAlert>
      <NAlert v-if="notice" type="success" class="notice">{{ notice }}</NAlert>
      <NSpin :show="loading">
        <div :aria-busy="loading">
          <NCard
            v-if="auth && !auth.authenticated"
            :title="setup ? '创建管理员' : '管理员登录'"
            class="editor-card"
          >
            <NForm @submit.prevent="submit">
              <NFormItem label="用户名" :label-props="{ for: 'username' }">
                <NInput
                  v-model:value="username"
                  :input-props="{ id: 'username', autocomplete: 'username', required: true }"
                  :maxlength="64"
                  :disabled="submitting"
                  placeholder="管理员用户名"
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
                  :minlength="15"
                  :maxlength="128"
                  :disabled="submitting"
                  placeholder="15–128 个字符，可使用长短语"
                />
              </NFormItem>
              <NFormItem v-if="setup" label="再次输入密码" :label-props="{ for: 'confirmation' }">
                <NInput
                  v-model:value="confirmation"
                  type="password"
                  show-password-on="click"
                  :input-props="{
                    id: 'confirmation',
                    autocomplete: 'new-password',
                    required: true,
                  }"
                  :minlength="15"
                  :maxlength="128"
                  :disabled="submitting"
                  placeholder="再次输入密码"
                />
              </NFormItem>
              <NButton
                attr-type="submit"
                type="primary"
                block
                :loading="submitting"
                :disabled="loading"
              >
                {{ setup ? '创建并登录' : '登录' }}
              </NButton>
            </NForm>
          </NCard>

          <section v-else-if="auth?.authenticated">
            <nav aria-label="管理导航" class="management-nav">
              <NButton
                :type="activePage === 'overview' ? 'primary' : 'default'"
                :secondary="activePage !== 'overview'"
                @click="activePage = 'overview'"
                >概览</NButton
              >
              <NButton
                :type="activePage === 'site' ? 'primary' : 'default'"
                :secondary="activePage !== 'site'"
                @click="activePage = 'site'"
                >监控网站</NButton
              >
              <NButton
                :type="activePage === 'tasks' ? 'primary' : 'default'"
                :secondary="activePage !== 'tasks'"
                @click="activePage = 'tasks'"
                >监控任务</NButton
              >
              <NButton
                :type="activePage === 'content' ? 'primary' : 'default'"
                :secondary="activePage !== 'content'"
                @click="activePage = 'content'"
                >内容与命中</NButton
              >
              <NButton
                :type="activePage === 'targets' ? 'primary' : 'default'"
                :secondary="activePage !== 'targets'"
                @click="activePage = 'targets'"
                >通知管理</NButton
              >
              <NButton
                :type="activePage === 'status' ? 'primary' : 'default'"
                :secondary="activePage !== 'status'"
                @click="activePage = 'status'"
                >系统设置</NButton
              >
            </nav>
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
          </section>
          <NCard v-else title="连接服务" class="record-card">
            <p>正在读取服务信息。若持续无法连接，请重试。</p>
            <NButton :loading="loading" @click="refresh">重试</NButton>
          </NCard>
        </div>
      </NSpin>

      <footer>
        SeekBell · 自托管的新帖监控与通知<span v-if="auth?.authenticated">
          · 显示时区：{{ displayTimezone ?? browserTimezone }}</span
        >
      </footer>
    </main>
  </NConfigProvider>
</template>
