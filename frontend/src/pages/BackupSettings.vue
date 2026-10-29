<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { formatTime, notify, request, sendRequest } from '../store'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import Icon from '../components/Icon.vue'
import BackupRestoreForm from '../components/BackupRestoreForm.vue'
interface BackupRecord {
  id: string
  kind: string
  result: string
  at: number
  archive_bytes: number | null
  application_version: string
  database_revision: string
}
interface BackupStatus {
  confirm_seconds: number
  candidate_available: boolean
  max_archive_bytes: number
  records: BackupRecord[]
}
const emit = defineEmits<{ dirty: [value: boolean] }>()
const action = ref('export'),
  recordsExpanded = ref(false)
const status = ref<BackupStatus>(),
  loading = ref(false),
  busy = ref(''),
  error = ref(''),
  readError = ref(''),
  message = ref('')
const downloadFields = reactive({ current: '', password: '', confirmation: '' })
const discarding = ref(false),
  discardPassword = ref(''),
  restoreDirty = ref(false),
  restoring = ref(false)
// The server skips the password shortly after it was entered; ask again once that lapses.
const needPassword = ref(true)
let confirmTimer: ReturnType<typeof setTimeout> | undefined
function trackConfirmation(seconds: number) {
  clearTimeout(confirmTimer)
  needPassword.value = seconds <= 0
  if (seconds > 0) confirmTimer = setTimeout(() => (needPassword.value = true), seconds * 1000)
}
const currentPassword = (value: string) => (needPassword.value ? { current_password: value } : {})
let active = true
onBeforeUnmount(() => {
  active = false
  clearTimeout(confirmTimer)
})
const dirty = computed(
  () =>
    !!busy.value ||
    restoring.value ||
    Object.values(downloadFields).some(Boolean) ||
    restoreDirty.value ||
    !!discardPassword.value,
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
const size = (bytes: number | null) =>
  bytes == null ? '—' : (bytes / 1024 / 1024).toFixed(2) + ' MiB'
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
  discard: '删除副本',
}
function select(value: string) {
  action.value = value
  error.value = ''
  message.value = ''
}
async function load() {
  loading.value = true
  readError.value = ''
  try {
    const value = await request<BackupStatus>('manage/backups')
    if (active) {
      status.value = value
      trackConfirmation(value.confirm_seconds)
    }
  } catch (e) {
    if (active) readError.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
async function download() {
  if (busy.value) return
  error.value = ''
  message.value = ''
  if (downloadFields.password !== downloadFields.confirmation) {
    error.value = '两次备份口令不一致。'
    return
  }
  busy.value = 'export'
  try {
    const response = await sendRequest(
      'manage/backups/download',
      'POST',
      JSON.stringify({
        ...currentPassword(downloadFields.current),
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
    busy.value = ''
    if (active) await load()
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
async function discard() {
  if (busy.value || !status.value?.candidate_available) return
  error.value = ''
  message.value = ''
  busy.value = 'discard'
  try {
    await request('manage/backups/candidate', 'DELETE', currentPassword(discardPassword.value))
    if (active) {
      status.value.candidate_available = false
      discarding.value = false
      message.value = '恢复副本已删除。'
      action.value = 'restore'
    }
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    discardPassword.value = ''
    busy.value = ''
    if (active) await load()
  }
}
onMounted(load)
</script>
<template>
  <div class="settings-stack">
    <section class="panel settings-card" aria-labelledby="backup-title">
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
            :disabled="!!busy || restoring"
            @click="select('export')"
          >
            备份下载
          </button>
          <button
            type="button"
            :class="{ active: action === 'restore' }"
            :aria-pressed="action === 'restore'"
            :disabled="!!busy || restoring"
            @click="select('restore')"
          >
            恢复备份
          </button>
        </nav>
      </div>
      <FormFeedback :error="error || readError" @retry="load" />
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
              :disabled="!!busy"
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
              :disabled="!!busy"
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
              :disabled="!!busy"
            />
          </div>
        </div>
        <div class="backup-actions">
          <button class="button primary" :disabled="!!busy">
            <Icon name="download" :size="15" />{{
              busy === 'export' ? '正在生成加密备份…' : '生成并下载加密备份'
            }}
          </button>
          <p v-if="message && action === 'export'" class="backup-done" role="status">
            <Icon name="check" :size="15" />{{ message }}
          </p>
        </div>
      </form>
      <div v-show="action === 'restore'" class="form-content form-stack">
        <p class="settings-body-text">
          用备份替换当前的任务、网站、通知目标和历史，服务不中断。较旧版本的备份会自动升级。
        </p>
        <p v-if="message && action === 'restore'" class="backup-done" role="status">
          <Icon name="check" :size="15" />{{ message }}
        </p>
        <div v-if="status?.candidate_available" class="info-note backup-candidate">
          <div class="backup-candidate-row">
            <p role="status">
              服务器上保留着一份之前“恢复验证”生成的独立恢复副本，不需要可以删除。
            </p>
            <button
              v-if="!discarding"
              type="button"
              class="button danger-outline"
              :disabled="!!busy"
              @click="discarding = true"
            >
              <Icon name="trash" :size="14" />删除恢复副本
            </button>
          </div>
          <form
            v-if="discarding"
            class="backup-discard"
            aria-label="删除恢复副本"
            @submit.prevent="discard"
          >
            <template v-if="needPassword">
              <label for="discard-current">当前管理员密码</label>
              <input
                id="discard-current"
                v-model="discardPassword"
                class="text-input"
                type="password"
                autocomplete="current-password"
                maxlength="128"
                required
                :disabled="!!busy"
              />
            </template>
            <button
              class="button danger-outline"
              :disabled="!!busy || (needPassword && !discardPassword)"
            >
              {{ busy === 'discard' ? '正在删除…' : '确认删除' }}
            </button>
            <button
              type="button"
              class="button"
              :disabled="!!busy"
              @click="((discarding = false), (discardPassword = ''))"
            >
              取消
            </button>
            <p class="small-note">删除后无法恢复，当前数据不受影响。</p>
          </form>
        </div>
        <BackupRestoreForm
          :need-password="needPassword"
          :max-bytes="status?.max_archive_bytes"
          @busy="restoring = $event"
          @dirty="restoreDirty = $event"
          @done="restored"
          @failed="load"
        />
      </div>
    </section>
    <section class="panel settings-card" aria-labelledby="backup-records-title">
      <div class="panel-heading"><h2 id="backup-records-title">备份与恢复记录</h2></div>
      <ReadRegion
        :loading="loading"
        :error="readError"
        :has-data="!!status"
        :min-height="120"
        @retry="load"
      >
        <div v-if="status" class="form-content form-stack">
          <p v-if="!status.records.length" class="small-note">暂无记录</p>
          <ul v-else class="backup-records">
            <li v-for="row in status.records.slice(0, recordsExpanded ? 50 : 5)" :key="row.id">
              <span class="backup-kind">{{ kinds[row.kind] }}</span>
              <span class="backup-result" :class="row.result">{{ labels[row.result] }}</span>
              <span>{{ formatTime(new Date(row.at * 1000).toISOString()) }}</span>
              <span>{{ size(row.archive_bytes) }}</span>
              <span class="backup-version" :title="'数据库 ' + row.database_revision"
                >v{{ row.application_version }}</span
              >
            </li>
          </ul>
          <button
            v-if="status.records.length > 5"
            class="text-link"
            @click="recordsExpanded = !recordsExpanded"
          >
            {{ recordsExpanded ? '收起' : '查看更多（共 ' + status.records.length + ' 条）' }}
          </button>
        </div>
      </ReadRegion>
    </section>
  </div>
</template>
