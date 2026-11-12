<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { Message, Source } from '@/api/contract'
import FeedbackForm from '@/components/FeedbackForm.vue'
import MarkdownAnswer from '@/components/MarkdownAnswer.vue'
import SourceCards from '@/components/SourceCards.vue'
import { formatTime } from '@/utils/time'

const props = defineProps<{
  message: Message
  question: string
  conversationId: string
  isLast: boolean
}>()

const emit = defineEmits<{ regenerate: [] }>()

const sourcesRef = ref<InstanceType<typeof SourceCards> | null>(null)
const feedbackOpen = ref(false)
const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | undefined

const sources = computed<Source[] | null>(() => props.message.sources)

function focusSource(n: number): void {
  void sourcesRef.value?.focusSource(n)
}

async function copyAnswer(): Promise<void> {
  const text = props.message.content
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    copied.value = true
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copied.value = false
    }, 1800)
  } catch {
    copied.value = false
  }
}

async function openFeedback(): Promise<void> {
  feedbackOpen.value = true
  await nextTick()
}
</script>

<template>
  <article class="assistant-answer">
    <MarkdownAnswer :content="message.content" @cite="focusSource" />

    <p v-if="message.gapReported" class="gap-tip">本次回答记录了数据缺口，将纳入后续优化。</p>

    <SourceCards ref="sourcesRef" :sources="sources" />

    <footer class="answer-actions">
      <time class="answer-time">{{ formatTime(message.completedAt || message.createdAt) }}</time>
      <button class="link" type="button" @click="copyAnswer">{{ copied ? '已复制' : '复制' }}</button>
      <button v-if="isLast" class="link" type="button" @click="emit('regenerate')">重新生成</button>
      <button class="link" type="button" @click="openFeedback">标错</button>
    </footer>

    <FeedbackForm
      v-if="feedbackOpen"
      :conversation-id="conversationId"
      :question="question"
      :answer="message.content"
      :sources="sources ?? []"
      @close="feedbackOpen = false"
    />
  </article>
</template>
