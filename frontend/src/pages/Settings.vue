<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AboutSettings from './AboutSettings.vue'
import Preferences from './Preferences.vue'
import BackupSettings from './BackupSettings.vue'
import OverviewSettings from './OverviewSettings.vue'
import SessionSettings from './SessionSettings.vue'
import FormFeedback from '../components/FormFeedback.vue'
import AlertsSettings from './AlertsSettings.vue'
import RetentionSettings from './RetentionSettings.vue'
import { account, saveAdministrator, setSession, confirmAction } from '../store'
const props = defineProps<{ tab?: string }>()
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
const categories = [
  { value: 'preferences', label: '通用' },
  { value: 'overview', label: '概览' },
  { value: 'alerts', label: '系统告警' },
  { value: 'retention', label: '历史与存储' },
  { value: 'backup', label: '备份与恢复' },
  { value: 'account', label: '账户与安全' },
  { value: 'about', label: '关于与诊断' },
]
const selectedTab = computed(() => props.tab || 'preferences')
const tabs = ref<HTMLElement>()
function revealCategory() {
  const nav = tabs.value
  const current = nav?.querySelector<HTMLElement>('[aria-current="page"]')
  if (nav && current)
    nav.scrollTo({ left: current.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2 })
}
watch(selectedTab, () => nextTick(revealCategory), { flush: 'post' })
let tabResize: ResizeObserver | undefined
onMounted(() => {
  tabResize = new ResizeObserver(revealCategory)
  if (tabs.value) tabResize.observe(tabs.value)
})
onBeforeUnmount(() => tabResize?.disconnect())
function selectCategory(value: string) {
  emit('navigate', '/settings/' + value)
}
const retentionDirty = ref(false)
const auxiliaryDirty = ref(false)
const sessionDirty = ref(false)
const sessionGeneration = ref(0)
const username = ref(account.username),
  currentPassword = ref(''),
  newPassword = ref(''),
  confirmPassword = ref('')
const dirty = computed(() =>
  ['preferences', 'overview', 'alerts', 'backup'].includes(props.tab || '')
    ? auxiliaryDirty.value
    : props.tab === 'retention'
      ? retentionDirty.value
      : props.tab === 'account'
        ? username.value !== account.username ||
          !!currentPassword.value ||
          !!newPassword.value ||
          !!confirmPassword.value
        : false,
)
watch(dirty, (value) => emit('dirty', value))
const error = ref(''),
  busy = ref(false),
  saved = ref(false)
watch(
  () => props.tab,
  () => {
    username.value = account.username
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    error.value = ''
    saved.value = false
    auxiliaryDirty.value = false
    retentionDirty.value = false
    emit('dirty', false)
    sessionDirty.value = false
  },
)
async function saveAccount() {
  if (busy.value) return
  error.value = ''
  saved.value = false
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致。'
    return
  }
  if (username.value === account.username && !newPassword.value) {
    error.value = '请修改用户名或填写新密码。'
    return
  }
  busy.value = true
  try {
    await saveAdministrator(username.value, currentPassword.value, newPassword.value)
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    saved.value = true
    sessionGeneration.value++
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
async function performLogout() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await setSession(false)
    emit('dirty', false)
    emit('navigate', '/login')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
function logout() {
  if (dirty.value) {
    confirmAction('放弃修改并退出？', '尚未保存的账户修改将丢失。', performLogout, '退出登录')
  } else void performLogout()
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">MAKE YOURSELF AT HOME</p>
      <h1 tabindex="-1">系统设置</h1>
      <p class="subtitle">让 SeekBell 按照你的习惯运转。</p>
    </div>
    <span class="small-badge neutral">单管理员</span>
  </section>
  <div class="settings-shell">
    <nav ref="tabs" class="page-tabs settings-categories" aria-label="设置分类">
      <button
        v-for="item in categories"
        :key="item.value"
        type="button"
        :class="{ active: selectedTab === item.value }"
        :aria-current="selectedTab === item.value ? 'page' : undefined"
        @click="selectCategory(item.value)"
      >
        {{ item.label }}
      </button>
    </nav>
    <div class="settings-content">
      <Preferences v-if="props.tab === 'preferences'" @dirty="auxiliaryDirty = $event" />
      <div v-else-if="props.tab === 'account'" class="settings-stack">
        <section class="panel settings-card">
          <div class="panel-heading">
            <h2>管理员资料</h2>
            <span class="avatar">{{ account.username.slice(0, 1).toUpperCase() }}</span>
          </div>
          <FormFeedback :error="error" retry-label="重试保存" @retry="saveAccount" />
          <form class="form-content form-stack" @submit.prevent="saveAccount">
            <div class="general-fields-grid account-fields">
              <div class="form-stack">
                <label for="admin-username">管理员用户名</label>
                <input
                  id="admin-username"
                  v-model="username"
                  class="text-input"
                  autocomplete="username"
                  pattern="[A-Za-z0-9_-]{3,32}"
                  minlength="3"
                  maxlength="32"
                  required
                  :disabled="busy"
                />
                <p class="small-note">3–32 位字母、数字、_ 或 -</p>
              </div>
              <div class="form-stack">
                <label for="current-password">当前密码</label>
                <input
                  id="current-password"
                  v-model="currentPassword"
                  class="text-input"
                  type="password"
                  autocomplete="current-password"
                  maxlength="128"
                  required
                  :disabled="busy"
                />
              </div>
              <div class="form-stack">
                <label for="new-password"
                  >新密码 <span class="optional">留空保留原密码</span></label
                >
                <input
                  id="new-password"
                  v-model="newPassword"
                  class="text-input"
                  type="password"
                  autocomplete="new-password"
                  minlength="8"
                  maxlength="128"
                  :disabled="busy"
                />
              </div>
              <div class="form-stack">
                <label for="confirm-new-password">确认新密码</label>
                <input
                  id="confirm-new-password"
                  v-model="confirmPassword"
                  class="text-input"
                  type="password"
                  autocomplete="new-password"
                  minlength="8"
                  maxlength="128"
                  :required="!!newPassword"
                  :disabled="busy"
                />
              </div>
            </div>
            <p v-if="saved" class="info-note" role="status">管理员资料已保存，旧会话已失效。</p>
            <div class="inline-form-footer">
              <button class="text-link" type="button" :disabled="busy" @click="logout">
                退出登录
              </button>
              <button
                class="button primary"
                type="submit"
                :disabled="busy || (username === account.username && !newPassword)"
              >
                {{ busy ? '保存中…' : '更新管理员资料' }}
              </button>
            </div>
          </form>
        </section>
        <SessionSettings :key="sessionGeneration" @dirty="(value) => (sessionDirty = value)" />
      </div>
      <RetentionSettings v-else-if="props.tab === 'retention'" @dirty="retentionDirty = $event" />
      <OverviewSettings v-else-if="props.tab === 'overview'" @dirty="auxiliaryDirty = $event" />
      <AlertsSettings v-else-if="props.tab === 'alerts'" @dirty="auxiliaryDirty = $event" />
      <AboutSettings v-else-if="props.tab === 'about'" />
      <BackupSettings v-else-if="props.tab === 'backup'" @dirty="auxiliaryDirty = $event" />
    </div>
  </div>
</template>
