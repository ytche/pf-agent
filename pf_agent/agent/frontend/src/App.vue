<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppShell from '@/components/AppShell.vue'
import AuthDialog from '@/components/AuthDialog.vue'
import Composer from '@/components/Composer.vue'
import ConversationView from '@/components/ConversationView.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'

const auth = useAuthStore()
const conversations = useConversationsStore()
const drawerOpen = ref(false)

onMounted(async () => {
  await auth.bootstrap()
  await conversations.bootstrap()
})

async function handleSend(question: string): Promise<void> {
  await conversations.send(question)
}

function openHistory(): void {
  drawerOpen.value = true
}

async function newConversation(): Promise<void> {
  drawerOpen.value = false
  await conversations.createConversation(false)
}

async function selectConversation(id: string): Promise<void> {
  drawerOpen.value = false
  await conversations.open(id)
}
</script>

<template>
  <div class="app">
    <AppShell @history="openHistory" @new-conversation="newConversation" />

    <div v-if="conversations.claimNotice" class="notice" role="status">
      <span>{{ conversations.claimNotice }}</span>
      <button class="link" type="button" @click="conversations.clearClaimNotice()">知道了</button>
    </div>

    <main class="main">
      <ConversationView
        @ask="handleSend"
        @retry="conversations.retry()"
        @regenerate="conversations.regenerate()"
        @login="auth.openDialog('login')"
        @new-conversation="newConversation"
      />
    </main>

    <Composer
      :pending="Boolean(conversations.current?.pending)"
      :disabled="!conversations.current || conversations.restoring"
      :conversation-id="conversations.currentId"
      @send="handleSend"
    />

    <HistoryDrawer
      :open="drawerOpen"
      :items="conversations.history"
      :current-id="conversations.currentId"
      :next-cursor="conversations.nextCursor"
      :loading="conversations.listLoading"
      :error="conversations.listError"
      @close="drawerOpen = false"
      @new="newConversation"
      @select="selectConversation"
      @load-more="conversations.loadMore()"
      @reload="conversations.reloadList()"
    />

    <AuthDialog @logged-in="conversations.onLoggedIn()" />
  </div>
</template>
