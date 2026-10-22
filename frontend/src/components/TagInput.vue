<script setup lang="ts">
import { ref } from 'vue'
import Icon from './Icon.vue'
const props = withDefaults(
  defineProps<{ modelValue: string[]; label: string; placeholder?: string; tone?: string }>(),
  { placeholder: '输入后按回车添加', tone: '' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const input = ref('')
function add() {
  const value = input.value.trim()
  if (value && !props.modelValue.includes(value) && props.modelValue.length < 64)
    emit('update:modelValue', [...props.modelValue, value])
  input.value = ''
}
</script>
<template>
  <div class="tag-input" :class="tone">
    <span v-for="(tag, i) in modelValue" :key="tag" class="tag"
      >{{ tag
      }}<button
        type="button"
        :aria-label="'删除' + label + '：' + tag"
        @click="
          emit(
            'update:modelValue',
            modelValue.filter((_, index) => index !== i),
          )
        "
      >
        <Icon name="close" :size="12" /></button></span
    ><input
      v-model="input"
      :aria-label="label"
      :placeholder="modelValue.length ? '添加…' : placeholder"
      maxlength="200"
      @keydown.enter.prevent="
        (event) => {
          if (!event.isComposing) add()
        }
      "
      @keydown="
        (event) => {
          if (event.key === ',' && !event.isComposing) {
            event.preventDefault()
            add()
          }
        }
      "
      @blur="add"
    />
  </div>
</template>
