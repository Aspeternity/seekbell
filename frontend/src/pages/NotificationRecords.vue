<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import Feedback from '../components/Feedback.vue'
import ReadRegion from '../components/ReadRegion.vue'
import RecordTabs from '../components/RecordTabs.vue'
import Records from './Records.vue'
import { signedIn, state } from '../store'
import { readCacheRevision, readSessionRevision } from '../readCache'
import { prepareRecords, recordsPrepared } from '../recordQueries'
const props = defineProps<{ tab: string; recordId?: string; initialTarget?: string }>()
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
  if (destination.recordId || recordsPrepared(destination.tab, state.settings.timezone)) {
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
onBeforeUnmount(() => {
  ++generation
})
</script>
<template>
  <RecordTabs
    v-if="!shown.recordId"
    :tab="shown.tab"
    :pending-tab="pending ? tab : undefined"
    @navigate="(path) => emit('navigate', path)"
  />
  <div class="notification-panel-region">
    <div v-if="hasView" class="notification-switch-feedback">
      <Feedback :loading="pending" :error="error" :message="message" subtle @retry="transition" />
    </div>
    <template v-if="hasView">
      <Records
        :key="shown.tab + ':' + (shown.recordId || '') + ':' + (initialTarget || '')"
        :tab="shown.tab"
        :record-id="shown.recordId"
        :initial-target="initialTarget"
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
