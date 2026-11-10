<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { confirmAction, notify, request } from '../store'
import { byteSize, scrollToSection, stamp } from '../settings'
import {
  STALE_DAYS,
  WEEKDAYS,
  clockText,
  contentsText,
  kindLabels,
  latestBackup,
  type BackupEntry,
  type BackupStatus,
} from '../backups'
import FormFeedback from '../components/FormFeedback.vue'
import Icon from '../components/Icon.vue'
import BackupNameDialog from '../components/BackupNameDialog.vue'
import BackupRestoreWizard from '../components/BackupRestoreWizard.vue'
import BackupScheduleSettings from '../components/BackupScheduleSettings.vue'
const emit = defineEmits<{ dirty: [value: boolean] }>()
const status = ref<BackupStatus>(),
  loading = ref(false),
  readError = ref(''),
  needPassword = ref(true)
// One download, deletion or rename at a time; none asks for the password.
const rowBusy = ref(false)
// The name dialog serves "back up now" (no id) and renaming one backup.
const naming = ref<{ id?: string; initial: string }>(),
  nameBusy = ref(false),
  nameError = ref('')
// The row just created is briefly highlighted.
const fresh = ref('')
// The restore wizard opens for an uploaded file (null) or a library entry.
const restoring = ref<BackupEntry | null>(),
  wizardDirty = ref(false),
  wizardBusy = ref(false),
  restoreDialog = ref<HTMLDialogElement>()
