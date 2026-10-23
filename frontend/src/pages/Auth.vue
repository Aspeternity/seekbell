<script setup lang="ts">
import { ref } from 'vue'
import Icon from '../components/Icon.vue'
import { account, authenticate } from '../store'
const props = defineProps<{
  setup: boolean
}>()
const emit = defineEmits<{
  navigate: [path: string]
}>()
const username = ref(props.setup ? '' : account.username),
  password = ref(''),
  confirmation = ref(''),
  visible = ref(false),
  error = ref(''),
  busy = ref(false)
async function submit() {
  error.value = ''
  if (!/^[A-Za-z0-9_-]{3,32}$/.test(username.value)) {
    error.value = '用户名应为 3–32 位字母、数字、下划线或短横线。'
    return
  }
  if (props.setup) {
    if (account.created) {
      error.value = '管理员已创建，请直接登录。'
      return
    }
    if (password.value.length < 8 || password.value.length > 128) {
      error.value = '密码应为 8–128 个字符。'
      return
    }
    if (password.value !== confirmation.value) {
      error.value = '两次输入的密码不一致。'
      return
    }
  }
  busy.value = true
  try {
    await authenticate(props.setup, username.value, password.value)
    password.value = ''
    confirmation.value = ''
    emit('navigate', '/')
  } catch (e) {
    error.value = (e as Error).message || '无法完成登录，请重试。'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <div class="auth-shell">
    <section class="auth-story">
      <a href="#/" class="brand" @click.prevent="emit('navigate', '/')"
        ><span class="brand-icon"><Icon name="bell" :size="23" /></span
        ><span>seekbell<span class="brand-period">.</span></span></a
      >
      <div class="auth-story-copy">
        <p class="eyebrow">LESS SCROLLING. MORE LIVING.</p>
        <h2>让消息找到你。<br />把时间留给生活。</h2>
        <p>从你关注的网站中，留意你在意的。<br />几条简单规则，一份属于你的信息流。</p>
        <div class="signal-illustration" aria-hidden="true">
          <span class="signal-ring ring-one" /><span class="signal-ring ring-two" />
          <div class="signal-bell"><Icon name="bell" :size="44" /></div>
          <div class="floating-message">
            <span class="icon-tile orange"><Icon name="spark" :size="20" /></span>
            <div><strong>发现一条你关心的新帖</strong><small>好价服务器雷达 · 刚刚</small></div>
            <span class="status-dot green-dot" />
          </div>
          <span class="floating-channel c-one"><Icon name="send" :size="24" /></span
          ><span class="floating-channel c-two"><Icon name="phone" :size="24" /></span>
        </div>
      </div>
      <p class="auth-story-footer">你的数据，由你掌握。<span>SeekBell · 自托管</span></p>
    </section>
    <main class="auth-main">
      <div class="auth-box">
        <span class="data-badge"><span class="status-dot" />自托管工作空间</span
        ><template v-if="setup && account.created"
          ><div class="auth-success-icon"><Icon name="shield" :size="32" /></div>
          <h1 tabindex="-1">管理员已经就绪</h1>
          <p class="auth-subtitle">此工作空间已创建唯一管理员，请登录。</p>
          <button class="button primary auth-submit" @click="emit('navigate', '/login')">
            前往登录<Icon name="arrow" :size="17" /></button></template
        ><template v-else
          ><h1 tabindex="-1">{{ setup ? '欢迎来到 SeekBell' : '欢迎回来' }}</h1>
          <p class="auth-subtitle">
            {{
              setup ? '创建你的唯一管理员，开启第一份关注。' : '登录工作空间，看看有哪些新发现。'
            }}
          </p>
          <form class="form-stack" @submit.prevent="submit" novalidate>
            <div v-if="error" class="form-errors" role="alert">
              <Icon name="alert" :size="18" />
              <p>{{ error }}</p>
            </div>
            <label
              >管理员用户名<input
                v-model="username"
                class="text-input"
                autocomplete="username"
                placeholder="例如：admin"
                maxlength="32" /></label
            ><label
              >{{ setup ? '设置密码' : '密码' }}
              <div class="password-field">
                <input
                  v-model="password"
                  :type="visible ? 'text' : 'password'"
                  class="text-input"
                  :autocomplete="setup ? 'new-password' : 'current-password'"
                  placeholder="请输入密码"
                  maxlength="128"
                /><button
                  class="icon-button"
                  type="button"
                  :aria-label="visible ? '隐藏密码' : '显示密码'"
                  @click="visible = !visible"
                >
                  <Icon :name="visible ? 'eye-off' : 'eye'" :size="18" />
                </button></div></label
            ><label v-if="setup"
              >确认密码<input
                v-model="confirmation"
                :type="visible ? 'text' : 'password'"
                class="text-input"
                autocomplete="new-password"
                placeholder="再次输入密码"
                maxlength="128"
            /></label>
            <p v-if="setup" class="small-note">
              至少 8 个字符。无需初始化令牌，仅允许创建一位管理员。
            </p>
            <button class="button primary auth-submit" type="submit" :disabled="busy">
              {{ busy ? '正在处理…' : setup ? '创建管理员并进入' : '登录工作空间'
              }}<Icon name="arrow" :size="17" />
            </button>
          </form>
        </template>
        <p class="auth-privacy">
          <Icon name="shield" :size="15" />账号保存在当前服务，密码不会回传。
        </p>
      </div>
      <footer>SeekBell · 留意你关心的</footer>
    </main>
  </div>
</template>
