<script setup lang="ts">
import { NButton, NCard, NDynamicTags, NFormItem, NSwitch } from 'naive-ui'
import type { Rule } from '../management'

defineProps<{ disabled: boolean }>()
const rule = defineModel<Rule>({ required: true })
const scopes = [
  { value: 'title', label: '仅标题' },
  { value: 'summary', label: '仅摘要' },
  { value: 'title_summary', label: '标题＋摘要' },
]
const modes = [
  { value: 'contains', label: '包含匹配' },
  { value: 'english_word', label: '英文整词匹配' },
]
const tags = [
  ['exclude', '排除词'],
  ['authors_include', '包含作者'],
  ['authors_exclude', '排除作者'],
  ['categories', '版块'],
] as const
</script>

<template>
  <div aria-label="规则编辑器">
    <div class="form-grid">
      <NFormItem label="匹配范围" :label-props="{ for: 'rule-scope' }">
        <select id="rule-scope" v-model="rule.scope" class="native-select" :disabled="disabled">
          <option v-for="option in scopes" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </NFormItem>
      <NFormItem label="匹配模式" :label-props="{ for: 'rule-mode' }">
        <select id="rule-mode" v-model="rule.mode" class="native-select" :disabled="disabled">
          <option v-for="option in modes" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </NFormItem>
      <NFormItem label="区分英文大小写"
        ><NSwitch
          v-model:value="rule.case_sensitive"
          :disabled="disabled"
          aria-label="区分英文大小写"
      /></NFormItem>
    </div>
    <p class="muted">
      每次输入一个词或短语，按 Enter
      保存标签，短语中的空格会保留。作者与版块按原字段精确匹配；未知字段可能导致信息不足。
    </p>
    <NCard
      v-for="(group, index) in rule.groups"
      :key="index"
      :title="'条件组 ' + (index + 1)"
      class="condition-card"
    >
      <NFormItem label="全部包含">
        <div @keydown.enter.prevent>
          <NDynamicTags
            v-model:value="group.all_of"
            :disabled="disabled"
            :max="64"
            :input-props="{
              maxlength: 200,
              inputProps: { 'aria-label': '条件组 ' + (index + 1) + ' 全部包含标签' },
            }"
          >
            <template #trigger="{ activate }"
              ><NButton :disabled="disabled || group.all_of.length >= 64" @click="activate"
                >添加组 {{ index + 1 }} 全部包含标签</NButton
              ></template
            >
          </NDynamicTags>
        </div>
      </NFormItem>
      <NFormItem label="至少包含一个">
        <div @keydown.enter.prevent>
          <NDynamicTags
            v-model:value="group.any_of"
            :disabled="disabled"
            :max="64"
            :input-props="{
              maxlength: 200,
              inputProps: { 'aria-label': '条件组 ' + (index + 1) + ' 至少包含一个标签' },
            }"
          >
            <template #trigger="{ activate }"
              ><NButton :disabled="disabled || group.any_of.length >= 64" @click="activate"
                >添加组 {{ index + 1 }} 至少包含一个标签</NButton
              ></template
            >
          </NDynamicTags>
        </div>
      </NFormItem>
      <NButton :disabled="disabled" @click="rule.groups.splice(index, 1)"
        >删除条件组 {{ index + 1 }}</NButton
      >
    </NCard>
    <NButton
      :disabled="disabled || rule.groups.length >= 16"
      @click="rule.groups.push({ all_of: [], any_of: [] })"
      >添加条件组</NButton
    >
    <p class="muted">组内非空条件全部满足，组间满足任一组；排除词优先否决。空条件组会被忽略。</p>
    <div class="form-grid">
      <NFormItem v-for="[key, label] in tags" :key="key" :label="label">
        <div @keydown.enter.prevent>
          <NDynamicTags
            v-model:value="rule[key]"
            :disabled="disabled"
            :max="64"
            :input-props="{ maxlength: 200, inputProps: { 'aria-label': label + '标签' } }"
          >
            <template #trigger="{ activate }"
              ><NButton :disabled="disabled || rule[key].length >= 64" @click="activate"
                >添加{{ label }}标签</NButton
              ></template
            >
          </NDynamicTags>
        </div>
      </NFormItem>
    </div>
  </div>
</template>
