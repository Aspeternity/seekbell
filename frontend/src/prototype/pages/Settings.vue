<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import {
  state,
  account,
  clone,
  notify,
  downloadConfig,
  validState,
  cleanState,
  restoreState,
  resetState,
  resetAccount,
  confirmAction,
  verifyPassword,
  updateAccount,
} from '../store'
import type { DemoState } from '../store'
const props = withDefaults(defineProps<{ tab?: string }>(), { tab: 'preferences' })
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
const draft = reactive(clone(state.settings)),
  username = ref(account.username),
  currentPassword = ref(''),
  password = ref(''),
  confirmPassword = ref(''),
  errors = ref<string[]>([]),
  busy = ref(false),
  importing = ref(false)
const imported = ref<DemoState | null>(null),
  fileName = ref(''),
  fileError = ref('')
const snapshot = () =>
  JSON.stringify({
    draft,
    username: username.value,
    currentPassword: currentPassword.value,
    password: password.value,
    confirmPassword: confirmPassword.value,
  })
const baseline = ref(snapshot()),
  dirty = computed(() => snapshot() !== baseline.value)
watch(dirty, (value) => emit('dirty', value))
function savePreferences() {
  errors.value = []
  if (!Number.isInteger(draft.retention) || draft.retention < 1 || draft.retention > 365) {
    errors.value = ['保留天数应为 1–365 之间的整数。']
    return
  }
  state.settings = clone(draft)
  baseline.value = snapshot()
  notify('偏好设置已保存，时间显示已同步更新。')
}
async function saveAccount() {
  errors.value = []
  if (!/^[A-Za-z0-9_-]{3,32}$/.test(username.value))
    errors.value.push('用户名应为 3–32 位字母、数字、下划线或短横线。')
  if (password.value && (password.value.length < 8 || password.value.length > 128))
    errors.value.push('新密码应为 8–128 个字符。')
  if (password.value !== confirmPassword.value) errors.value.push('两次输入的新密码不一致。')
  if (!currentPassword.value) errors.value.push('请填写当前演示密码。')
  if (errors.value.length) return
  busy.value = true
  try {
    if (!(await verifyPassword(currentPassword.value))) {
      errors.value = ['当前演示密码不正确。']
      return
    }
    await updateAccount(username.value, password.value || undefined)
    currentPassword.value = ''
    password.value = ''
    confirmPassword.value = ''
    baseline.value = snapshot()
    notify('演示管理员资料已更新。')
  } catch {
    errors.value = ['当前浏览器无法更新演示账号，请重试。']
  } finally {
    busy.value = false
  }
}
async function readImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  imported.value = null
  fileError.value = ''
  if (!file) return
  fileName.value = file.name
  if (file.size > 1024 * 1024) {
    fileError.value = '备份文件不能超过 1 MiB。'
    input.value = ''
    return
  }
  importing.value = true
  try {
    const data: unknown = JSON.parse(await file.text())
    if (
      !data ||
      typeof data !== 'object' ||
      !('kind' in data) ||
      data.kind !== 'seekbell-demo-backup' ||
      !('data' in data) ||
      !validState(data.data)
    )
      throw Error()
    imported.value = cleanState(data.data)
  } catch {
    fileError.value = '文件不是兼容的 SeekBell 演示备份，或包含无效/缺失的数据。'
  } finally {
    importing.value = false
    input.value = ''
  }
}
function restore() {
  if (!imported.value) return
  const data = clone(imported.value)
  confirmAction(
    '恢复这份演示备份？',
    '将替换当前浏览器内的任务、目标、内容、记录与偏好设置。管理员账号保持不变，不修改服务端。',
    () => {
      restoreState(data)
      Object.assign(draft, state.settings)
      baseline.value = snapshot()
      imported.value = null
      fileName.value = ''
    },
    '确认恢复',
  )
}
function reset() {
  confirmAction(
    '重置整个演示工作空间？',
    '清除浏览器内的编辑内容与演示账号，恢复默认示例并进入首次初始化。此操作不会影响真实数据库。',
    () => {
      resetState()
      resetAccount()
      emit('dirty', false)
      emit('navigate', '/setup')
    },
    '重置演示',
  )
}
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">MAKE YOURSELF AT HOME</p>
      <h1 tabindex="-1">系统设置</h1>
      <p class="subtitle">让 SeekBell 按照你的习惯运转。</p>
    </div>
    <span class="small-badge neutral">单管理员 · 本地演示</span>
  </section>
  <nav class="page-tabs" aria-label="设置分类">
    <button
      v-for="item in [
        { id: 'preferences', label: '偏好与保留' },
        { id: 'account', label: '管理员' },
        { id: 'backup', label: '备份与恢复' },
        { id: 'about', label: '关于' },
      ]"
      :key="item.id"
      :class="{ active: tab === item.id }"
      :aria-current="tab === item.id ? 'page' : undefined"
      @click="emit('navigate', '/settings/' + item.id)"
    >
      {{ item.label }}
    </button>
  </nav>
  <div v-if="errors.length" class="form-errors" role="alert">
    <Icon name="alert" :size="18" />
    <div>
      <p v-for="error in errors" :key="error">{{ error }}</p>
    </div>
  </div>
  <div class="settings-layout">
    <section v-if="tab === 'preferences'" class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>时间与历史</h2>
          <p>保留足够上下文，不让信息无限堆积</p>
        </div>
        <Icon name="clock" :size="19" />
      </div>
      <form class="form-content form-stack" @submit.prevent="savePreferences">
        <label
          >显示时区<select v-model="draft.timezone" class="text-input">
            <option value="Asia/Shanghai">中国标准时间 · Asia/Shanghai</option>
            <option value="UTC">协调世界时 · UTC</option>
            <option value="Asia/Tokyo">日本标准时间 · Asia/Tokyo</option>
            <option value="America/Los_Angeles">洛杉矶 · America/Los_Angeles</option>
          </select></label
        >
        <p class="small-note">帖子与投递存储 UTC，展示按所选时区转换。</p>
        <label
          >普通历史保留天数
          <div class="unit-input">
            <input
              v-model.number="draft.retention"
              type="number"
              min="1"
              max="365"
              class="text-input"
              required
            /><span>天</span>
          </div></label
        >
        <div class="info-note">
          <Icon name="shield" :size="18" />
          <p>独立去重标识不随普通历史删除。原型只保存策略，不执行后台清理。</p>
        </div>
        <div class="subtle-divider" />
        <h3>系统告警</h3>
        <div class="setting-row no-border">
          <div>
            <strong>故障与恢复通知</strong><small>每次状态变化通知一次，避免每轮重复。</small>
          </div>
          <Toggle v-model="draft.recoveryAlerts" label="故障与恢复通知" />
        </div>
        <fieldset class="plain-fieldset">
          <legend class="field-label">告警通知目标</legend>
          <div class="form-stack">
            <label v-for="target in state.targets" :key="target.id" class="check-label"
              ><input v-model="draft.alertTargets" type="checkbox" :value="target.id" />{{
                target.name
              }}<span class="small-badge neutral">{{
                target.enabled ? '已启用' : '已暂停'
              }}</span></label
            >
          </div>
        </fieldset>
        <div class="inline-form-footer">
          <span>{{ dirty ? '有未保存的修改' : '设置已保存' }}</span
          ><button class="button primary" type="submit">保存偏好设置</button>
        </div>
      </form>
    </section>
    <section v-else-if="tab === 'account'" class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>管理员资料</h2>
          <p>此工作空间仅允许一个管理员</p>
        </div>
        <span class="avatar">{{ account.username.slice(0, 1).toUpperCase() }}</span>
      </div>
      <form class="form-content form-stack" @submit.prevent="saveAccount">
        <div class="info-note">
          <Icon name="shield" :size="18" />
          <p>
            这是浏览器内的演示账号，不提供真实服务端认证。请勿使用真实密码。默认演示密码为
            SeekBell2026!。
          </p>
        </div>
        <label
          >管理员用户名<input
            v-model="username"
            class="text-input"
            autocomplete="username"
            maxlength="32" /></label
        ><label
          >当前演示密码 <span class="required">*</span
          ><input
            v-model="currentPassword"
            type="password"
            class="text-input"
            autocomplete="current-password"
            required /></label
        ><label
          >新密码 <span class="optional">不修改则留空</span
          ><input
            v-model="password"
            type="password"
            class="text-input"
            autocomplete="new-password"
            minlength="8"
            maxlength="128" /></label
        ><label
          >确认新密码<input
            v-model="confirmPassword"
            type="password"
            class="text-input"
            autocomplete="new-password"
            maxlength="128"
        /></label>
        <div class="inline-form-footer">
          <button class="text-link" type="button" @click="emit('navigate', '/login')">
            退出演示登录</button
          ><button class="button primary" type="submit" :disabled="busy">
            {{ busy ? '保存中…' : '更新管理员资料' }}
          </button>
        </div>
      </form>
    </section>
    <div v-else-if="tab === 'backup'" class="side-stack">
      <section class="panel settings-card">
        <div class="panel-heading">
          <div>
            <h2>导出演示备份</h2>
            <p>带走当前浏览器内的配置和合成历史</p>
          </div>
          <Icon name="download" :size="21" />
        </div>
        <div class="form-content">
          <div class="backup-summary">
            <span
              ><strong>{{ state.tasks.length }}</strong
              >任务</span
            ><span
              ><strong>{{ state.targets.length }}</strong
              >目标</span
            ><span
              ><strong>{{ state.posts.length }}</strong
              >帖子</span
            ><span
              ><strong>{{ state.deliveries.length }}</strong
              >记录</span
            >
          </div>
          <div class="info-note">
            <Icon name="shield" :size="18" />
            <p>
              不包含管理员密码、会话、服务地址与通知凭据。文件只适用于此原型；不是生产数据库备份。
            </p>
          </div>
          <button class="button primary spaced" @click="downloadConfig">
            <Icon name="download" :size="17" />下载演示备份
          </button>
        </div>
      </section>
      <section class="panel settings-card">
        <div class="panel-heading">
          <div>
            <h2>从文件恢复</h2>
            <p>先校验文件，确认后再替换本地数据</p>
          </div>
          <Icon name="upload" :size="21" />
        </div>
        <div class="form-content">
          <label class="upload-zone"
            ><Icon name="upload" :size="28" /><strong>{{
              importing ? '正在校验…' : '选择 SeekBell 演示备份'
            }}</strong
            ><span>JSON 格式 · 最大 1 MiB</span
            ><input
              type="file"
              accept=".json,application/json"
              aria-label="选择演示备份文件"
              :disabled="importing"
              @change="readImport"
          /></label>
          <p v-if="fileError" class="inline-error" role="alert">{{ fileError }}</p>
          <div v-if="imported" class="restore-preview">
            <strong>{{ fileName }}</strong>
            <p>
              校验通过：{{ imported.tasks.length }} 个任务、{{ imported.targets.length }} 个目标、{{
                imported.posts.length
              }}
              条内容。
            </p>
            <button class="button primary" @click="restore">确认恢复这份备份</button>
          </div>
        </div>
      </section>
    </div>
    <div v-else class="side-stack">
      <section class="panel about-card">
        <span class="brand-icon"><Icon name="bell" :size="26" /></span>
        <h2>SeekBell<span class="brand-period">.</span></h2>
        <p>留意你关心的。</p>
        <span class="small-badge neutral">管理界面 v0.2 · 完整演示</span>
        <dl class="detail-grid">
          <div>
            <dt>前端</dt>
            <dd>Vue 3 / TypeScript / Vite</dd>
          </div>
          <div>
            <dt>运行模式</dt>
            <dd>浏览器本地 · 模拟数据</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>NodeSeek 官方 RSS</dd>
          </div>
          <div>
            <dt>后端连接</dt>
            <dd>未接入</dd>
          </div>
        </dl>
        <p>六个管理模块、任务与目标编辑、内容与投递详情，以及初始化和登录流程均可体验。</p>
      </section>
      <section class="panel danger-panel">
        <h3>重新体验首次初始化</h3>
        <p>重置全部演示数据与演示账号，进入创建管理员流程。</p>
        <button class="button danger-outline" @click="reset">重置演示工作空间</button>
      </section>
    </div>
    <aside class="panel support-panel settings-aside">
      <h2><Icon name="help" :size="18" />关于这些设置</h2>
      <p v-if="tab === 'preferences'">
        时区立即影响内容和投递时间。保留与告警配置仅存储在浏览器，不运行后台任务。
      </p>
      <p v-else-if="tab === 'account'">
        首次初始化直接创建唯一管理员，无初始化令牌。演示密码只保存本地摘要；正式认证仍需服务端会话、CSRF
        与安全密码哈希。
      </p>
      <p v-else-if="tab === 'backup'">
        真实环境恢复需管理员重新验证，并保护数据库与通知加密密钥。本轮只实现演示数据的可运行导入导出流程。
      </p>
      <p v-else>本轮界面延续已确认的暖橙视觉。没有外部字体、分析脚本或真实采集/通知请求。</p>
      <div class="subtle-divider" />
      <p>所有变化仅影响当前浏览器。清除站点数据会恢复初始示例。</p>
    </aside>
  </div>
</template>
