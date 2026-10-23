<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Feedback from '../components/Feedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import NotificationTabs from '../components/NotificationTabs.vue'
import Targets from './Targets.vue'
import Records from './Records.vue'
import { signedIn, state } from '../store'
import { readCacheRevision, readSessionRevision } from '../readCache'
import { prepareRecords, recordsPrepared, recordTabs } from '../recordQueries'
const props = defineProps<{ tab: string; recordId?: string }>()
const emit = defineEmits<{ navigate: [path: string] }>()
const shown = shallowRef({ tab: props.tab, recordId: props.recordId, prepared: false })
const hasView = ref(false),
  pending = ref(false),
  error = ref('')
const names: Record<string, string> = {
  deliveries: '投递记录',
  manual: '手动重发',
  tests: '测试记录',
}
const message = computed(() => '正在读取' + (names[props.tab] || '通知记录') + '…')
let generation = 0
async function transition() {
  const current = ++generation
  const session = readSessionRevision.value,
    revision = readCacheRevision.value
  const destination = { tab: props.tab, recordId: props.recordId, prepared: false }
  pending.value = false
  error.value = ''
  if (!signedIn.value) {
    hasView.value = false
    return
  }
  if (
    hasView.value &&
    shown.value.tab === destination.tab &&
    shown.value.recordId === destination.recordId
  )
    return
  if (
    destination.tab === 'targets' ||
    destination.recordId ||
    recordsPrepared(destination.tab, state.settings.timezone)
  ) {
    shown.value = destination
    hasView.value = true
    return
  }
  pending.value = true
  try {
    await prepareRecords(destination.tab, state.settings.timezone)
    if (
      current !== generation ||
      session !== readSessionRevision.value ||
      revision !== readCacheRevision.value
    )
      return
    shown.value = { ...destination, prepared: true }
    hasView.value = true
  } catch (e) {
    if (current === generation && session === readSessionRevision.value)
      error.value =
        '无法切换到' + (names[destination.tab] || '通知记录') + '：' + (e as Error).message
  } finally {
    if (current === generation) pending.value = false
  }
}
watch(
  () => [
    props.tab,
    props.recordId,
    state.settings.timezone,
    readCacheRevision.value,
    readSessionRevision.value,
  ],
  transition,
  { immediate: true },
)
onMounted(() => {
  if (signedIn.value)
    for (const tab of recordTabs) void prepareRecords(tab, state.settings.timezone).catch(() => {})
})
onBeforeUnmount(() => {
  ++generation
})
</script>
<template>
  <template v-if="!shown.recordId">
    <section class="page-heading">
      <div>
        <p class="eyebrow">GOOD NEWS, YOUR WAY</p>
        <h1 tabindex="-1">通知管理</h1>
        <p class="subtitle">把关心的消息，送到你习惯的地方。</p>
      </div>
      <button class="button primary" @click="emit('navigate', '/target/new')">
        <Icon name="plus" :size="18" />添加通知目标
      </button>
    </section>
    <NotificationTabs
      :tab="shown.tab"
      :pending-tab="pending ? tab : undefined"
      @navigate="(path) => emit('navigate', path)"
    />
  </template>
  <div class="notification-panel-region">
    <div v-if="hasView" class="notification-switch-feedback">
      <Feedback :loading="pending" :error="error" :message="message" subtle @retry="transition" />
    </div>
    <template v-if="hasView">
      <Targets v-if="shown.tab === 'targets'" @navigate="(path) => emit('navigate', path)" />
      <Records
        v-else
        :key="shown.tab + ':' + (shown.recordId || '')"
        :tab="shown.tab"
        :record-id="shown.recordId"
        :prepared="shown.prepared"
        @navigate="(path) => emit('navigate', path)"
      />
    </template>
    <section v-else class="panel">
      <ReadRegion
        :loading="pending"
        :error="error"
        :has-data="false"
        :min-height="360"
        @retry="transition"
      />
    </section>
  </div>
</template>
<style scoped>
.notification-panel-region {
  position: relative;
}
.notification-switch-feedback {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 3;
  max-width: calc(100% - 24px);
}
.notification-switch-feedback :deep(.remote-feedback) {
  margin: 0;
  padding: 4px 8px;
  background: #fff;
  border-radius: 4px;
}
.notification-switch-feedback :deep(.form-errors) {
  background: #fff8f5;
}
</style>
