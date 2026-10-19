<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { NButton } from 'naive-ui'
import TargetsPanel from './TargetsPanel.vue'
const DeliveriesPanel = defineAsyncComponent(() => import('./DeliveriesPanel.vue'))
defineProps<{ csrf: string }>()
const tab = ref('targets')
</script>
<template>
  <div class="subtab-bar" role="tablist" aria-label="通知管理标签">
    <NButton
      role="tab"
      :aria-selected="tab === 'targets'"
      :type="tab === 'targets' ? 'primary' : 'default'"
      :secondary="tab !== 'targets'"
      @click="tab = 'targets'"
      >目标配置</NButton
    ><NButton
      role="tab"
      :aria-selected="tab === 'records'"
      :type="tab === 'records' ? 'primary' : 'default'"
      :secondary="tab !== 'records'"
      @click="tab = 'records'"
      >投递记录</NButton
    >
  </div>
  <TargetsPanel v-if="tab === 'targets'" :csrf="csrf" /><DeliveriesPanel v-else :csrf="csrf" />
</template>
