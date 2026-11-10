<script setup lang="ts">
import { ref, watch } from 'vue'
import { notify, request } from '../store'
import { byteSize, stamp } from '../settings'
import type { Leftover } from '../backups'
import Icon from './Icon.vue'
const props = defineProps<{ leftovers: Leftover[]; needPassword: boolean }>()
const emit = defineEmits<{ dirty: [value: boolean]; changed: [] }>()
const kinds = { previous: '恢复前的旧数据', candidate: '恢复验证副本' }
// One leftover at a time is being confirmed for deletion.
const removing = ref(''),
  password = ref(''),
  busy = ref(false),
  error = ref('')
watch(
  () => !!password.value || busy.value,
  (value) => emit('dirty', value),
)
function choose(id: string) {
  removing.value = id
  password.value = ''
  error.value = ''
}
async function remove() {
  if (busy.value || !removing.value) return
  busy.value = true
  error.value = ''
  try {
    await request(
      'manage/backups/leftovers/' + encodeURIComponent(removing.value),
      'DELETE',
      props.needPassword ? { current_password: password.value } : {},
    )
    removing.value = ''
    notify('恢复残留已删除。')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    password.value = ''
    busy.value = false
    emit('changed')
  }
}
</script>
<template>
  <section
    v-if="leftovers.length"
    id="restore-leftovers"
    class="panel settings-card"
    aria-labelledby="leftovers-title"
  >
    <div class="panel-heading">
      <div>
        <h2 id="leftovers-title">恢复残留</h2>
        <p>恢复备份时被替换下来的旧数据</p>
      </div>
    </div>
    <div class="form-content form-stack">
      <p class="small-note">
        每次恢复备份都会把被替换的整份旧数据留在服务器上。确认恢复结果无误后可以删除，当前数据不受影响。
      </p>
      <p v-if="error" class="warning-note" role="alert">{{ error }}</p>
      <ul class="storage-leftover-list">
        <li v-for="row in leftovers" :key="row.id">
          <div class="storage-leftover-row">
            <strong>{{ kinds[row.kind] }}</strong>
            <span>{{ stamp(row.at) }}</span>
            <span>{{ byteSize(row.bytes) }}</span>
            <button
              v-if="removing !== row.id"
              type="button"
              class="button danger-outline"
              :disabled="busy"
              @click="choose(row.id)"
            >
              <Icon name="trash" :size="14" />删除
            </button>
          </div>
          <form
            v-if="removing === row.id"
            class="backup-discard"
            aria-label="删除恢复残留"
            @submit.prevent="remove"
          >
            <template v-if="needPassword">
              <label :for="'leftover-password-' + row.id">当前管理员密码</label>
              <input
                :id="'leftover-password-' + row.id"
                v-model="password"
                class="text-input"
                type="password"
                autocomplete="current-password"
                maxlength="128"
                required
                :disabled="busy"
              />
            </template>
            <button class="button danger-outline" :disabled="busy || (needPassword && !password)">
              {{ busy ? '正在删除…' : '确认删除' }}
            </button>
            <button type="button" class="button" :disabled="busy" @click="choose('')">取消</button>
            <p class="small-note">删除后无法找回。</p>
          </form>
        </li>
      </ul>
    </div>
  </section>
</template>
