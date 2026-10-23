<script setup lang="ts">
import Icon from './Icon.vue'
defineProps<{ page: number; total: number; pageSize: number; label: string }>()
const emit = defineEmits<{ change: [page: number] }>()
</script>
<template>
  <div class="pagination">
    <span>共 {{ total }} 条 · 每页 {{ pageSize }} 条</span>
    <div>
      <button
        class="icon-button"
        :disabled="page <= 1"
        :aria-label="'上一页' + label"
        @click="emit('change', page - 1)"
      >
        <Icon name="back" :size="16" />
      </button>
      <span>{{ page }} / {{ Math.max(1, Math.ceil(total / pageSize)) }}</span>
      <button
        class="icon-button"
        :disabled="page >= Math.ceil(total / pageSize)"
        :aria-label="'下一页' + label"
        @click="emit('change', page + 1)"
      >
        <Icon name="arrow" :size="16" />
      </button>
    </div>
  </div>
</template>
