<script setup lang="ts">
import AppSelect from '../components/AppSelect.vue'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Toggle from '../components/Toggle.vue'
import TelegramPreview from '../components/TelegramPreview.vue'
import { state, channelMeta, clone, newTarget, saveTarget } from '../store'
import type { Channel, Target } from '../store'
const props = defineProps<{
  target: Target
}>()
const emit = defineEmits<{
  navigate: [path: string]
  dirty: [value: boolean]
}>()
const draft = reactive(clone(props.target)),
  errors = ref<string[]>([]),
  busy = ref(false)
const privateFields = reactive({
  base: '',
  token: '',
  chat: '',
  device: '',
  host: '',
  username: '',
  password: '',
  from: '',
  to: '',
  url: '',
  headers: '',
})
const threadId = ref(''),
  insecure = ref(draft.security === 'plain')
const baseline = JSON.stringify({
  draft,
  privateFields,
  threadId: threadId.value,
  insecure: insecure.value,
})
watch(
  [draft, privateFields, threadId, insecure],
  () =>
    emit(
      'dirty',
      JSON.stringify({
        draft,
        privateFields,
        threadId: threadId.value,
        insecure: insecure.value,
      }) !== baseline,
    ),
  { deep: true },
)
const meta = computed(() => channelMeta[draft.channel])
const duplicate = computed(() =>
  state.targets.some((t) => t.id !== draft.id && t.name.trim() === draft.name.trim()),
)
function changeChannel(channel: Channel) {
  if (draft.id) return
  Object.assign(draft, { ...newTarget(channel), name: draft.name })
  Object.keys(privateFields).forEach((k) => (privateFields[k as keyof typeof privateFields] = ''))
  threadId.value = ''
  insecure.value = false
}
function validUrl(value: string, base = false) {
  try {
    const u = new URL(value)
    return (
      ['https:', 'http:'].includes(u.protocol) &&
      !!u.hostname &&
      !u.username &&
      !u.password &&
      !u.hash &&
      (!base || !u.search) &&
      !/[\s\\]/.test(value)
    )
  } catch {
    return false
  }
}
function required(value: string, label: string) {
  if (!draft.configured && !value.trim()) errors.value.push('请填写' + label + '。')
}
function checkUrl(value: string, label: string, base = false) {
  required(value, label)
  if (value && !validUrl(value, base))
    errors.value.push(label + '须为 HTTP(S) 地址，不含用户名、密码或片段。')
}
async function save() {
  if (busy.value) return
  errors.value = []
  if (!draft.name.trim()) errors.value.push('请填写目标名称。')
  if (draft.channel === 'telegram') {
    required(privateFields.token, 'Bot Token')
    required(privateFields.chat, 'Chat ID')
    if (privateFields.token && !/^[0-9]+:[A-Za-z0-9_-]+$/.test(privateFields.token))
      errors.value.push('Bot Token 格式应为数字、冒号和令牌。')
    if (privateFields.chat && !/^-?[0-9]+$|^@[A-Za-z0-9_]+$/.test(privateFields.chat))
      errors.value.push('Chat ID 应为数字或 @用户名。')
    if (privateFields.base && !validUrl(privateFields.base, true))
      errors.value.push('Telegram 服务地址无效。')
    if (
      threadId.value &&
      (!Number.isInteger(Number(threadId.value)) || Number(threadId.value) <= 0)
    )
      errors.value.push('话题 ID 应为正整数。')
  } else if (draft.channel === 'bark') {
    required(privateFields.device, '设备 Key')
    if (privateFields.base && !validUrl(privateFields.base, true))
      errors.value.push('Bark 服务地址无效。')
  } else if (draft.channel === 'smtp') {
    required(privateFields.host, 'SMTP 服务器')
    required(privateFields.from, '发件地址')
    required(privateFields.to, '收件地址')
    if (privateFields.host && /[\s/@\\]/.test(privateFields.host))
      errors.value.push('SMTP 服务器应为主机名或 IP。')
    if (!Number.isInteger(draft.port) || draft.port < 1 || draft.port > 65535)
      errors.value.push('SMTP 端口应在 1–65535 之间。')
    for (const [value, label] of [
      [privateFields.from, '发件地址'],
      [privateFields.to, '收件地址'],
    ])
      if (value && !/^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/.test(value))
        errors.value.push(label + '应为单个邮箱。')
    if (!draft.configured && Boolean(privateFields.username) !== Boolean(privateFields.password))
      errors.value.push('SMTP 用户名与密码需一起填写或一起留空。')
    if (draft.security === 'plain' && !insecure.value)
      errors.value.push('使用明文 SMTP 前必须明确确认。')
  } else {
    checkUrl(privateFields.url, 'Webhook URL')
    if (privateFields.headers)
      try {
        const headers: unknown = JSON.parse(privateFields.headers)
        if (!headers || Array.isArray(headers) || typeof headers !== 'object') throw Error()
        const entries = Object.entries(headers)
        const blocked = [
          'host',
          'content-length',
          'transfer-encoding',
          'connection',
          'content-type',
          'idempotency-key',
          'cookie',
          'proxy-authorization',
          'accept-encoding',
        ]
        if (
          entries.length > 20 ||
          new Set(entries.map(([k]) => k.toLowerCase())).size !== entries.length ||
          entries.some(
            ([k, v]) =>
              !/^[-!#$%&'*+.^_`|~0-9A-Za-z]+$/.test(k) ||
              blocked.includes(k.toLowerCase()) ||
              k.toLowerCase().startsWith('proxy-') ||
              typeof v !== 'string' ||
              v.length > 4096 ||
              /[\r\n]/.test(v),
          )
        )
          throw Error()
      } catch {
        errors.value.push('请求头应为有效 JSON 字符串映射，不能包含保留头、重复头或换行。')
      }
  }
  if (!Number.isInteger(draft.summaryLimit) || draft.summaryLimit < 0 || draft.summaryLimit > 1000)
    errors.value.push('摘要长度应为 0–1000 的整数。')
  if (errors.value.length) {
    nextTick(() => document.querySelector<HTMLElement>('[data-target-errors]')?.focus())
    return
  }
  busy.value = true
  try {
    const connection: Record<string, unknown> = {
      include_summary: draft.summary,
      summary_limit: draft.summaryLimit,
    }
    const put = (key: string, value: string) => {
      if (value.trim()) connection[key] = value.trim()
    }
    if (draft.channel === 'telegram') {
      put('base_url', privateFields.base)
      put('bot_token', privateFields.token)
      put('chat_id', privateFields.chat)
      if (threadId.value) connection.message_thread_id = Number(threadId.value)
    } else if (draft.channel === 'bark') {
      put('base_url', privateFields.base)
      put('device_key', privateFields.device)
      connection.group = draft.group
    } else if (draft.channel === 'smtp') {
      put('host', privateFields.host)
      put('username', privateFields.username)
      if (privateFields.password) connection.password = privateFields.password
      put('from_address', privateFields.from)
      put('to_address', privateFields.to)
      Object.assign(connection, {
        port: draft.port,
        security: draft.security,
        allow_insecure: insecure.value,
      })
    } else {
      put('url', privateFields.url)
      if (privateFields.headers.trim()) connection.headers = JSON.parse(privateFields.headers)
      connection.response_mode = draft.responseMode
    }
    await saveTarget({ ...draft, configured: true }, connection)
    Object.keys(privateFields).forEach((k) => (privateFields[k as keyof typeof privateFields] = ''))
    emit('dirty', false)
    emit('navigate', '/notifications/targets')
  } catch (e) {
    errors.value = [(e as Error).message]
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <button class="back-link" @click="emit('navigate', '/notifications/targets')">
    <Icon name="back" :size="17" />返回通知目标
  </button>
  <section class="page-heading">
    <div>
      <p class="eyebrow">MAKE IT REACH YOU</p>
      <h1 tabindex="-1">{{ draft.id ? '编辑通知目标' : '添加通知目标' }}</h1>
      <p class="subtitle">一次配置，让关注有一个可靠的去处。</p>
    </div>
    <span class="small-badge neutral">{{ meta.type }}</span>
  </section>
  <div v-if="errors.length" data-target-errors tabindex="-1" class="form-errors" role="alert">
    <Icon name="alert" :size="19" />
    <div>
      <strong>请检查目标配置</strong>
      <p v-for="error in errors" :key="error">{{ error }}</p>
    </div>
  </div>
  <form class="editor-layout target-editor" @submit.prevent="save" novalidate>
    <div class="editor-fields">
      <section class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">01</span>
          <div>
            <h2>目标与渠道</h2>
            <p>为不同的通知选择合适的方式</p>
          </div>
        </div>
        <div class="form-content">
          <div class="channel-picker">
            <button
              v-for="(item, id) in channelMeta"
              :key="id"
              type="button"
              :disabled="!!draft.id && draft.channel !== id"
              :aria-pressed="draft.channel === id"
              :class="{ selected: draft.channel === id }"
              @click="changeChannel(id)"
            >
              <Icon :name="item.icon" :size="20" />{{ item.type }}
            </button>
          </div>
          <label class="field-label" for="target-name"
            >目标名称 <span class="required">*</span></label
          ><input
            id="target-name"
            v-model="draft.name"
            class="text-input"
            maxlength="80"
            placeholder="例如：我的私人通知"
          />
          <p v-if="duplicate" class="warning-note">已有同名目标，请确认是否需要重复配置。</p>
          <div class="setting-row no-border">
            <div>
              <strong>启用目标</strong><small>暂停后停止发送和重试，恢复时不自动补发。</small>
            </div>
            <Toggle v-model="draft.enabled" label="启用通知目标" />
          </div>
        </div>
      </section>
      <section class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">02</span>
          <div>
            <h2>{{ meta.type }} 连接配置</h2>
            <p>配置由服务端加密保存，敏感字段不回传</p>
          </div>
          <Icon name="shield" :size="18" />
        </div>
        <div class="form-content form-stack">
          <div class="info-note">
            <Icon name="shield" :size="18" />
            <p>
              地址、账号、令牌与请求头只写入服务端加密配置。已配置的敏感字段留空保留；保存不会发送通知。
            </p>
          </div>
          <template v-if="draft.channel === 'telegram'"
            ><label
              >Bot Token <span class="required">*</span
              ><input
                v-model="privateFields.token"
                type="password"
                autocomplete="off"
                class="text-input"
                :placeholder="
                  draft.configured ? '已配置 · 留空保留' : '123456:demo_token'
                " /></label
            ><label
              >Chat ID <span class="required">*</span
              ><input
                v-model="privateFields.chat"
                type="password"
                autocomplete="off"
                class="text-input"
                :placeholder="draft.configured ? '已配置 · 留空保留' : '-1001234567890'" /></label
            ><label
              >话题 ID <span class="optional">选填</span
              ><input
                v-model="threadId"
                type="number"
                min="1"
                class="text-input"
                placeholder="指定群组话题" /></label
            ><label
              >服务地址 <span class="optional">选填</span
              ><input
                v-model="privateFields.base"
                class="text-input"
                placeholder="默认 https://api.telegram.org" /></label
          ></template>
          <template v-if="draft.channel === 'bark'"
            ><label
              >设备 Key <span class="required">*</span
              ><input
                v-model="privateFields.device"
                type="password"
                autocomplete="off"
                class="text-input"
                :placeholder="draft.configured ? '已配置 · 留空保留' : '演示设备 Key'" /></label
            ><label
              >服务地址 <span class="optional">选填</span
              ><input
                v-model="privateFields.base"
                class="text-input"
                placeholder="默认 https://api.day.app" /></label
            ><label
              >通知分组<input
                v-model="draft.group"
                class="text-input"
                maxlength="100"
                placeholder="SeekBell" /></label
          ></template>
          <template v-if="draft.channel === 'smtp'"
            ><div class="form-two">
              <label
                >SMTP 服务器 <span class="required">*</span
                ><input
                  v-model="privateFields.host"
                  class="text-input"
                  :placeholder="
                    draft.configured ? '已配置 · 留空保留' : 'smtp.example.test'
                  " /></label
              ><label
                >端口<input
                  v-model.number="draft.port"
                  type="number"
                  min="1"
                  max="65535"
                  class="text-input"
              /></label>
            </div>
            <label
              >连接安全<AppSelect
                v-model="draft.security"
                aria-label="连接安全"
                class="text-input"
                :options="[
                  { value: 'tls', label: '隐式 TLS' },
                  { value: 'starttls', label: 'STARTTLS' },
                  { value: 'plain', label: '明文（需明确允许）' },
                ]" /></label
            ><label v-if="draft.security === 'plain'" class="check-label"
              ><input
                v-model="insecure"
                type="checkbox"
              />我了解明文连接不加密，明确允许此配置</label
            >
            <div class="form-two">
              <label
                >登录用户名<input
                  v-model="privateFields.username"
                  autocomplete="off"
                  class="text-input"
                  placeholder="可选，须与密码配对" /></label
              ><label
                >登录密码<input
                  v-model="privateFields.password"
                  type="password"
                  autocomplete="new-password"
                  class="text-input"
                  placeholder="留空保留原配置"
              /></label>
            </div>
            <label
              >发件地址 <span class="required">*</span
              ><input
                v-model="privateFields.from"
                type="email"
                class="text-input"
                :placeholder="
                  draft.configured ? '已配置 · 留空保留' : 'sender@example.test'
                " /></label
            ><label
              >收件地址 <span class="required">*</span
              ><input
                v-model="privateFields.to"
                type="email"
                class="text-input"
                :placeholder="
                  draft.configured ? '已配置 · 留空保留' : 'reader@example.test'
                " /></label
          ></template>
          <template v-if="draft.channel === 'webhook'"
            ><label
              >Webhook URL <span class="required">*</span
              ><input
                v-model="privateFields.url"
                type="password"
                autocomplete="off"
                class="text-input"
                :placeholder="
                  draft.configured ? '已配置 · 留空保留' : 'https://example.test/notify'
                " /></label
            ><label
              >自定义请求头 <span class="optional">JSON，最多 20 项</span
              ><textarea
                v-model="privateFields.headers"
                rows="4"
                spellcheck="false"
                placeholder='{"X-Demo-Key":"sample"}'
              /></label
            ><label
              >成功判定<AppSelect
                v-model="draft.responseMode"
                aria-label="成功判定"
                class="text-input"
                :options="[
                  { value: 'json_ok', label: 'JSON 响应中 ok 为 true' },
                  { value: 'status', label: '任意 HTTP 2xx' },
                ]"
            /></label>
            <p class="small-note">
              固定 JSON 消息结构，包含 schema_version 与稳定
              event_id。不执行脚本，不自定义消息代码。
            </p></template
          >
        </div>
      </section>
      <section class="panel form-panel">
        <div class="form-section-heading">
          <span class="section-number">03</span>
          <div>
            <h2>通知内容</h2>
            <p>用刚好的信息，决定是否进一步查看</p>
          </div>
        </div>
        <div class="form-content">
          <div class="setting-row no-border">
            <div>
              <strong>包含 RSS 摘要</strong><small>只使用来源已有的摘要，不读取全文。</small>
            </div>
            <Toggle v-model="draft.summary" label="包含 RSS 摘要" />
          </div>
          <label v-if="draft.summary" class="field-label"
            >摘要最大长度<input
              v-model.number="draft.summaryLimit"
              type="number"
              min="0"
              max="1000"
              class="text-input"
          /></label>
        </div>
      </section>
    </div>
    <aside class="editor-preview">
      <section class="panel support-panel">
        <h2><Icon :name="meta.icon" :size="19" />消息预览</h2>
        <p>{{ meta.description }}</p>
        <div class="message-preview">
          <span class="small-badge neutral">SEEKBELL</span>
          <TelegramPreview
            v-if="draft.channel === 'telegram'"
            :summary="draft.summary"
            :summary-limit="draft.summaryLimit"
          />
          <template v-else>
            <h3>DMIT 洛杉矶套餐补货</h3>
            <p>作者：cloud_note<br />版块：优惠<br />命中：好价服务器雷达</p>
            <p v-if="draft.summary">
              {{ '新一批套餐开放，记录本次优惠信息。'.slice(0, draft.summaryLimit) }}
            </p>
            <span class="mock-link">查看原帖 ↗</span>
          </template>
        </div>
        <p class="small-note">
          {{
            draft.channel === 'smtp'
              ? 'SMTP 成功只代表服务器接受，不保证进入收件箱。'
              : '同帖多任务命中，将在同一目标合并为一条通知。'
          }}
        </p>
      </section>
      <div class="editor-tip">
        <Icon name="shield" :size="18" />
        <p>保存后可用于任务目标选择；可在通知目标页显式运行独立测试。</p>
      </div>
    </aside>
    <div class="save-bar">
      <div>
        <Icon name="shield" :size="15" /><span
          >配置加密保存到服务端<small>不会发送通知</small></span
        >
      </div>
      <div class="save-actions">
        <button type="button" class="button" @click="emit('navigate', '/notifications/targets')">
          取消</button
        ><button type="submit" class="button primary" :disabled="busy">
          <Icon name="check" :size="17" />保存目标
        </button>
      </div>
    </div>
  </form>
</template>
