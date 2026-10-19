<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput, NInputNumber, NTag } from 'naive-ui'
import { request } from '../api'
import type { VersionInfo } from '../api'
import {
  browserTimezone,
  getSettings,
  getTargets,
  getTimezones,
  localDate,
  message,
  setDisplayTimezone,
  write,
} from '../management'
import type { SystemSettings, Target } from '../management'
const props = defineProps<{ csrf: string }>()
const emit = defineEmits<{ accountUpdated: [] }>()
const settings = ref<SystemSettings | null>(null)
const targets = ref<Target[]>([])
const version = ref<VersionInfo | null>(null)
const zones = ref<string[]>([])
const timezone = ref(browserTimezone)
const days = ref<number | null>(30)
const alertTargetId = ref<string>('')
const name = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const loading = ref(false)
const busy = ref(false)
const cleanupConfirm = ref(false)
const error = ref('')
const notice = ref('')
const labels: Record<string, string> = {
  posts: '本地帖子',
  outbox: '已结束自动投递',
  rule_hits: '命中记录',
  source_runs: '采集历史',
  manual_delivery_attempts: '手动重发',
  target_test_attempts: '目标测试',
}
function clearPasswords() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmation.value = ''
}
async function load() {
  if (busy.value || loading.value) return
  loading.value = true
  error.value = ''
  cleanupConfirm.value = false
  try {
    const [value, options, info, availableTargets] = await Promise.all([
      getSettings(),
      getTimezones(),
      request<VersionInfo>('/api/version'),
      getTargets(),
    ])
    settings.value = value
    zones.value = options
    version.value = info
    targets.value = availableTargets
    timezone.value = value.timezone ?? (options.includes(browserTimezone) ? browserTimezone : 'UTC')
    days.value = value.retention_days
    alertTargetId.value = value.alert_target_id ?? ''
    name.value = value.username
    setDisplayTimezone(value.timezone)
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}
async function save() {
  if (!settings.value || busy.value || days.value === null) return
  busy.value = true
  error.value = notice.value = ''
  cleanupConfirm.value = false
  try {
    settings.value = await write<SystemSettings>(
      '/settings',
      'PUT',
      {
        expected_revision: settings.value.revision,
        timezone: timezone.value,
        retention_days: days.value,
        alert_target_id: alertTargetId.value || null,
      },
      props.csrf,
    )
    alertTargetId.value = settings.value.alert_target_id ?? ''
    setDisplayTimezone(settings.value.timezone)
    notice.value = '显示与保留设置已保存。后台维护将按新天数分批清理。'
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function cleanup() {
  if (!settings.value || busy.value) return
  busy.value = true
  error.value = notice.value = ''
  try {
    const result = await write<{ counts: Record<string, number> }>(
      '/settings/cleanup',
      'POST',
      { expected_revision: settings.value.revision, confirmed: true },
      props.csrf,
    )
    settings.value = await getSettings()
    notice.value =
      '本批清理完成：' +
      Object.entries(result.counts)
        .map(([key, count]) => (labels[key] ?? key) + ' ' + count)
        .join('，') +
      '。'
    cleanupConfirm.value = false
  } catch (cause) {
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function changeAccount() {
  if (busy.value) return
  error.value = notice.value = ''
  if (newPassword.value !== confirmation.value) {
    error.value = '两次输入的新密码不一致。'
    return
  }
  busy.value = true
  try {
    await write(
      '/account',
      'PUT',
      {
        username: name.value,
        current_password: currentPassword.value,
        ...(newPassword.value ? { new_password: newPassword.value } : {}),
      },
      props.csrf,
    )
    clearPasswords()
    emit('accountUpdated')
  } catch (cause) {
    error.value = message(cause)
  } finally {
    clearPasswords()
    busy.value = false
  }
}
onMounted(load)
onUnmounted(clearPasswords)
</script>
<template>
  <section aria-label="系统设置" :aria-busy="loading || busy">
    <div class="panel-heading">
      <h2>系统设置</h2>
      <NButton :loading="loading" :disabled="busy" @click="load">重新读取设置</NButton>
    </div>
    <NAlert v-if="error" type="error" class="notice">{{ error }}</NAlert
    ><NAlert v-if="notice" type="success" class="notice">{{ notice }}</NAlert>
    <div class="split-grid">
      <NCard v-if="settings" title="显示与历史保留" class="record-card">
        <NForm @submit.prevent="save"
          ><div class="form-grid">
            <NFormItem label="显示时区" :label-props="{ for: 'settings-zone' }"
              ><select id="settings-zone" v-model="timezone" class="native-select" :disabled="busy">
                <option v-for="zone in zones" :key="zone" :value="zone">{{ zone }}</option>
              </select></NFormItem
            >
            <NFormItem label="普通历史保留天数" :label-props="{ for: 'settings-days' }"
              ><NInputNumber
                v-model:value="days"
                :min="1"
                :max="3650"
                :precision="0"
                :disabled="busy"
                :input-props="{ id: 'settings-days', required: true }"
            /></NFormItem>
            <NFormItem label="系统故障告警目标" :label-props="{ for: 'settings-alert-target' }"
              ><select
                id="settings-alert-target"
                v-model="alertTargetId"
                class="native-select"
                :disabled="busy"
              >
                <option value="">无（仅网页提示）</option>
                <option v-for="t in targets" :key="t.id" :value="t.id">
                  {{ t.name }}{{ t.enabled ? '' : '（已停用）' }}
                </option>
              </select></NFormItem
            >
          </div>
          <p class="muted">
            未保存时区时使用浏览器时区，当前浏览器为 {{ browserTimezone }}。时间始终以 UTC
            存储，显示设置不改变通知快照与采集计划。
          </p>
          <NAlert type="warning" class="notice"
            >保存较短保留期后，后台维护会自动删除过期普通历史。独立已见/已发身份账本永久保留；等待、重试、在途和存在结果不确定性的投递及其关联内容保留。近期重发或迟到结果也会延后原记录清理。</NAlert
          >
          <div class="actions">
            <NButton type="primary" attr-type="submit" :loading="busy" :disabled="days === null"
              >保存显示与保留设置</NButton
            ><NButton :disabled="busy" @click="timezone = browserTimezone">使用浏览器时区</NButton>
          </div></NForm
        >
        <div class="kv-grid">
          <div class="kv-box">
            <p>最近清理：{{ localDate(settings.last_cleanup_at) }}</p>
          </div>
          <div v-for="(count, key) in settings.last_cleanup_counts" :key="key" class="kv-box">
            <p>{{ labels[key] ?? key }}：{{ count }}</p>
          </div>
        </div>
        <p class="muted">
          后台调度开启时每分钟执行一批，每类主记录最多 200
          条，关联尝试与贡献一并清理；不会清理未保存草稿所选天数，也不保证立即缩小 SQLite
          文件。备份或导出前先考虑所需历史。
        </p>
        <NAlert v-if="!settings.scheduler.enabled" type="info" class="notice"
          >后台维护由启动配置关闭，可显式清理一批。</NAlert
        >
        <NButton :disabled="busy" @click="cleanupConfirm = true">清理一批过期历史</NButton>
        <NAlert v-if="cleanupConfirm" type="warning" class="notice"
          ><p>
            按已保存的
            {{ settings.retention_days }}
            天清理普通历史，本操作不可恢复；去重账本和未完成/不确定投递仍保留。
          </p>
          <div class="actions">
            <NButton :loading="busy" @click="cleanup">确认清理一批</NButton
            ><NButton :disabled="busy" @click="cleanupConfirm = false">取消清理</NButton>
          </div></NAlert
        >
      </NCard>
      <NCard v-if="settings" title="管理员账号" class="record-card">
        <p class="muted">
          需要当前密码验证。修改后撤销全部已登录会话，请用更新后的账号重新登录；新密码留空只修改用户名。
        </p>
        <NForm @submit.prevent="changeAccount">
          <NFormItem label="管理员用户名" :label-props="{ for: 'account-name' }"
            ><NInput
              v-model:value="name"
              :maxlength="64"
              :disabled="busy"
              :input-props="{ id: 'account-name', required: true, autocomplete: 'username' }"
          /></NFormItem>
          <NFormItem label="当前密码" :label-props="{ for: 'account-current' }"
            ><NInput
              v-model:value="currentPassword"
              type="password"
              :maxlength="128"
              :disabled="busy"
              :input-props="{
                id: 'account-current',
                required: true,
                autocomplete: 'current-password',
              }"
          /></NFormItem>
          <NFormItem label="新密码（可留空）" :label-props="{ for: 'account-new' }"
            ><NInput
              v-model:value="newPassword"
              type="password"
              :minlength="15"
              :maxlength="128"
              :disabled="busy"
              :input-props="{ id: 'account-new', autocomplete: 'new-password' }"
          /></NFormItem>
          <NFormItem label="再次输入新密码" :label-props="{ for: 'account-confirm' }"
            ><NInput
              v-model:value="confirmation"
              type="password"
              :minlength="15"
              :maxlength="128"
              :disabled="busy"
              :input-props="{ id: 'account-confirm', autocomplete: 'new-password' }"
          /></NFormItem>
          <NButton attr-type="submit" type="primary" :loading="busy"
            >保存账号并退出所有会话</NButton
          >
        </NForm>
      </NCard>
    </div>
    <div class="split-grid" style="margin-top: 16px">
      <NCard title="备份与恢复" class="record-card"
        ><p class="muted">
          完整备份通过停服维护命令生成，包含账号、历史、去重账本、通知凭据及原密钥，并用独立口令加密。恢复时验证备份中的管理员密码，只能写入空数据目录，完成后须重新登录。部署操作见随版本提供的备份恢复文档；请先在独立环境验证，再切换日常数据卷。
        </p></NCard
      >
      <NCard v-if="version" title="版本与运行状态" class="record-card">
        <div class="record-meta">
          <NTag :type="settings?.scheduler.healthy ? 'success' : 'error'">{{
            settings?.scheduler.healthy ? '后台组件正常' : '后台组件异常'
          }}</NTag>
        </div>
        <div class="kv-grid">
          <div class="kv-box">
            <p>应用版本：{{ version.version }}</p>
          </div>
          <div class="kv-box">
            <p>
              代码版本：<code>{{ version.build_revision }}</code>
            </p>
          </div>
          <div class="kv-box">
            <p>
              数据库迁移：<code>{{ version.database_revision }}</code>
            </p>
          </div>
        </div>
      </NCard>
    </div>
  </section>
</template>
