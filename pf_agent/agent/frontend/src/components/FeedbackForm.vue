<script setup lang="ts">
import { ref } from 'vue'
import { api, ApiError } from '@/api/client'
import type { Source } from '@/api/contract'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  conversationId: string
  question: string
  answer: string
  sources: Source[]
}>()

const emit = defineEmits<{ close: [] }>()

const ERROR_TYPES = ['事实错误', '检索漏召回', '编造来源', '答非所问', '结构差']
const auth = useAuthStore()

const errorType = ref('')
const correction = ref('')
const comment = ref('')
const busy = ref(false)
const status = ref<'idle' | 'ok' | 'error'>('idle')
const message = ref('')

async function submit(): Promise<void> {
  if (!errorType.value) {
    status.value = 'error'
    message.value = '请先选择错误类型'
    return
  }
  busy.value = true
  status.value = 'idle'
  message.value = ''
  try {
    const result = await api.feedback({
      conversationId: props.conversationId,
      question: props.question,
      answer: props.answer,
      sources: props.sources,
      errorType: errorType.value,
      correction: correction.value.trim() || null,
      comment: comment.value.trim() || null,
    })
    if (result.ok) {
      status.value = 'ok'
      message.value = `已记录标注${result.id ? `（${result.id}）` : ''}，将纳入优化分析`
    } else {
      status.value = 'error'
      message.value = '标注提交失败，请稍后重试'
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      auth.invalidateSession()
      message.value = '登录状态已失效，请重新登录后提交'
    } else {
      message.value = '标注提交失败，请稍后重试'
    }
    status.value = 'error'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="feedback-form" @submit.prevent="submit">
    <label class="field">
      <span>错误类型</span>
      <select v-model="errorType" aria-label="错误类型">
        <option value="" disabled>选择错误类型…</option>
        <option v-for="type in ERROR_TYPES" :key="type" :value="type">{{ type }}</option>
      </select>
    </label>
    <label class="field">
      <span>正确说法（可选）</span>
      <textarea v-model="correction" rows="2" placeholder="写下正确内容，便于核对"></textarea>
    </label>
    <label class="field">
      <span>备注（可选）</span>
      <textarea v-model="comment" rows="2" placeholder="哪句话不对、期望怎样"></textarea>
    </label>
    <p v-if="message" class="feedback-status" :class="status">{{ message }}</p>
    <div class="feedback-actions">
      <button class="primary small" type="submit" :disabled="busy">{{ busy ? '提交中…' : '提交标注' }}</button>
      <button class="ghost small" type="button" @click="emit('close')">关闭</button>
    </div>
  </form>
</template>
