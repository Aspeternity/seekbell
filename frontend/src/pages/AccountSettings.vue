<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { account, confirmAction, saveAdministrator, setSession } from '../store'
import FormFeedback from '../components/FormFeedback.vue'
import SessionSettings from './SessionSettings.vue'
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
// Two small forms share one request; each asks for the current password on its own.
const name = reactive({ username: account.username, current: '' })
const secret = reactive({ current: '', next: '', confirmation: '' })
const busy = ref(''),
  nameError = ref(''),
  secretError = ref(''),
  saved = ref(''),
  sessionBusy = ref(false),
  sessionGeneration = ref(0)
const dirty = computed(
  () =>
    name.username !== account.username ||
    !!name.current ||
    Object.values(secret).some(Boolean) ||
    sessionBusy.value,
)
watch(dirty, (value) => emit('dirty', value))
async function update(kind: 'name' | 'secret', username: string, current: string, next: string) {
  busy.value = kind
  saved.value = ''
  try {
    await saveAdministrator(username, current, next)
    // Only the submitted form is cleared; a draft in the other one is still valid.
    if (kind === 'name') Object.assign(name, { username: account.username, current: '' })
    else Object.assign(secret, { current: '', next: '', confirmation: '' })
    saved.value = kind
    // Every other session was signed out, so the session card reads again.
    sessionGeneration.value++
  } catch (e) {
    ;(kind === 'name' ? nameError : secretError).value = (e as Error).message
  } finally {
    busy.value = ''
  }
}
function saveName() {
  if (busy.value) return
  nameError.value = secretError.value = ''
  void update('name', name.username, name.current, '')
}
function saveSecret() {
  if (busy.value) return
  nameError.value = secretError.value = ''
  if (secret.next !== secret.confirmation) {
    secretError.value = '两次输入的新密码不一致。'
    return
  }
  void update('secret', account.username, secret.current, secret.next)
}
async function performLogout() {
  if (busy.value) return
  busy.value = 'logout'
  try {
    await setSession(false)
    emit('dirty', false)
    emit('navigate', '/login')
  } catch (e) {
    nameError.value = (e as Error).message
  } finally {
    busy.value = ''
  }
}
function logout() {
  if (dirty.value)
    confirmAction('放弃修改并退出？', '尚未保存的账户修改将丢失。', performLogout, '退出登录')
  else void performLogout()
}
</script>
<template>
  <div class="settings-stack">
    <section class="panel settings-card">
      <div class="panel-heading">
        <h2>管理员用户名</h2>
        <span class="avatar">{{ account.username.slice(0, 1).toUpperCase() }}</span>
      </div>
      <FormFeedback :error="nameError" :retryable="false" />
      <form class="form-content form-stack" aria-label="修改用户名" @submit.prevent="saveName">
        <div class="general-fields-grid account-fields">
          <div class="form-stack">
            <label for="admin-username">管理员用户名</label>
            <input
              id="admin-username"
              v-model="name.username"
              class="text-input"
              autocomplete="username"
              pattern="[A-Za-z0-9_-]{3,32}"
              minlength="3"
              maxlength="32"
              required
              :disabled="!!busy"
            />
            <p class="small-note">3–32 位字母、数字、_ 或 -</p>
          </div>
          <div class="form-stack">
            <label for="name-current-password">当前密码</label>
            <input
              id="name-current-password"
              v-model="name.current"
              class="text-input"
              type="password"
              autocomplete="current-password"
              maxlength="128"
              required
              :disabled="!!busy"
            />
          </div>
        </div>
        <div class="inline-form-footer settings-savebar">
          <span role="status">{{ saved === 'name' ? '用户名已更新，其他会话已退出' : '' }}</span>
          <button
            class="button primary"
            type="submit"
            :disabled="!!busy || name.username === account.username"
          >
            {{ busy === 'name' ? '保存中…' : '更新用户名' }}
          </button>
        </div>
      </form>
    </section>
    <section class="panel settings-card">
      <div class="panel-heading">
        <div>
          <h2>修改密码</h2>
          <p>修改后其他浏览器需要重新登录</p>
        </div>
      </div>
      <FormFeedback :error="secretError" :retryable="false" />
      <form class="form-content form-stack" aria-label="修改密码" @submit.prevent="saveSecret">
        <div class="settings-fields-grid three">
          <div class="form-stack">
            <label for="current-password">当前密码</label>
            <input
              id="current-password"
              v-model="secret.current"
              class="text-input"
              type="password"
              autocomplete="current-password"
              maxlength="128"
              required
              :disabled="!!busy"
            />
          </div>
          <div class="form-stack">
            <label for="new-password">新密码</label>
            <input
              id="new-password"
              v-model="secret.next"
              class="text-input"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required
              :disabled="!!busy"
            />
            <p class="small-note">至少 8 个字符</p>
          </div>
          <div class="form-stack">
            <label for="confirm-new-password">确认新密码</label>
            <input
              id="confirm-new-password"
              v-model="secret.confirmation"
              class="text-input"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required
              :disabled="!!busy"
            />
          </div>
        </div>
        <div class="inline-form-footer settings-savebar">
          <span role="status">{{ saved === 'secret' ? '密码已更新，其他会话已退出' : '' }}</span>
          <button class="button primary" type="submit" :disabled="!!busy || !secret.next">
            {{ busy === 'secret' ? '保存中…' : '更新密码' }}
          </button>
        </div>
      </form>
    </section>
    <SessionSettings
      :generation="sessionGeneration"
      @dirty="sessionBusy = $event"
      @logout="logout"
    />
  </div>
</template>
