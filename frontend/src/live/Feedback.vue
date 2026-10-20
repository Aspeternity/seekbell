<script setup lang="ts">
defineProps<{ loading: boolean; error: string }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <p v-if="loading" class="info-note" role="status">正在读取服务端记录…</p>
  <div v-else-if="error" class="form-errors" role="alert">
    <p>{{ error }}</p>
    <button class="button" @click="$emit('retry')">重新加载</button>
  </div>
</template>
