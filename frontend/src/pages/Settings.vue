<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { settingsTabs } from '../settings'
import AboutSettings from './AboutSettings.vue'
import AccountSettings from './AccountSettings.vue'
import AlertsSettings from './AlertsSettings.vue'
import BackupSettings from './BackupSettings.vue'
import DataSettings from './DataSettings.vue'
import Preferences from './Preferences.vue'
const props = defineProps<{ tab?: string }>()
const emit = defineEmits<{ navigate: [path: string]; dirty: [value: boolean] }>()
const selectedTab = computed(() => props.tab || 'preferences')
const tabs = ref<HTMLElement>()
function revealCategory() {
  const nav = tabs.value
  const current = nav?.querySelector<HTMLElement>('[aria-current="page"]')
  if (nav && current)
    nav.scrollTo({ left: current.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2 })
}
watch(selectedTab, () => nextTick(revealCategory), { flush: 'post' })
let tabResize: ResizeObserver | undefined
onMounted(() => {
  tabResize = new ResizeObserver(revealCategory)
  if (tabs.value) tabResize.observe(tabs.value)
})
onBeforeUnmount(() => tabResize?.disconnect())
</script>
<template>
  <section class="page-heading">
    <div>
      <p class="eyebrow">MAKE YOURSELF AT HOME</p>
      <h1 tabindex="-1">系统设置</h1>
      <p class="subtitle">让 SeekBell 按照你的习惯运转。</p>
    </div>
  </section>
  <div class="settings-shell">
    <nav ref="tabs" class="page-tabs settings-categories" aria-label="设置分类">
      <button
        v-for="item in settingsTabs"
        :key="item.value"
        type="button"
        :class="{ active: selectedTab === item.value }"
        :aria-current="selectedTab === item.value ? 'page' : undefined"
        @click="emit('navigate', '/settings/' + item.value)"
      >
        {{ item.label }}
      </button>
    </nav>
    <div class="settings-content">
      <Preferences v-if="selectedTab === 'preferences'" @dirty="emit('dirty', $event)" />
      <AlertsSettings v-else-if="selectedTab === 'alerts'" @dirty="emit('dirty', $event)" />
      <DataSettings v-else-if="selectedTab === 'data'" @dirty="emit('dirty', $event)" />
      <BackupSettings v-else-if="selectedTab === 'backup'" @dirty="emit('dirty', $event)" />
      <AccountSettings
        v-else-if="selectedTab === 'account'"
        @dirty="emit('dirty', $event)"
        @navigate="emit('navigate', $event)"
      />
      <AboutSettings v-else-if="selectedTab === 'about'" />
    </div>
  </div>
</template>
