<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { confirmAction, restoreBackup } from '../store'
// `setup` restores a fresh installation, which has no current administrator to confirm.
const props = defineProps<{ setup?: boolean; maxBytes?: number }>()
const emit = defineEmits<{
  done: [result: { restored: boolean; paused: boolean; previous: string }]
  busy: [value: boolean]
  dirty: [value: boolean]
  failed: []
}>()
const fields = reactive({ current: '', password: '', username: '', adminPassword: '' })
const file = ref<File>(),
  pause = ref(true),
  busy = ref(false),
  error = ref('')
let active = true
onBeforeUnmount(() => {
  active = false
})
const dirty = computed(() => Object.values(fields).some(Boolean) || !!file.value)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
watch(busy, (value) => emit('busy', value))
const size = (bytes: number) => (bytes / 1024 / 1024).toFixed(2) + ' MiB'
function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
}
async function run() {
  if (busy.value || !file.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await restoreBackup(
      props.setup ? 'auth/setup/restore' : 'manage/backups/apply',
      {
        ...(props.setup ? {} : { current_password: fields.current }),
        password: fields.password,
        username: fields.username,
        admin_password: fields.adminPassword,
        pause: pause.value,
      },
      file.value,
    )
    Object.assign(fields, { current: '', password: '', username: '', adminPassword: '' })
    file.value = undefined
    emit('done', result)
  } catch (e) {
    if (active) error.value = (e as Error).message
    emit('failed')
  } finally {
    fields.current = ''
    fields.adminPassword = ''
    if (active) busy.value = false
  }
}
function submit() {
  if (busy.value || !file.value) return
  error.value = ''
  if (props.maxBytes && file.value.size > props.maxBytes) {
    error.value = '备份超过支持上限。'
    return
  }
  if (props.setup) return void run()
  confirmAction(
    '恢复这个备份？',
    '当前的任务、网站、通知目标和历史将被备份内容替换，原数据会保留在服务器数据目录的 before-restore 文件夹中。恢复后需用备份中的管理员重新登录。',
    run,
    '确认恢复',
  )
}
</script>
<template>
  <form
    class="form-stack backup-restore"
    aria-label="从文件恢复"
    novalidate
    @submit.prevent="submit"
  >
    <div v-if="error" class="form-errors" role="alert">
      <Icon name="alert" :size="18" />
      <p>{{ error }}</p>
    </div>
    <label class="upload-zone backup-file" :class="{ chosen: !!file }" for="restore-file">
      <Icon name="upload" :size="20" />
      <strong>{{ file ? file.name : '选择 .sbbackup 备份文件' }}</strong>
      <span v-if="file">{{ size(file.size) }} · 点击更换</span>
      <input
        id="restore-file"
        type="file"
        accept=".sbbackup"
        aria-label="加密备份文件"
        :disabled="busy"
        @change="selectFile"
      />
    </label>
    <div class="settings-fields-grid">
      <div class="form-stack">
        <label for="restore-archive-password">备份加密口令</label>
        <input
          id="restore-archive-password"
          v-model="fields.password"
          class="text-input"
          type="password"
          autocomplete="off"
          maxlength="1024"
          :disabled="busy"
        />
      </div>
      <div v-if="!setup" class="form-stack">
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
      <div class="form-stack">
        <label for="restore-username">备份中的管理员用户名</label>
        <input
          id="restore-username"
          v-model="fields.username"
          class="text-input"
          autocomplete="off"
          maxlength="32"
          :disabled="busy"
        />
      </div>
      <div class="form-stack">
        <label for="restore-password">备份中的管理员密码</label>
        <input
          id="restore-password"
          v-model="fields.adminPassword"
          class="text-input"
          type="password"
          autocomplete="off"
          maxlength="128"
          :disabled="busy"
        />
      </div>
    </div>
    <label class="check-label"
      ><input v-model="pause" type="checkbox" :disabled="busy" />恢复后暂停采集和通知</label
    >
    <p class="small-note backup-pause-note">
      {{
        pause
          ? '所有网站和通知目标恢复为暂停，备份中尚未发出的通知不再发送；确认旧实例已停止后再手动开启。'
          : '恢复后立即按备份中的配置采集和发送；如果旧实例仍在运行，会重复通知。'
      }}
    </p>
    <div class="backup-actions">
      <button
        class="button primary"
        :disabled="busy || !file || !fields.password || !fields.username || !fields.adminPassword"
      >
        <Icon name="refresh" :size="15" />{{ busy ? '正在恢复…' : '恢复备份' }}
      </button>
    </div>
  </form>
</template>
