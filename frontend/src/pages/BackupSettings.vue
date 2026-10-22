<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { request, sendRequest, state } from '../store'
import Icon from '../components/Icon.vue'
import { historyGet, useRemote } from '../history'
import type { Page } from '../history'
const totals = useRemote(
  async () => {
    const [posts, deliveries] = await Promise.all([
      historyGet<Page<unknown>>('posts', { page_size: 1 }),
      historyGet<Page<unknown>>('deliveries', { page_size: 1 }),
    ])
    return { posts: posts.total, deliveries: deliveries.total }
  },
  () => [],
)
const emit = defineEmits<{ dirty: [value: boolean] }>()
const currentPassword = ref(''),
  password = ref(''),
  confirmation = ref('')
const username = ref(''),
  adminPassword = ref('')
const file = ref<File>(),
  input = ref<HTMLInputElement>()
const busy = ref(false),
  error = ref(''),
  message = ref('')
const candidate = ref(false),
  loaded = ref(false),
  acknowledged = ref(false)
const maxArchive = ref(0)
const dirty = computed(
  () =>
    busy.value ||
    !!(
      currentPassword.value ||
      password.value ||
      confirmation.value ||
      username.value ||
      adminPassword.value ||
      file.value
    ),
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })
async function load() {
  try {
    const status = await request<{ candidate_available: boolean; max_archive_bytes: number }>(
      'manage/backups',
    )
    candidate.value = status.candidate_available
    maxArchive.value = status.max_archive_bytes
    loaded.value = true
  } catch (e) {
    error.value = (e as Error).message
  }
}
onMounted(load)
function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
}
function clearSecrets() {
  currentPassword.value = ''
  password.value = ''
  confirmation.value = ''
  adminPassword.value = ''
}
async function download() {
  if (busy.value) return
  error.value = ''
  message.value = ''
  if (password.value !== confirmation.value) {
    error.value = '两次备份口令不一致。'
    return
  }
  busy.value = true
  try {
    const response = await sendRequest(
      'manage/backups/download',
      'POST',
      JSON.stringify({ current_password: currentPassword.value, password: password.value }),
      'application/json',
    )
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'seekbell.sbbackup'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
    message.value = '加密备份已生成并交给浏览器下载，请确认文件已保存，并单独保管备份口令。'
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    clearSecrets()
    busy.value = false
  }
}
async function restore() {
  if (busy.value || !file.value || candidate.value || !acknowledged.value) return
  error.value = ''
  message.value = ''
  if (file.value.size > maxArchive.value) {
    error.value = '备份超过支持上限。'
    return
  }
  busy.value = true
  try {
    const metadata = JSON.stringify({
      current_password: currentPassword.value,
      password: password.value,
      username: username.value,
      admin_password: adminPassword.value,
    })
    // JSON credentials stay in the request body, never a URL/header or browser storage.
    const body = new Blob([metadata + '\n', file.value], { type: 'application/octet-stream' })
    await sendRequest('manage/backups/restore', 'POST', body)
    candidate.value = true
    message.value = '独立恢复副本已生成，副本旧会话已清除。当前工作空间继续运行；副本尚未启用。'
    file.value = undefined
    if (input.value) input.value.value = ''
    username.value = ''
    acknowledged.value = false
  } catch (e) {
    error.value = (e as Error).message
    await load() // A lost response can still have published a valid candidate.
  } finally {
    clearSecrets()
    busy.value = false
  }
}
</script>
<template>
  <div class="side-stack">
    <div v-if="error" class="form-errors" role="alert">{{ error }}</div>
    <p v-if="message" class="info-note" role="status">{{ message }}</p>
    <p v-if="busy" role="status">正在处理，请保持页面打开。大文件可能需要较长时间。</p>

    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>导出备份</h2>
          <p>加密保存完整数据，先在独立副本中恢复</p>
        </div>
        <Icon name="download" :size="21" />
      </div>
      <div class="form-content form-stack">
        <div class="backup-summary">
          <span
            ><strong>{{ state.tasks.length }}</strong
            >任务</span
          ><span
            ><strong>{{ state.targets.length }}</strong
            >目标</span
          ><span
            ><strong>{{ totals.data.value?.posts ?? '—' }}</strong
            >帖子</span
          ><span
            ><strong>{{ totals.data.value?.deliveries ?? '—' }}</strong
            >记录</span
          >
        </div>
        <p>
          备份包含管理员、规则、历史、去重账本、队列和原凭据密钥。下载使用一致性快照，后台继续运行；快照之后的修改与回执不在备份中。
        </p>
        <p class="warning-note">
          请单独保管备份口令，丢失后无法解密。普通演示备份不能用于生产恢复。
        </p>
        <form class="form-stack" @submit.prevent="download">
          <label for="backup-current">当前管理员密码</label>
          <input
            id="backup-current"
            v-model="currentPassword"
            class="text-input"
            type="password"
            autocomplete="current-password"
            maxlength="128"
            required
            :disabled="busy"
          />
          <label for="backup-password">备份加密口令</label>
          <input
            id="backup-password"
            v-model="password"
            class="text-input"
            type="password"
            autocomplete="off"
            minlength="12"
            maxlength="1024"
            required
            :disabled="busy"
          />
          <p class="small-note">下载时设置新的独立口令；恢复时输入所选备份的口令，12–1024 字符。</p>
          <label for="backup-confirm">确认下载口令</label>
          <input
            id="backup-confirm"
            v-model="confirmation"
            class="text-input"
            type="password"
            autocomplete="off"
            minlength="12"
            maxlength="1024"
            required
            :disabled="busy"
          />
          <button class="button primary" type="submit" :disabled="busy || !loaded">
            生成并下载加密备份
          </button>
        </form>
      </div>
    </section>
    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>从文件恢复</h2>
          <p>先校验文件，恢复到独立副本</p>
        </div>
        <Icon name="upload" :size="21" />
      </div>
      <div class="form-content form-stack">
        <p>
          仅支持相同数据库版本。还需验证备份中的管理员用户名与当时密码。恢复不会覆盖当前数据，也不会启动副本中的采集或发送。
        </p>
        <p class="warning-note">
          启用副本前必须停止原实例。恢复会保留原启停配置和待发送队列，可能重复发送；正式切换需在宿主机按维护说明执行。
        </p>
        <p v-if="candidate" class="info-note" role="status">
          已有独立恢复副本，尚未启用。请按维护说明处理后再上传，网页不能覆盖此副本。
        </p>
        <form v-else class="form-stack" @submit.prevent="restore">
          <label for="restore-file">加密备份文件</label>
          <div>
            <label class="upload-zone"
              ><Icon name="upload" :size="28" /><strong>{{
                file?.name || '选择加密备份文件'
              }}</strong
              ><span>.sbbackup · 加密数据库备份</span
              ><input
                id="restore-file"
                ref="input"
                class="text-input"
                type="file"
                accept=".sbbackup"
                required
                :disabled="busy || !loaded"
                @change="selectFile"
            /></label>
          </div>
          <p class="small-note">
            支持数据库最大 2 GiB 的加密备份。浏览器下载会占用相应内存，大库建议使用停服 CLI。
          </p>
          <p class="small-note">请先在上方填写当前管理员密码和所选备份的加密口令。</p>
          <label for="restore-username">备份中的管理员用户名</label>
          <input
            id="restore-username"
            v-model="username"
            class="text-input"
            autocomplete="off"
            pattern="[A-Za-z0-9_-]{3,32}"
            required
            :disabled="busy"
          />
          <label for="restore-password">备份中的管理员密码</label>
          <input
            id="restore-password"
            v-model="adminPassword"
            class="text-input"
            type="password"
            autocomplete="off"
            maxlength="128"
            required
            :disabled="busy"
          />
          <label class="checkbox-row"
            ><input
              v-model="acknowledged"
              type="checkbox"
              required
              :disabled="busy"
            />我已了解：只生成独立副本，尚未切换当前工作空间。</label
          >
          <button
            class="button primary"
            type="submit"
            :disabled="
              busy || !loaded || !acknowledged || !file || !currentPassword || password.length < 12
            "
          >
            验证并生成独立恢复副本
          </button>
        </form>
        <button v-if="!loaded" class="button" :disabled="busy" @click="load">
          重新读取备份状态
        </button>
      </div>
    </section>
  </div>
</template>
