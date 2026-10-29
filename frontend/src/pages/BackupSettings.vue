<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { formatTime, request, sendRequest } from '../store'
import FormFeedback from '../components/FormFeedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
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
const restoreFields = reactive({ current: '', password: '', username: '', adminPassword: '' })
const file = ref<File>(),
  input = ref<HTMLInputElement>(),
  acknowledged = ref(false)
let active = true
onBeforeUnmount(() => {
  active = false
})
const dirty = computed(
  () =>
    !!busy.value ||
    Object.values(downloadFields).some(Boolean) ||
    Object.values(restoreFields).some(Boolean) ||
    !!file.value,
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
const size = (bytes: number | null) =>
  bytes == null ? '—' : (bytes / 1024 / 1024).toFixed(2) + ' MiB'
const labels: Record<string, string> = {
  generated: '已生成，交给浏览器下载',
  verified: '已验证并生成恢复副本',
  failed: '操作失败',
}
async function load() {
  loading.value = true
  readError.value = ''
  try {
    const value = await request<BackupStatus>('manage/backups')
    if (active) status.value = value
  } catch (e) {
    if (active) readError.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
}
async function download() {
  if (busy.value || !status.value) return
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
        current_password: downloadFields.current,
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
    message.value = '加密备份已生成并交给浏览器下载，请确认文件已保存，并单独保管备份口令。'
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    Object.assign(downloadFields, { current: '', password: '', confirmation: '' })
    busy.value = ''
    if (active) await load()
  }
}
async function restore() {
  if (
    busy.value ||
    !file.value ||
    !status.value ||
    status.value.candidate_available ||
    !acknowledged.value
  )
    return
  error.value = ''
  message.value = ''
  if (file.value.size > status.value.max_archive_bytes) {
    error.value = '备份超过支持上限。'
    return
  }
  busy.value = 'restore'
  try {
    const metadata = JSON.stringify({
      current_password: restoreFields.current,
      password: restoreFields.password,
      username: restoreFields.username,
      admin_password: restoreFields.adminPassword,
    })
    await sendRequest(
      'manage/backups/restore',
      'POST',
      new Blob([metadata + String.fromCharCode(10), file.value], {
        type: 'application/octet-stream',
      }),
    )
    if (active) {
      status.value.candidate_available = true
      message.value = '独立恢复副本已生成，当前工作空间继续运行；副本尚未启用。'
      file.value = undefined
      if (input.value) input.value.value = ''
      acknowledged.value = false
      restoreFields.username = ''
    }
  } catch (e) {
    if (active) error.value = (e as Error).message
  } finally {
    restoreFields.current = ''
    restoreFields.password = ''
    restoreFields.adminPassword = ''
    busy.value = ''
    if (active) await load()
  }
}
onMounted(load)
</script>
<template>
  <div class="settings-columns settings-backup-grid">
    <div class="settings-backup-editor side-stack">
      <div
        v-if="error || readError || message || busy || status?.candidate_available"
        class="settings-backup-feedback"
      >
        <FormFeedback :error="error || readError" @retry="load" />
        <p v-if="status?.candidate_available" class="info-note" role="status">
          已有独立恢复副本，尚未启用。请按维护说明处理后再上传，网页不能覆盖此副本。
        </p>
        <p v-if="message" class="info-note" role="status">{{ message }}</p>
        <p v-if="busy" role="status">
          {{ busy === 'export' ? '正在生成加密备份…' : '正在上传并验证备份…' }} 请保持页面打开。
        </p>
      </div>
      <nav class="segmented compact" aria-label="备份操作">
        <button
          type="button"
          :class="{ active: action === 'export' }"
          :aria-pressed="action === 'export'"
          @click="action = 'export'"
        >
          备份下载
        </button>
        <button
          type="button"
          :class="{ active: action === 'restore' }"
          :aria-pressed="action === 'restore'"
          @click="action = 'restore'"
        >
          恢复验证
        </button>
      </nav>
      <section v-show="action === 'export'" class="panel settings-card">
        <div class="panel-heading"><h2>导出备份</h2></div>
        <form class="form-content form-stack" @submit.prevent="download">
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
          <label for="backup-password">备份加密口令</label>
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
          <p class="small-note">为本次下载设置独立口令，12–1024字符。</p>
          <label for="backup-confirm">确认下载口令</label>
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
          <button class="button primary" :disabled="!!busy || !status">生成并下载加密备份</button>
        </form>
      </section>
      <section v-show="action === 'restore'" class="panel settings-card">
        <div class="panel-heading">
          <div>
            <h2>从文件恢复</h2>
            <p>选择文件 → 验证 → 生成独立副本</p>
          </div>
        </div>
        <div class="form-content form-stack">
          <p>仅支持相同数据库版本。恢复不会覆盖当前数据，也不会启动副本中的采集或发送。</p>
          <p class="warning-note">
            启用副本前必须停止原实例。副本保留原启停配置和待发送队列，可能重复发送；正式切换需按维护说明在宿主机执行。
          </p>
          <form v-if="!status?.candidate_available" class="form-stack" @submit.prevent="restore">
            <label for="restore-file">加密备份文件</label>
            <input
              id="restore-file"
              ref="input"
              class="text-input"
              type="file"
              accept=".sbbackup"
              required
              :disabled="!!busy || !status"
              @change="selectFile"
            />
            <p v-if="file" class="small-note">{{ file.name }} · {{ size(file.size) }}</p>
            <label for="restore-current">当前管理员密码（恢复验证）</label>
            <input
              id="restore-current"
              v-model="restoreFields.current"
              class="text-input"
              type="password"
              autocomplete="current-password"
              maxlength="128"
              required
              :disabled="!!busy"
            />
            <label for="restore-archive-password">所选备份的加密口令</label>
            <input
              id="restore-archive-password"
              v-model="restoreFields.password"
              class="text-input"
              type="password"
              autocomplete="off"
              minlength="12"
              maxlength="1024"
              required
              :disabled="!!busy"
            />
            <label for="restore-username">备份中的管理员用户名</label>
            <input
              id="restore-username"
              v-model="restoreFields.username"
              class="text-input"
              autocomplete="off"
              pattern="[A-Za-z0-9_-]{3,32}"
              required
              :disabled="!!busy"
            />
            <label for="restore-password">备份中的管理员密码</label>
            <input
              id="restore-password"
              v-model="restoreFields.adminPassword"
              class="text-input"
              type="password"
              autocomplete="off"
              maxlength="128"
              required
              :disabled="!!busy"
            />
            <label class="checkbox-row"
              ><input
                v-model="acknowledged"
                type="checkbox"
                required
                :disabled="!!busy"
              />我已了解：只生成独立副本，尚未切换当前工作空间。</label
            >
            <button class="button primary" :disabled="!!busy || !status || !file || !acknowledged">
              验证并生成独立恢复副本
            </button>
          </form>
          <a
            class="text-link"
            href="https://github.com/Aspeternity/seekbell/blob/main/docs/BACKUP_RESTORE.md"
            target="_blank"
            rel="noopener noreferrer"
            >查看副本启用与处理步骤</a
          >
        </div>
      </section>
    </div>
    <div class="side-stack">
      <section class="panel settings-card">
        <div class="panel-heading">
          <div>
            <h2>备份与恢复</h2>
            <p>加密备份与独立恢复副本</p>
          </div>
          <button class="button" :disabled="loading || !!busy" @click="load">刷新备份状态</button>
        </div>
        <div class="form-content form-stack">
          <p>
            备份包含管理员、规则、历史、去重账本、队列和原凭据密钥。下载使用一致性快照，后台继续运行；快照之后的修改和回执不在备份中。
          </p>
          <p class="warning-note">
            请单独保管备份口令，丢失后无法解密。浏览器下载大文件会占用相应内存，数据库最大2
            GiB，大库可使用维护命令。
          </p>
          <a
            class="text-link"
            href="https://github.com/Aspeternity/seekbell/blob/main/docs/BACKUP_RESTORE.md"
            target="_blank"
            rel="noopener noreferrer"
            >查看备份恢复维护说明</a
          >
        </div>
      </section>
      <section class="panel settings-card">
        <div class="panel-heading"><h2>备份与验证记录</h2></div>
        <ReadRegion
          :loading="loading"
          :error="readError"
          :has-data="!!status"
          :min-height="160"
          @retry="load"
        >
          <div v-if="status" class="form-content form-stack">
            <p class="small-note">
              保留最近50次操作。已交给浏览器下载不代表文件已保存。副本验证记录不代表已经启用。
            </p>
            <p v-if="!status.records.length">尚无备份或验证记录。</p>
            <article
              v-for="row in status.records.slice(0, recordsExpanded ? 50 : 5)"
              :key="row.id"
              class="history-evaluation"
            >
              <strong
                >{{ row.kind === 'export' ? '导出备份' : '恢复验证' }} ·
                {{ labels[row.result] }}</strong
              >
              <p>
                {{ formatTime(new Date(row.at * 1000).toISOString()) }} ·
                {{ size(row.archive_bytes) }}
              </p>
              <p class="small-note">
                应用 {{ row.application_version }} · 数据库 {{ row.database_revision }}
              </p>
            </article>
            <button
              v-if="status.records.length > 5"
              class="text-link"
              @click="recordsExpanded = !recordsExpanded"
            >
              {{ recordsExpanded ? '收起记录' : '展开更多记录' }}
            </button>
          </div>
        </ReadRegion>
      </section>
    </div>
  </div>
</template>
