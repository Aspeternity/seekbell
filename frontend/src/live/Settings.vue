<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DisplaySettings from './DisplaySettings.vue'
import AlertsSettings from './AlertsSettings.vue'
import RetentionSettings from './RetentionSettings.vue'
import Icon from '../prototype/components/Icon.vue'
import { state, account, savePreferences, saveAdministrator, setSession } from './store'
const props = defineProps<{ tab?: string }>()
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
const retentionDirty = ref(false)
const auxiliaryDirty = ref(false)
const name = ref(state.settings.workspaceName),
  description = ref(state.settings.workspaceDescription)
const baseline = ref(JSON.stringify([name.value, description.value]))
const username = ref(account.username),
  currentPassword = ref(''),
  newPassword = ref(''),
  confirmPassword = ref('')
const dirty = computed(() =>
  ['display', 'alerts'].includes(props.tab || '')
    ? auxiliaryDirty.value
    : props.tab === 'retention'
      ? retentionDirty.value
      : props.tab === 'account'
        ? username.value !== account.username ||
          !!currentPassword.value ||
          !!newPassword.value ||
          !!confirmPassword.value
        : JSON.stringify([name.value, description.value]) !== baseline.value,
)
watch(dirty, (value) => emit('dirty', value))
const error = ref(''),
  busy = ref(false),
  saved = ref(false)
async function save() {
  if (busy.value) return
  error.value = ''
  saved.value = false
  busy.value = true
  try {
    await savePreferences({
      ...state.settings,
      workspaceName: name.value.trim(),
      workspaceDescription: description.value.trim(),
    })
    baseline.value = JSON.stringify([name.value, description.value])
    saved.value = true
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
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
  <nav class="page-tabs" aria-label="设置分类">
    <button
      v-for="item in [
        { id: 'preferences', label: '工作空间' },
        { id: 'account', label: '管理员' },
        { id: 'retention', label: '保留策略' },
        { id: 'display', label: '时区' },
        { id: 'alerts', label: '系统告警' },
      ]"
      :key="item.id"
      :class="{ active: tab === item.id }"
      @click="emit('navigate', '/settings/' + item.id)"
    >
      {{ item.label }}
    </button>
  </nav>
  <div v-if="error" class="form-errors" role="alert">{{ error }}</div>
  <div class="settings-layout">
    <section v-if="props.tab === 'preferences'" class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>工作空间与偏好</h2>
          <p>让这片信息空间，有自己的名字</p>
        </div>
        <Icon name="clock" :size="19" />
      </div>
      <form class="form-content form-stack" @submit.prevent="save">
        <h3>工作空间</h3>
        <p class="small-note">名称与说明显示在左侧导航顶部，方便识别你的工作空间。</p>
        <div class="workspace-settings-fields">
          <label for="workspace-name">工作空间名称</label
          ><input id="workspace-name" v-model="name" class="text-input" maxlength="24" required />
          <p class="small-note">最多 24 个字符。</p>
          <label for="workspace-description">工作空间说明 <span class="optional">选填</span></label>
          <input
            id="workspace-description"
            v-model="description"
            class="text-input"
            maxlength="40"
          />
        </div>
        <div class="workspace-preview" aria-label="工作空间外观预览">
          <span class="workspace-icon" aria-hidden="true">{{
            name.trim() === '个人工作空间' ? 'S' : Array.from(name.trim())[0]?.toUpperCase() || 'S'
          }}</span>
          <span class="workspace-copy"
            ><strong :title="name">{{ name.trim() || '工作空间名称' }}</strong
            ><small v-if="description.trim()" :title="description">{{
              description.trim()
            }}</small></span
          ><span class="workspace-dot" aria-hidden="true" />
        </div>
        <p class="small-note">上方为外观预览，保存后同步到导航；此名称不会更改管理员登录账号。</p>
        <div class="inline-form-footer">
          <span role="status">{{
            saved ? '设置已保存' : dirty ? '有未保存的修改' : '设置已保存'
          }}</span>
          <button class="button primary" type="submit" :disabled="busy">
            {{ busy ? '保存中…' : '保存偏好设置' }}
          </button>
        </div>
      </form>
    </section>
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
          <span>{{ dirty ? '有未保存的修改' : '资料已保存' }}</span>
          <button class="button primary" type="submit" :disabled="busy">
            {{ busy ? '保存中…' : '保存管理员资料' }}
          </button>
        </div>
        <button class="button" type="button" :disabled="busy" @click="logout">退出登录</button>
      </form>
    </section>
    <RetentionSettings v-else-if="props.tab === 'retention'" @dirty="retentionDirty = $event" />
    <DisplaySettings v-else-if="props.tab === 'display'" @dirty="auxiliaryDirty = $event" />
    <AlertsSettings v-else-if="props.tab === 'alerts'" @dirty="auxiliaryDirty = $event" />
    <section v-else class="panel empty-state">
      <h2>此设置将在后续阶段接入</h2>
      <p>当前可保存工作空间名称与说明，或管理登录会话。</p>
    </section>
  </div>
</template>
