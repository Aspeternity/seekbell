<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { notify, request, sendRequest } from '../store'
import { byteSize, scrollToSection, stamp } from '../settings'
import type { BackupStatus } from '../backups'
import FormFeedback from '../components/FormFeedback.vue'
import Icon from '../components/Icon.vue'
import BackupRestoreForm from '../components/BackupRestoreForm.vue'
import RestoreLeftovers from '../components/RestoreLeftovers.vue'
const emit = defineEmits<{ dirty: [value: boolean] }>()
// Backup status is shared: the backup forms and the leftover list all ask for the
// administrator password, and one recent entry covers them all.
const status = ref<BackupStatus>(),
  loading = ref(false),
  readError = ref(''),
  needPassword = ref(true)
let confirmTimer: ReturnType<typeof setTimeout> | undefined
async function load() {
  loading.value = true
  readError.value = ''
  try {
    const value = await request<BackupStatus>('manage/backups')
    if (!active) return
    status.value = value
    clearTimeout(confirmTimer)
    needPassword.value = value.confirm_seconds <= 0
    if (value.confirm_seconds > 0)
      confirmTimer = setTimeout(() => (needPassword.value = true), value.confirm_seconds * 1000)
  } catch (e) {
    if (active) readError.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await load()
  await nextTick()
  scrollToSection('leftovers', 'restore-leftovers')
})
const action = ref('export')
const busy = ref(false),
  error = ref(''),
  message = ref('')
const downloadFields = reactive({ current: '', password: '', confirmation: '' })
const restoreDirty = ref(false),
  restoring = ref(false),
  leftoversDirty = ref(false)
let active = true
onBeforeUnmount(() => {
  active = false
  clearTimeout(confirmTimer)
})
const dirty = computed(
  () =>
    busy.value ||
    restoring.value ||
    Object.values(downloadFields).some(Boolean) ||
    restoreDirty.value ||
    leftoversDirty.value,
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
const labels: Record<string, string> = {
  generated: '已生成',
  verified: '已生成副本',
  failed: '失败',
  deleted: '已删除',
  restored: '已恢复',
}
const kinds: Record<string, string> = {
  export: '导出备份',
  restore: '恢复备份',
  discard: '删除残留',
}
function select(value: string) {
  action.value = value
  error.value = ''
  message.value = ''
}
async function download() {
  if (busy.value) return
  error.value = ''
  message.value = ''
  if (downloadFields.password !== downloadFields.confirmation) {
    error.value = '两次备份口令不一致。'
    return
  }
  busy.value = true
  try {
    const response = await sendRequest(
      'manage/backups/download',
      'POST',
      JSON.stringify({
        ...(needPassword.value ? { current_password: downloadFields.current } : {}),
        password: downloadFields.password,
      }),
      'application/json',
    )
    const blob = await response.blob()
    if (!active) return
    const url = URL.createObjectURL(blob),
      link = document.createElement('a')
    link.href = url
    link.download =
      'seekbell-' +
      new Date().toISOString().slice(0, 19).split('-').join('').split(':').join('') +
      'Z.sbbackup'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
    Object.assign(downloadFields, { password: '', confirmation: '' })
    message.value = '备份已交给浏览器下载，请确认文件已保存。'
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    downloadFields.current = ''
    busy.value = false
    if (active) void load()
  }
}
async function restored(result: { paused: boolean }) {
  restoreDirty.value = false
  restoring.value = false
  notify(result.paused ? '备份已恢复，采集和通知已暂停。' : '备份已恢复。')
  // Let the cleared draft reach the settings shell before leaving.
  await nextTick()
  location.hash = '/'
}
</script>
<template>
  <div class="settings-stack">
    <section id="backup-settings" class="panel settings-card" aria-labelledby="backup-title">
      <div class="panel-heading">
        <div>
          <h2 id="backup-title">备份与恢复</h2>
          <p>加密备份全部配置、规则与历史</p>
        </div>
        <nav class="segmented compact backup-switch" aria-label="备份操作">
          <button
            type="button"
            :class="{ active: action === 'export' }"
            :aria-pressed="action === 'export'"
            :disabled="busy || restoring"
            @click="select('export')"
          >
            备份下载
          </button>
          <button
            type="button"
            :class="{ active: action === 'restore' }"
            :aria-pressed="action === 'restore'"
            :disabled="busy || restoring"
            @click="select('restore')"
          >
            恢复备份
          </button>
        </nav>
      </div>
      <FormFeedback :error="error || readError" :retryable="!error && !!readError" @retry="load" />
      <form
        v-show="action === 'export'"
        class="form-content form-stack"
        aria-label="导出备份"
        @submit.prevent="download"
      >
        <div class="settings-fields-grid" :class="{ three: needPassword }">
          <div v-if="needPassword" class="form-stack">
            <label for="backup-current">当前管理员密码</label>
            <input
              id="backup-current"
              v-model="downloadFields.current"
              class="text-input"
              type="password"
              autocomplete="current-password"
              maxlength="128"
              required
              :disabled="busy"
            />
          </div>
          <div class="form-stack">
            <label for="backup-password">备份口令</label>
            <input
              id="backup-password"
              v-model="downloadFields.password"
              class="text-input"
              type="password"
              autocomplete="off"
              minlength="12"
              maxlength="1024"
              required
              :disabled="busy"
            />
            <p class="small-note">至少 12 个字符，丢失后无法解密</p>
          </div>
          <div class="form-stack">
            <label for="backup-confirm">确认备份口令</label>
            <input
              id="backup-confirm"
              v-model="downloadFields.confirmation"
              class="text-input"
              type="password"
              autocomplete="off"
              minlength="12"
              maxlength="1024"
              required
              :disabled="busy"
            />
          </div>
        </div>
        <div class="backup-actions">
          <button class="button primary" :disabled="busy">
            <Icon name="download" :size="15" />{{
              busy ? '正在生成加密备份…' : '生成并下载加密备份'
            }}
          </button>
          <p v-if="message" class="backup-done" role="status">
            <Icon name="check" :size="15" />{{ message }}
          </p>
        </div>
      </form>
      <div v-show="action === 'restore'" class="form-content form-stack">
        <p class="settings-body-text">
          用备份替换当前的任务、网站、通知目标和历史，服务不中断。较旧版本的备份会自动升级。
        </p>
        <BackupRestoreForm
          :need-password="needPassword"
          :max-bytes="status?.max_archive_bytes"
          @busy="restoring = $event"
          @dirty="restoreDirty = $event"
          @done="restored"
          @failed="load"
        />
      </div>
      <details v-if="status?.records.length" class="settings-details backup-history">
        <summary>操作记录（最近 {{ status.records.length }} 次）</summary>
        <ul class="backup-records">
          <li v-for="row in status.records" :key="row.id">
            <span class="backup-kind">{{ kinds[row.kind] }}</span>
            <span class="backup-result" :class="row.result">{{ labels[row.result] }}</span>
            <span>{{ stamp(row.at) }}</span>
            <span>{{ byteSize(row.archive_bytes) }}</span>
            <span class="backup-version">v{{ row.application_version }}</span>
          </li>
        </ul>
      </details>
    </section>
    <RestoreLeftovers
      v-if="status"
      :leftovers="status.leftovers"
      :need-password="needPassword"
      @dirty="leftoversDirty = $event"
      @changed="load"
    />
  </div>
</template>
