<script setup lang="ts">
import MessageItem from '@/components/MessageItem.vue'
import type { Message } from '@/api/contract'

const props = defineProps<{
  messages: Message[]
  conversationId: string
}>()

const emit = defineEmits<{ regenerate: [] }>()

function questionBefore(index: number): string {
  for (let i = index - 1; i >= 0; i -= 1) {
    const message = props.messages[i]
    if (message.role === 'user') return message.content
  }
  return ''
}
</script>

<template>
  <ol class="message-list">
    <template v-for="(message, index) in messages" :key="message.id">
      <li v-if="message.role === 'user'" class="turn turn-user">
        <div class="user-bubble">{{ message.content }}</div>
      </li>
      <li v-else class="turn turn-assistant">
        <MessageItem
          :message="message"
          :question="questionBefore(index)"
          :conversation-id="conversationId"
          :is-last="index === messages.length - 1"
          @regenerate="emit('regenerate')"
        />
      </li>
    </template>
  </ol>
</template>
