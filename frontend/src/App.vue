<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NConfigProvider,
  NDescriptions,
  NDescriptionsItem,
  NForm,
  NFormItem,
  NInput,
  NSpin,
  NTag,
  zhCN,
} from 'naive-ui'
import { ApiError, authenticate, loadAuth, loadSystemInfo, logout } from './api'
import type { AuthState, VersionInfo } from './api'

const TargetsPanel = defineAsyncComponent(() => import('./components/TargetsPanel.vue'))
const TasksPanel = defineAsyncComponent(() => import('./components/TasksPanel.vue'))

const auth = ref<AuthState | null>(null)
const activePage = ref('tasks')
const info = ref<VersionInfo | null>(null)
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const setup = computed(() => auth.value !== null && !auth.value.initialized)

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
  info.value = null
  clearPasswords()
  try {
    auth.value = await loadAuth()
    if (auth.value.authenticated) {
      info.value = await loadSystemInfo()
    }
  } catch (cause) {
    error.value = readableError(cause)
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!auth.value || submitting.value) return
  error.value = ''
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
    info.value = await loadSystemInfo()
  } catch (cause) {
    clearPasswords()
    if (cause instanceof ApiError && [401, 403, 409].includes(cause.status)) {
      // Recover stale sessions and setup races without replaying submitted credentials.
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
    info.value = null
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

let recoveringSession = false
async function sessionExpired() {
  if (recoveringSession) return
  recoveringSession = true
  auth.value = null
  info.value = null
  await refresh()
  error.value = '会话已过期，请重新登录。'
  recoveringSession = false
}
onMounted(() => {
  window.addEventListener('seekbell:session-expired', sessionExpired)
  void refresh()
})
onUnmounted(() => window.removeEventListener('seekbell:session-expired', sessionExpired))
</script>

<template>
  <NConfigProvider
    :locale="zhCN"
    :theme-overrides="{ common: { primaryColor: '#1b645b', primaryColorHover: '#257d71' } }"
  >
    <main class="shell">
      <header class="header">
        <a class="brand" href="/" aria-label="SeekBell 首页"><span class="bell">S</span>SeekBell</a>
        <div v-if="auth?.authenticated" class="account">
          <span>{{ auth.username }}</span>
          <NButton
            secondary
            :loading="submitting"
            :disabled="loading || submitting"
            @click="signOut"
          >
            退出登录
          </NButton>
        </div>
        <NTag v-else :bordered="false">新帖监控与通知</NTag>
      </header>

      <section class="intro" aria-labelledby="page-title">
        <p class="eyebrow">从新帖，到你关心的消息</p>
        <h1 id="page-title">
          {{
            auth?.authenticated ? '欢迎回来。' : setup ? '创建你的管理员账号。' : '登录 SeekBell。'
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
      </section>

      <NAlert v-if="error" title="操作未完成" type="error" class="error-note" role="alert">
        {{ error }}
      </NAlert>
      <NSpin :show="loading">
        <div :aria-busy="loading">
          <NCard v-if="auth && !auth.authenticated" :title="setup ? '创建管理员' : '管理员登录'">
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
                :type="activePage === 'tasks' ? 'primary' : 'default'"
                @click="activePage = 'tasks'"
                >监控任务</NButton
              >
              <NButton
                :type="activePage === 'targets' ? 'primary' : 'default'"
                @click="activePage = 'targets'"
                >通知目标</NButton
              >
              <NButton
                :type="activePage === 'status' ? 'primary' : 'default'"
                @click="activePage = 'status'"
                >运行信息</NButton
              >
            </nav>
            <TasksPanel
              v-if="activePage === 'tasks'"
              :csrf="auth.csrf_token"
              @targets="activePage = 'targets'"
            />
            <TargetsPanel v-else-if="activePage === 'targets'" :csrf="auth.csrf_token" />
            <NCard v-else title="运行信息" class="status-card">
              <template #header-extra>
                <NButton secondary :loading="loading" :disabled="submitting" @click="refresh">
                  刷新状态
                </NButton>
              </template>
              <NDescriptions v-if="info" :column="1" label-placement="left" bordered>
                <NDescriptionsItem label="服务状态">
                  <NTag type="success" size="small" :bordered="false">已就绪</NTag>
                </NDescriptionsItem>
                <NDescriptionsItem label="应用版本">{{ info.version }}</NDescriptionsItem>
                <NDescriptionsItem label="代码版本">
                  <code>{{ info.build_revision }}</code>
                </NDescriptionsItem>
                <NDescriptionsItem label="数据库迁移">
                  <code>{{ info.database_revision ?? '尚未初始化' }}</code>
                </NDescriptionsItem>
              </NDescriptions>
              <p v-else>暂时无法读取运行信息，请刷新重试。</p>
            </NCard>
          </section>
          <NCard v-else title="连接服务">
            <p>正在读取服务信息。若持续无法连接，请重试。</p>
            <NButton :loading="loading" @click="refresh">重试</NButton>
          </NCard>
        </div>
      </NSpin>

      <NAlert
        v-if="auth?.authenticated"
        title="当前开发进度"
        type="info"
        :bordered="false"
        class="phase-note"
      >
        通知目标、监控任务和两类规则试匹配已接入，后台采集与通知调度尚未启动。
      </NAlert>
      <footer>SeekBell · 自托管的新帖监控与通知</footer>
    </main>
  </NConfigProvider>
</template>
