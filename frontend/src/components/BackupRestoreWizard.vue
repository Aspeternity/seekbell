<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { request, restoreBackup, uploadBackup } from '../store'
import { byteSize, stamp } from '../settings'
import { contentRows, count, kindLabels, type BackupEntry, type Inspection } from '../backups'
// Three steps: choose a backup, check it without changing anything, then confirm.
// System settings start from a library entry and keep the current administrator;
// `setup` uploads a file on a fresh installation and restores it under a newly chosen one.
const props = defineProps<{
  setup?: boolean
  entry?: BackupEntry
  needPassword?: boolean
  maxBytes?: number
}>()
const emit = defineEmits<{
  done: [result: { restored: boolean; paused: boolean }]
  cancel: []
  busy: [value: boolean]
  dirty: [value: boolean]
}>()
const steps = ['选择备份', '检查内容', '确认恢复']
const step = ref(props.entry ? 1 : 0)
const file = ref<File>(),
  progress = ref(0),
  inspection = ref<Inspection>(),
  pause = ref(true),
  busy = ref(false),
  error = ref('')
const fields = reactive({ current: '', username: '', adminPassword: '', confirmation: '' })
let active = true
const dirty = computed(() => !!file.value || Object.values(fields).some(Boolean))
watch(dirty, (value) => emit('dirty', value), { immediate: true })
watch(busy, (value) => emit('busy', value))
const ready = computed(() =>
  props.setup
    ? !!fields.username && !!fields.adminPassword && !!fields.confirmation
    : !props.needPassword || !!fields.current,
)
const created = computed(() =>
  inspection.value ? stamp(Date.parse(inspection.value.backup.created_at) / 1000) : '',
)
function fail(e: unknown) {
  if (active) error.value = (e as Error).message
}
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
  error.value = ''
}
async function inspectFile() {
  if (!file.value || busy.value) return
  if (props.maxBytes && file.value.size > props.maxBytes) {
    error.value = '备份超过支持上限。'
    return
  }
  busy.value = true
  error.value = ''
  progress.value = 0
  try {
    const result = await uploadBackup<Inspection>(
      'auth/setup/inspect',
      file.value,
      (share) => (progress.value = share),
    )
    if (!active) return
    inspection.value = result
    step.value = 1
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}
async function inspectEntry() {
  if (!props.entry) return
  busy.value = true
  error.value = ''
  try {
    const result = await request<Inspection>(
      'manage/backups/' + encodeURIComponent(props.entry.id) + '/inspect',
      'POST',
    )
    if (active) inspection.value = result
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}
function release() {
  // An abandoned upload is removed now instead of waiting for it to expire.
  const stage = inspection.value?.stage
  if (stage && !props.setup)
    void request('manage/backups/inspect/' + stage, 'DELETE').catch(() => {})
  inspection.value = undefined
}
function back() {
  error.value = ''
  if (step.value === 2) step.value = 1
  else if (step.value === 1 && !props.entry) {
    release()
    step.value = 0
  } else cancel()
}
function cancel() {
  if (busy.value) return
  release()
  emit('cancel')
}
function validate() {
  if (!props.setup) return ''
  if (!/^[A-Za-z0-9_-]{3,32}$/.test(fields.username))
    return '用户名应为 3–32 位字母、数字、下划线或短横线。'
  if (fields.adminPassword.length < 8) return '密码应为 8–128 个字符。'
  if (fields.adminPassword !== fields.confirmation) return '两次输入的密码不一致。'
  return ''
}
async function confirm() {
  const stage = inspection.value?.stage
  if (!stage || busy.value || !ready.value) return
  error.value = validate()
  if (error.value) return
  busy.value = true
  try {
    const result = props.setup
      ? await restoreBackup('auth/setup/restore', {
          stage,
          username: fields.username,
          admin_password: fields.adminPassword,
          pause: pause.value,
        })
      : await restoreBackup('manage/backups/inspect/' + stage + '/restore', {
          ...(props.needPassword ? { current_password: fields.current } : {}),
          pause: pause.value,
        })
    Object.assign(fields, { current: '', username: '', adminPassword: '', confirmation: '' })
    file.value = undefined
    inspection.value = undefined
    emit('done', result)
  } catch (e) {
    fail(e)
  } finally {
    fields.current = ''
    if (active) busy.value = false
  }
}
onMounted(() => {
  if (props.entry) void inspectEntry()
})
onBeforeUnmount(() => {
  active = false
  if (inspection.value) release()
})
</script>
<template>
  <div class="backup-wizard">
    <ol class="backup-steps" aria-label="恢复步骤">
      <li
        v-for="(label, index) in steps"
        :key="label"
        :class="{ done: index < step, current: index === step }"
        :aria-current="index === step ? 'step' : undefined"
      >
        <span>{{ index + 1 }}</span
        >{{ label }}
      </li>
    </ol>
    <div v-if="error" class="form-errors" role="alert">
      <Icon name="alert" :size="18" />
      <p>{{ error }}</p>
    </div>

    <form
      v-if="step === 0"
      class="form-stack"
      aria-label="选择备份文件"
      @submit.prevent="inspectFile"
    >
      <label class="upload-zone backup-file" :class="{ chosen: !!file }" for="restore-file">
        <Icon name="upload" :size="20" />
        <strong>{{ file ? file.name : '选择备份文件（.tar.gz）' }}</strong>
        <span v-if="file">{{ byteSize(file.size) }} · 点击更换</span>
        <span v-else>只检查，不会改变任何数据</span>
        <input
          id="restore-file"
          type="file"
          accept=".gz,.tar.gz,application/gzip"
          aria-label="备份文件"
          :disabled="busy"
          @change="choose"
        />
      </label>
      <div
        v-if="busy"
        class="backup-progress"
        role="progressbar"
        aria-label="上传进度"
        :aria-valuenow="Math.round(progress * 100)"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: Math.round(progress * 100) + '%' }" />
      </div>
      <div class="backup-wizard-actions">
        <button v-if="!setup" type="button" class="button" :disabled="busy" @click="cancel">
          取消
        </button>
        <button class="button primary" :disabled="busy || !file">
          {{
            busy
              ? progress < 1
                ? '正在上传 ' + Math.round(progress * 100) + '%'
                : '正在检查…'
              : '检查备份'
          }}
        </button>
      </div>
    </form>

    <section v-else-if="step === 1" class="form-stack" aria-label="检查备份内容">
      <p v-if="busy && !inspection" class="small-note">正在检查备份…</p>
      <template v-if="inspection">
        <dl class="detail-grid backup-facts">
          <div>
            <dt>备份时间</dt>
            <dd>{{ created }}</dd>
          </div>
          <div>
            <dt>类型</dt>
            <dd>{{ kindLabels[inspection.backup.kind] }}</dd>
          </div>
          <div>
            <dt>版本</dt>
            <dd>
              {{ inspection.backup.application_version }}
              <span v-if="inspection.backup.upgrade" class="small-badge amber">将自动升级</span>
            </dd>
          </div>
          <div>
            <dt>工作空间</dt>
            <dd>{{ inspection.backup.summary.workspace ?? '—' }}</dd>
          </div>
        </dl>
        <table class="backup-compare">
          <caption class="small-note">
            {{
              inspection.current ? '恢复后，左边的当前数据会被右边的备份内容替换。' : '备份中的内容'
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">内容</th>
              <th v-if="inspection.current" scope="col">当前</th>
              <th scope="col">备份中</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in contentRows" :key="row.key">
              <th scope="row">{{ row.label }}</th>
              <td v-if="inspection.current">{{ count(inspection.current[row.key] as number) }}</td>
              <td>{{ count(inspection.backup.summary[row.key] as number) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <div class="backup-wizard-actions">
        <button type="button" class="button" :disabled="busy" @click="back">
          {{ entry ? '取消' : '换一个文件' }}
        </button>
        <button
          type="button"
          class="button primary"
          :disabled="busy || !inspection"
          @click="step = 2"
        >
          下一步
        </button>
      </div>
    </section>

    <form
      v-else
      class="form-stack backup-restore"
      aria-label="确认恢复"
      novalidate
      @submit.prevent="confirm"
    >
      <p v-if="!setup" class="backup-safety">
        <Icon name="shield" :size="16" />恢复前会先自动备份当前数据。
      </p>
      <div v-if="setup || needPassword" class="settings-fields-grid">
        <div v-if="!setup && needPassword" class="form-stack">
          <label for="restore-current">当前管理员密码</label>
          <input
            id="restore-current"
            v-model="fields.current"
            class="text-input"
            type="password"
            autocomplete="current-password"
            maxlength="128"
            :disabled="busy"
          />
        </div>
        <template v-if="setup">
          <div class="form-stack">
            <label for="restore-username">管理员用户名</label>
            <input
              id="restore-username"
              v-model="fields.username"
              class="text-input"
              autocomplete="username"
              maxlength="32"
              :disabled="busy"
            />
          </div>
          <div class="form-stack">
            <label for="restore-password">设置密码</label>
            <input
              id="restore-password"
              v-model="fields.adminPassword"
              class="text-input"
              type="password"
              autocomplete="new-password"
              maxlength="128"
              :disabled="busy"
            />
          </div>
          <div class="form-stack">
            <label for="restore-confirmation">确认密码</label>
            <input
              id="restore-confirmation"
              v-model="fields.confirmation"
              class="text-input"
              type="password"
              autocomplete="new-password"
              maxlength="128"
              :disabled="busy"
            />
          </div>
        </template>
      </div>
      <label class="check-label"
        ><input v-model="pause" type="checkbox" :disabled="busy" />恢复后暂停采集和通知</label
      >
      <p class="small-note backup-pause-note">
        {{ pause ? '网站和通知目标将暂停，需手动重新开启。' : '如果旧实例仍在运行，会重复通知。' }}
      </p>
      <div class="backup-wizard-actions">
        <button type="button" class="button" :disabled="busy" @click="back">上一步</button>
        <button class="button primary" :disabled="busy || !ready">
          <Icon name="refresh" :size="15" />{{ busy ? '正在恢复…' : '恢复备份' }}
        </button>
      </div>
    </form>
  </div>
</template>
