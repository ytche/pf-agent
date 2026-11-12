<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  pending: boolean
  disabled: boolean
  conversationId: string | null
}>()

const emit = defineEmits<{ send: [question: string] }>()

const value = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

watch(
  () => props.conversationId,
  () => {
    // 未发送草稿不持久化：切换/新建会话即清空并复位输入高度
    value.value = ''
    void nextTick(() => {
      if (textarea.value) textarea.value.style.height = ''
    })
  },
)

function resize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  const max = 8 * 24
  el.style.height = `${Math.min(el.scrollHeight, max)}px`
}

function submit(): void {
  const question = value.value.trim()
  if (!question || props.disabled || props.pending) return
  emit('send', question)
  value.value = ''
  void nextTick(() => {
    resize()
    textarea.value?.focus()
  })
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  submit()
}
</script>

<template>
  <div class="composer-wrap">
    <div class="composer">
      <textarea
        ref="textarea"
        v-model="value"
        class="composer-input"
        rows="1"
        placeholder="输入规则问题，Enter 发送，Shift+Enter 换行"
        aria-label="输入规则问题"
        :disabled="disabled"
        @input="resize"
        @keydown="onKeydown"
      ></textarea>
      <button class="send-btn" type="button" :disabled="disabled || pending || !value.trim()" @click="submit">
        发送
      </button>
    </div>
    <p v-if="pending" class="composer-hint">该会话正在回答，完成后可继续发送；可以切换或新建其他会话。</p>
  </div>
</template>
