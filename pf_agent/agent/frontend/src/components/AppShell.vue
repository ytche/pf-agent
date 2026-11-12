<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'

const auth = useAuthStore()
const conversations = useConversationsStore()
const menuOpen = ref(false)
const accountRef = ref<HTMLElement | null>(null)

defineEmits<{ history: []; 'new-conversation': [] }>()

function closeMenu(event: MouseEvent): void {
  if (!menuOpen.value) return
  const target = event.target as Node | null
  if (target && accountRef.value?.contains(target)) return
  menuOpen.value = false
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') menuOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', closeMenu)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeMenu)
  document.removeEventListener('keydown', onDocumentKeydown)
})

async function logout(): Promise<void> {
  menuOpen.value = false
  auth.logout()
  await conversations.logoutReset()
}
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">PF</span>
        <div class="brand-text">
          <span class="brand-title">PathFinder 1e 规则问答</span>
          <span class="brand-sub">回答基于规则库检索，来源可追溯</span>
        </div>
      </div>

      <div class="topbar-actions">
        <button class="ghost" type="button" @click="$emit('history')">历史</button>
        <button class="primary" type="button" @click="$emit('new-conversation')">新会话</button>

        <div v-if="auth.isLoggedIn" ref="accountRef" class="account">
          <button class="ghost account-btn" type="button" :aria-expanded="menuOpen" @click.stop="menuOpen = !menuOpen">
            {{ auth.displayName }} <span aria-hidden="true">▾</span>
          </button>
          <div v-if="menuOpen" class="account-menu" role="menu">
            <a v-if="auth.isAdmin" class="menu-item" href="/admin/" role="menuitem">管理后台</a>
            <button class="menu-item" type="button" role="menuitem" @click="logout">退出登录</button>
          </div>
        </div>
        <button v-else-if="auth.enabled" class="ghost" type="button" @click="auth.openDialog('login')">
          登录 / 注册
        </button>
      </div>
    </div>
  </header>
</template>
