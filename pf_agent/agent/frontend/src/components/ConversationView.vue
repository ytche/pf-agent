<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import MessageList from '@/components/MessageList.vue'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'

const emit = defineEmits<{
  ask: [question: string]
  retry: []
  regenerate: []
  login: []
  'new-conversation': []
}>()

const conversations = useConversationsStore()
const auth = useAuthStore()
const scroller = ref<HTMLElement | null>(null)
const atBottom = ref(true)
const showNewAnswer = ref(false)

const current = computed(() => conversations.current)
const messages = computed(() => current.value?.messages ?? [])
const examples = [
  '借机攻击在什么情况下触发？',
  '女巫 1 环法术有哪些？',
  '法师 20 级成长表是什么？',
  '肩部奇物有哪些？',
]

function scrollToBottom(behavior: ScrollBehavior = 'auto'): void {
  const el = scroller.value
  if (!el) return
  el.scrollTo?.({ top: el.scrollHeight, behavior })
  atBottom.value = true
  showNewAnswer.value = false
}

function onScroll(): void {
  const el = scroller.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  atBottom.value = distance < 56
  if (atBottom.value) showNewAnswer.value = false
}

watch(
  () => conversations.currentId,
  () => {
    showNewAnswer.value = false
    void nextTick(() => scrollToBottom('auto'))
  },
)

watch(
  () => messages.value.length,
  async (next, previous) => {
    if (next <= previous) return
    const last = messages.value[next - 1]
    if (atBottom.value) {
      await nextTick()
      scrollToBottom('smooth')
    } else if (last?.role === 'assistant') {
      showNewAnswer.value = true
    }
  },
)

function ask(question: string): void {
  if (current.value?.pending) return
  emit('ask', question)
}

async function reload(): Promise<void> {
  const id = conversations.currentId
  if (!id) return
  const runtime = conversations.conversations[id]
  if (runtime) runtime.detailLoaded = false
  await conversations.open(id)
}
</script>

<template>
  <section class="conversation">
    <div ref="scroller" class="scroll-area" @scroll.passive="onScroll">
      <div class="conversation-inner">
        <p v-if="conversations.booting || conversations.restoring" class="loading-note">
          {{ conversations.restoring ? '正在恢复账号会话…' : '正在加载…' }}
        </p>

        <template v-else-if="current">
          <p v-if="current.loading && !current.messages.length" class="loading-note">正在读取历史…</p>

          <div v-else-if="current.loadError" class="load-error" role="alert">
            <p>{{ current.loadError }}</p>
            <div class="load-error-actions">
              <button class="ghost" type="button" @click="reload">重试</button>
              <button class="primary" type="button" @click="emit('new-conversation')">新建会话</button>
            </div>
          </div>

          <div v-else-if="!current.messages.length" class="welcome">
            <h2>有什么规则问题？</h2>
            <p class="welcome-sub">可以直接提问，回答会标注来源；来源默认展开 3 张，可查看全部。</p>
            <p v-if="auth.memoryMode" class="temp-mode">临时模式：重启后历史清空，登录与跨设备同步不可用。</p>
            <div class="examples">
              <button v-for="question in examples" :key="question" class="example" type="button" @click="ask(question)">
                {{ question }}
              </button>
            </div>
          </div>

          <MessageList
            v-else
            :messages="current.messages"
            :conversation-id="current.summary.id"
            @regenerate="emit('regenerate')"
          />

          <div v-if="current.pending" class="waiting" role="status">
            <span class="waiting-dot"></span>
            正在检索并生成回答…
          </div>

          <div v-if="current.turnError" class="turn-error" role="alert">
            <p>{{ current.turnError.message }}</p>
            <div class="turn-error-actions">
              <template v-if="current.turnError.kind === 'auth'">
                <button
                  v-if="current.turnError.anonymousRetry"
                  class="primary"
                  type="button"
                  @click="emit('retry')"
                >
                  重试（匿名）
                </button>
                <button
                  :class="current.turnError.anonymousRetry ? 'ghost' : 'primary'"
                  type="button"
                  @click="emit('login')"
                >
                  登录
                </button>
              </template>
              <button
                v-else-if="current.turnError.kind === 'quota'"
                class="primary"
                type="button"
                @click="emit('new-conversation')"
              >
                新建会话
              </button>
              <button
                v-else-if="current.turnError.retryable"
                class="primary"
                type="button"
                @click="emit('retry')"
              >
                重试
              </button>
              <button
                v-else-if="current.turnError.kind === 'notfound' || current.turnError.kind === 'deleted'"
                class="primary"
                type="button"
                @click="emit('new-conversation')"
              >
                新建会话
              </button>
            </div>
          </div>
        </template>

        <div v-else class="welcome">
          <h2>会话不可用</h2>
          <p class="welcome-sub">当前会话不存在或读取失败，请新建会话继续提问。</p>
          <button class="primary" type="button" @click="emit('new-conversation')">新建会话</button>
        </div>
      </div>
    </div>

    <button v-if="showNewAnswer" class="new-answer" type="button" @click="scrollToBottom('smooth')">
      有新回答 ↓
    </button>
  </section>
</template>
