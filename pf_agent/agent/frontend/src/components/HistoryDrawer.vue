<script setup lang="ts">
import { onBeforeUnmount, onMounted, nextTick, ref } from 'vue'
import { useConversationsStore, type ConversationRuntime } from '@/stores/conversations'
import { formatTime } from '@/utils/time'

defineProps<{
  open: boolean
  items: ConversationRuntime[]
  currentId: string | null
  nextCursor: string | null
  loading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  close: []
  new: []
  select: [id: string]
  'load-more': []
  reload: []
}>()

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

const conversations = useConversationsStore()
const editingId = ref<string | null>(null)
const draftTitle = ref('')
const confirmingId = ref<string | null>(null)
const actionError = ref('')

function startRename(item: ConversationRuntime): void {
  editingId.value = item.summary.id
  draftTitle.value = item.summary.title ?? ''
  confirmingId.value = null
  actionError.value = ''
  void nextTick(() => {
    const input = document.querySelector<HTMLInputElement>('.rename-input')
    input?.focus()
    input?.select()
  })
}

async function commitRename(): Promise<void> {
  const id = editingId.value
  if (!id) return
  try {
    await conversations.rename(id, draftTitle.value)
    editingId.value = null
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '重命名失败'
  }
}

function cancelRename(): void {
  editingId.value = null
  actionError.value = ''
}

function startDelete(id: string): void {
  confirmingId.value = id
  editingId.value = null
  actionError.value = ''
}

async function confirmDelete(id: string): Promise<void> {
  try {
    await conversations.remove(id)
    confirmingId.value = null
  } catch {
    actionError.value = '删除失败，请稍后重试'
  }
}

async function togglePin(id: string): Promise<void> {
  actionError.value = ''
  try {
    await conversations.togglePin(id)
  } catch {
    actionError.value = '置顶状态更新失败'
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="drawer-root">
      <div class="drawer-mask" @click="emit('close')"></div>
      <aside class="drawer" role="dialog" aria-label="历史会话">
        <header class="drawer-head">
          <h2>历史</h2>
          <div class="drawer-head-actions">
            <button class="primary small" type="button" @click="emit('new')">新会话</button>
            <button class="ghost small drawer-close" type="button" @click="emit('close')">返回</button>
          </div>
        </header>

        <p v-if="actionError" class="inline-error">{{ actionError }}</p>
        <p v-if="error" class="inline-error">
          {{ error }}
          <button class="link" type="button" @click="emit('reload')">重试</button>
        </p>

        <div class="drawer-body">
          <p v-if="!items.length && !loading" class="empty-note">暂无历史会话</p>

          <ul class="history-list">
            <li
              v-for="item in items"
              :key="item.summary.id"
              class="history-item"
              :class="{ active: item.summary.id === currentId }"
            >
              <template v-if="editingId === item.summary.id">
                <form class="rename-form" @submit.prevent="commitRename">
                  <input v-model="draftTitle" class="rename-input" maxlength="120" aria-label="会话标题" />
                  <button class="primary small" type="submit">保存</button>
                  <button class="ghost small" type="button" @click="cancelRename">取消</button>
                </form>
              </template>

              <template v-else-if="confirmingId === item.summary.id">
                <div class="delete-confirm">
                  <span>永久删除该会话？</span>
                  <button class="danger small" type="button" @click="confirmDelete(item.summary.id)">删除</button>
                  <button class="ghost small" type="button" @click="confirmingId = null">取消</button>
                </div>
              </template>

              <template v-else>
                <button class="history-main" type="button" @click="emit('select', item.summary.id)">
                  <span class="history-title">
                    <span v-if="item.summary.pinned" class="pin-mark" aria-label="已置顶">📌</span>
                    {{ item.summary.title || '未命名会话' }}
                  </span>
                  <span class="history-meta">
                    <span v-if="item.pending" class="pending-text">回答中…</span>
                    <span v-else>{{ formatTime(item.summary.updatedAt) }}</span>
                  </span>
                </button>
                <span v-if="item.unread" class="unread-dot" aria-label="有未读回答"></span>
                <div class="history-actions">
                  <button class="link" type="button" @click.stop="togglePin(item.summary.id)">
                    {{ item.summary.pinned ? '取消置顶' : '置顶' }}
                  </button>
                  <button class="link" type="button" @click.stop="startRename(item)">重命名</button>
                  <button class="link danger-text" type="button" @click.stop="startDelete(item.summary.id)">删除</button>
                </div>
              </template>
            </li>
          </ul>

          <div v-if="nextCursor" class="load-more">
            <button class="ghost" type="button" :disabled="loading" @click="emit('load-more')">
              {{ loading ? '加载中…' : '加载更多' }}
            </button>
          </div>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
