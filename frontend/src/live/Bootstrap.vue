<script setup lang="ts">
import { ref } from 'vue'
import App from '../prototype/App.vue'
import Overview from './Overview.vue'
import Settings from './Settings.vue'
import { initialize } from './store'
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
</script>
<template>
  <App v-if="ready" :overview="Overview" :settings="Settings" />
  <main v-else class="panel empty-state">
    <h1>SeekBell</h1>
    <p role="status">{{ error || '正在连接工作空间…' }}</p>
    <button v-if="error" class="button primary" :disabled="busy" @click="start">重新连接</button>
  </main>
</template>