const scheduleDirty = ref(false)
let confirmTimer: ReturnType<typeof setTimeout> | undefined
let freshTimer: ReturnType<typeof setTimeout> | undefined
let active = true
watch(
  () =>
    rowBusy.value || nameBusy.value || wizardDirty.value || wizardBusy.value || scheduleDirty.value,
  (value) => emit('dirty', value),
  { immediate: true },
)
const latest = computed(() => latestBackup(status.value?.backups ?? []))
const health = computed(() => status.value?.health ?? 'none')
const schedule = computed(() => status.value?.schedule)
const scheduleText = computed(() => {
  const value = schedule.value
  if (!value?.enabled) return '自动备份已关闭'
  const when =
    (value.frequency === 'weekly' ? '每' + WEEKDAYS[value.weekday] : '每天') +
    ' ' +
    clockText(value.minute)
  return value.next_run_at ? when + ' · 下次 ' + stamp(value.next_run_at) : when
})
const total = computed(() => (status.value?.backups ?? []).reduce((sum, row) => sum + row.bytes, 0))
const diskUsed = computed(() => {
  const value = status.value
  if (!value?.total_bytes) return 0
  return Math.min(100, Math.max(0, Math.round((1 - value.free_bytes / value.total_bytes) * 100)))
})
function ago(seconds: number) {
  const elapsed = Math.max(0, Date.now() / 1000 - seconds)
  if (elapsed < 3600) return Math.max(1, Math.round(elapsed / 60)) + ' 分钟前'
  if (elapsed < 86400) return Math.round(elapsed / 3600) + ' 小时前'
  return Math.round(elapsed / 86400) + ' 天前'
}
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
function openNaming(row?: BackupEntry) {
  nameError.value = ''
  naming.value = { id: row?.id, initial: row?.name ?? '' }
}
function closeNaming() {
  if (!nameBusy.value) naming.value = undefined
}
async function submitName(name: string) {
  const target = naming.value
  if (!target || nameBusy.value) return
  nameBusy.value = true
  nameError.value = ''
  try {
    if (target.id) {
      await request('manage/backups/' + encodeURIComponent(target.id), 'PATCH', { name })
      notify('名称已保存。')
    } else {
      const { id } = await request<{ id: string }>('manage/backups', 'POST', { name })
      notify('备份已生成并保存在服务器。')
      fresh.value = id
      clearTimeout(freshTimer)
      freshTimer = setTimeout(() => (fresh.value = ''), 2400)
    }
    nameBusy.value = false
    naming.value = undefined
    if (active) await load()
  } catch (e) {
    nameError.value = (e as Error).message
  } finally {
    nameBusy.value = false
  }
}
async function download(id: string) {
  rowBusy.value = true
  try {
    const { url } = await request<{ url: string }>(
      'manage/backups/' + encodeURIComponent(id) + '/ticket',
      'POST',
    )
    // A plain link: the browser streams the file to disk and shows its own progress.
    const link = document.createElement('a')
    link.href = url
    link.download = id
    link.click()
  } catch (e) {
    notify((e as Error).message)
  } finally {
    rowBusy.value = false
    if (active) await load()
  }
}
function askDelete(id: string) {
  confirmAction('删除备份？', '删除后无法恢复。', () => void remove(id), '删除')
}
async function remove(id: string) {
  if (rowBusy.value) return
  rowBusy.value = true
  try {
    await request('manage/backups/' + encodeURIComponent(id), 'DELETE')
    notify('备份已删除。')
  } catch (e) {
    notify((e as Error).message)
  } finally {
    rowBusy.value = false
    if (active) await load()
  }
}
async function copyDirectory() {
  try {
    if (!navigator.clipboard?.writeText) throw new Error()
    await navigator.clipboard.writeText(status.value?.directory ?? '')
    notify('已复制存放位置。')
  } catch {
    notify('复制失败，请手动选取。')
  }
}
async function openWizard(entry: BackupEntry | null) {
  restoring.value = entry
  await nextTick()
  restoreDialog.value?.showModal()
  document.body.classList.add('website-panel-open')
}
function closeWizard() {
  if (wizardBusy.value) return
  restoreDialog.value?.close()
  document.body.classList.remove('website-panel-open')
  restoring.value = undefined
  wizardDirty.value = false
  void load()
}
function dialogCancel(event: Event) {
  // Dismissing the file picker inside fires a bubbling "cancel" too; only Escape closes.
  if (event.target !== restoreDialog.value) return
  event.preventDefault()
  closeWizard()
}
async function restored(result: { paused: boolean }) {
  wizardDirty.value = false
  wizardBusy.value = false
  closeWizard()
  notify(result.paused ? '备份已恢复，采集和通知已暂停。' : '备份已恢复。')
  // Let the cleared draft reach the settings shell before leaving.
  await nextTick()
  location.hash = '/'
}
onMounted(async () => {
  await load()
  await nextTick()
  scrollToSection('list', 'backup-list')
})
onBeforeUnmount(() => {
  active = false
  clearTimeout(confirmTimer)
  clearTimeout(freshTimer)
  document.body.classList.remove('website-panel-open')
})
</script>
<template>
  <div class="settings-stack">
    <section id="backup-settings" class="panel settings-card" aria-labelledby="backup-title">
      <div class="panel-heading">
        <div>
          <h2 id="backup-title">备份状态</h2>
          <p>完整备份配置、规则、通知目标与历史</p>
        </div>
        <div class="backup-heading-actions">
          <button class="button" type="button" @click="openWizard(null)">
            <Icon name="upload" :size="15" />从文件恢复
          </button>
          <button class="button primary" type="button" @click="openNaming()">
            <Icon name="download" :size="15" />立即备份
          </button>
        </div>
      </div>
      <FormFeedback :error="readError" :retryable="!!readError && !status" @retry="load" />
      <div v-if="status" class="form-content backup-overview">
        <dl class="about-tiles backup-tiles">
          <div class="backup-health" :class="health">
            <dt>
              <span class="about-tile-icon"><Icon name="clock" :size="16" /></span>上次备份
            </dt>
            <dd>
              <span class="backup-health-value"
                ><span class="status-dot" />{{ latest ? ago(latest.at) : '还没有备份' }}</span
              >
              <small v-if="latest"
                >{{ stamp(latest.at) }} · {{ kindLabels[latest.kind!]
                }}<template v-if="health === 'overdue'">
                  ·
                  {{
                    schedule?.enabled ? '已超过两个周期' : '已超过 ' + STALE_DAYS + ' 天'
                  }}</template
                ></small
              >
              <small v-else>建议现在备份一次</small>
              <small v-if="health === 'failed'" class="backup-failure" role="alert"
                >自动备份失败：{{ schedule?.last_error }}</small
              >
              <small class="backup-next">{{ scheduleText }}</small>
            </dd>
          </div>
          <div>
            <dt>
              <span class="about-tile-icon"><Icon name="layers" :size="16" /></span>已存备份
            </dt>
            <dd>
              {{ status.backups.length }} 份
              <small v-if="status.backups.length">共 {{ byteSize(total) }}</small>
              <small class="backup-directory" :title="status.directory">
                <Icon name="folder" :size="13" /><span>{{ status.directory }}</span>
                <button
                  class="icon-button backup-copy"
                  type="button"
                  aria-label="复制存放位置"
                  title="复制存放位置"
                  @click="copyDirectory"
                >
                  <Icon name="copy" :size="13" />
                </button>
              </small>
            </dd>
          </div>
          <div>
            <dt>
              <span class="about-tile-icon"><Icon name="database" :size="16" /></span>磁盘可用
            </dt>
            <dd>
              {{ byteSize(status.free_bytes) }}
              <span
                class="about-meter"
                role="meter"
                aria-label="磁盘已用"
                :aria-valuenow="diskUsed"
                aria-valuemin="0"
                aria-valuemax="100"
                ><span :style="{ width: diskUsed + '%' }"
              /></span>
              <small>共 {{ byteSize(status.total_bytes) }} · 已用 {{ diskUsed }}%</small>
            </dd>
          </div>
        </dl>
      </div>
    </section>

    <section id="backup-list" class="panel settings-card" aria-labelledby="backup-list-title">
      <div class="panel-heading">
        <div>
          <h2 id="backup-list-title">备份列表</h2>
          <p>恢复前会先自动备份当前数据；恢复前的备份保留 30 天</p>
        </div>
      </div>
      <div class="form-content">
        <p v-if="loading && !status" class="small-note">正在读取…</p>
        <div v-else-if="status && !status.backups.length" class="backup-empty">
          <span class="about-tile-icon"><Icon name="inbox" :size="20" /></span>
          <strong>还没有备份</strong>
          <button class="button primary" type="button" @click="openNaming()">
            <Icon name="download" :size="15" />立即备份
          </button>
        </div>
        <ul v-if="status?.backups.length" class="backup-list">
          <li v-for="row in status.backups" :key="row.id" :class="{ fresh: fresh === row.id }">
            <div class="backup-row">
              <div class="backup-row-main">
                <strong>{{ row.name || stamp(row.at) }}</strong>
                <button
                  v-if="row.valid"
                  type="button"
                  class="icon-button backup-rename"
                  :disabled="rowBusy"
                  :aria-label="'重命名 ' + row.id"
                  title="重命名"
                  @click="openNaming(row)"
                >
                  <Icon name="edit" :size="14" />
                </button>
              </div>
              <span class="backup-row-meta">
                <span
                  v-if="row.valid"
                  class="small-badge"
                  :class="row.kind === 'manual' ? 'neutral' : 'amber'"
                  >{{ kindLabels[row.kind!] }}</span
                >
                <span v-else class="small-badge rose">无法识别</span>
                <span
                  ><template v-if="row.name">{{ stamp(row.at) }} · </template
                  >{{ byteSize(row.bytes)
                  }}<template v-if="row.valid">
                    · v{{ row.application_version }} · {{ contentsText(row.summary) }}</template
                  ></span
                >
              </span>
              <div class="backup-row-actions">
                <button
                  type="button"
                  class="button"
                  :disabled="rowBusy"
                  :aria-label="'下载 ' + row.id"
                  @click="download(row.id)"
                >
                  <Icon name="download" :size="14" />下载
                </button>
                <button
                  v-if="row.valid"
                  type="button"
                  class="button"
                  :disabled="rowBusy"
                  :aria-label="'恢复 ' + row.id"
                  @click="openWizard(row)"
                >
                  <Icon name="refresh" :size="14" />恢复
                </button>
                <button
                  type="button"
                  class="button danger-outline"
                  :disabled="rowBusy"
                  :aria-label="'删除 ' + row.id"
                  @click="askDelete(row.id)"
                >
                  <Icon name="trash" :size="14" />删除
                </button>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </section>

    <BackupScheduleSettings @dirty="scheduleDirty = $event" @saved="load" />

    <BackupNameDialog
      v-if="naming"
      :title="naming.id ? '重命名备份' : '立即备份'"
      :action="naming.id ? '保存' : '备份'"
      :busy-action="naming.id ? '正在保存…' : '正在备份…'"
      :initial="naming.initial"
      :busy="nameBusy"
      :error="nameError"
      @submit="submitName"
      @close="closeNaming"
    />

    <dialog
      ref="restoreDialog"
      class="website-drawer backup-restore-modal"
      aria-label="恢复备份"
      @cancel="dialogCancel"
      @click="
        (event) => {
          if (event.target === restoreDialog) closeWizard()
        }
      "
    >
      <div class="website-drawer-shell">
        <header class="website-drawer-header">
          <div>
            <h2>恢复备份</h2>
            <p>用备份替换当前的任务、网站、通知目标和历史，服务不中断</p>
          </div>
          <button
            class="icon-button"
            aria-label="关闭恢复备份"
            :disabled="wizardBusy"
            @click="closeWizard"
          >
            <Icon name="close" :size="21" />
          </button>
        </header>
        <div class="website-drawer-body">
          <BackupRestoreWizard
            v-if="restoring !== undefined"
            :entry="restoring ?? undefined"
            :need-password="needPassword"
            :max-bytes="status?.max_upload_bytes"
            @busy="wizardBusy = $event"
            @dirty="wizardDirty = $event"
            @cancel="closeWizard"
            @done="restored"
          />
        </div>
      </div>
    </dialog>
  </div>
</template>
