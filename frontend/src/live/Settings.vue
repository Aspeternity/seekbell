<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AboutSettings from './AboutSettings.vue'
import Preferences from './Preferences.vue'
import BackupSettings from './BackupSettings.vue'
import DisplaySettings from './DisplaySettings.vue'
import AlertsSettings from './AlertsSettings.vue'
import RetentionSettings from './RetentionSettings.vue'
import Icon from '../prototype/components/Icon.vue'
import { account, saveAdministrator, setSession } from './store'
const props = defineProps<{ tab?: string }>()
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
const tabs = ref<HTMLElement>()
const preferenceTabs = ['preferences', 'retention', 'display', 'alerts']
const selectedTab = computed(() =>
  preferenceTabs.includes(props.tab || '') ? 'preferences' : props.tab,
)
onMounted(() =>
  tabs.value?.querySelector('.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' }),
)
const retentionDirty = ref(false)
const auxiliaryDirty = ref(false)
const username = ref(account.username),
  currentPassword = ref(''),
  newPassword = ref(''),
  confirmPassword = ref('')
const dirty = computed(() =>
  ['preferences', 'display', 'alerts', 'backup'].includes(props.tab || '')
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
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
async function logout() {
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
  <nav ref="tabs" class="page-tabs" aria-label="设置分类">
    <button
      v-for="item in [
        { id: 'preferences', label: '偏好与保留' },
        { id: 'account', label: '管理员' },
        { id: 'backup', label: '备份与恢复' },
        { id: 'about', label: '关于' },
      ]"
      :key="item.id"
      :class="{ active: selectedTab === item.id }"
      :aria-current="selectedTab === item.id ? 'page' : undefined"
      @click="emit('navigate', '/settings/' + item.id)"
    >
      {{ item.label }}
    </button>
  </nav>
  <div v-if="error" class="form-errors" role="alert">{{ error }}</div>
  <div class="settings-layout">
    <Preferences v-if="props.tab === 'preferences'" @dirty="auxiliaryDirty = $event" />
    <section v-else-if="props.tab === 'account'" class="panel settings-card">
      <div class="panel-heading">
        <h2>管理员资料</h2>
        <span class="avatar">{{ account.username.slice(0, 1).toUpperCase() }}</span>
      </div>
      <form class="form-content form-stack" @submit.prevent="saveAccount">
        <p class="small-note">
          修改需验证当前密码。保存后其他浏览器的旧会话失效，当前浏览器继续登录。
        </p>
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
        <p class="small-note">3–32 位字母、数字、下划线或短横线。</p>
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
        <label for="new-password">新密码 <span class="optional">留空保留原密码</span></label>
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
        <p v-if="saved" class="info-note" role="status">管理员资料已保存，旧会话已失效。</p>
        <div class="inline-form-footer">
          <button class="text-link" type="button" :disabled="busy" @click="logout">退出登录</button>
          <button class="button primary" type="submit" :disabled="busy">
            {{ busy ? '保存中…' : '更新管理员资料' }}
          </button>
        </div>
      </form>
    </section>
    <RetentionSettings v-else-if="props.tab === 'retention'" @dirty="retentionDirty = $event" />
    <DisplaySettings v-else-if="props.tab === 'display'" @dirty="auxiliaryDirty = $event" />
    <AlertsSettings v-else-if="props.tab === 'alerts'" @dirty="auxiliaryDirty = $event" />
    <AboutSettings v-else-if="props.tab === 'about'" />
    <BackupSettings v-else-if="props.tab === 'backup'" @dirty="auxiliaryDirty = $event" />
    <aside class="panel support-panel settings-aside">
      <h2><Icon name="help" :size="18" />关于这些设置</h2>
      <template v-if="selectedTab === 'preferences'">
        <p>时区影响网页与通知的时间显示。保留策略与系统告警由后台按照已保存的配置执行。</p>
        <div class="subtle-divider" />
        <p>
          <button class="text-link" @click="emit('navigate', '/settings/retention')">
            查看保留策略与清理状态
          </button>
        </p>
        <p>
          <button class="text-link" @click="emit('navigate', '/settings/display')">
            查看时区详情
          </button>
        </p>
        <p>
          <button class="text-link" @click="emit('navigate', '/settings/alerts')">
            查看系统告警记录
          </button>
        </p>
      </template>
      <p v-else-if="selectedTab === 'account'">
        首次初始化直接创建唯一管理员，无初始化令牌。修改资料需要验证当前密码，保存后其他浏览器的旧会话失效。
      </p>
      <p v-else-if="selectedTab === 'backup'">
        真实备份包含数据库和通知加密密钥。恢复先生成独立副本，正式切换通过宿主机维护工具执行。
      </p>
      <p v-else>SeekBell 使用内置网站适配器关注新帖。版本与运行状态从当前服务读取。</p>
    </aside>
  </div>
</template>
