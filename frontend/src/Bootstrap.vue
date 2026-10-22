<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import App from './App.vue'
import { initialize, signedIn, refreshRuntime, runtime } from './store'
const ready = ref(false),
  error = ref(''),
  busy = ref(false)
async function start() {
  busy.value = true
  error.value = ''
  try {
    await initialize()
    ready.value = true
  } catch (e) {
    error.value = (e as Error).message || '无法连接服务，请稍后重试。'
  } finally {
    busy.value = false
  }
}
start()
const runtimeTimer = setInterval(async () => {
  if (!signedIn.value) return
  try {
    await refreshRuntime()
  } catch {
    Object.assign(runtime, {
      active: false,
      status: 'unavailable',
      code: 'runtime_status_unavailable',
    })
  }
}, 5000)
onBeforeUnmount(() => clearInterval(runtimeTimer))
</script>
<template>
  <App v-if="ready" />
  <main v-else class="panel empty-state">
    <h1>SeekBell</h1>
    <p role="status">{{ error || '正在连接工作空间…' }}</p>
    <button v-if="error" class="button primary" :disabled="busy" @click="start">重新连接</button>
  </main>
</template>
