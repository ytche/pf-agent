import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError } from '@/api/client'
import type {
  ChatAnswer,
  ConversationDetail,
  ConversationPage,
  ConversationSummary,
  Message,
} from '@/api/contract'
import { navigateToConversation } from '@/router'
import { storage } from '@/utils/storage'
import { nowIso, titleFromQuestion } from '@/utils/time'
import { useAuthStore } from './auth'

export type TurnErrorKind =
  | 'auth'
  | 'quota'
  | 'rate'
  | 'deleted'
  | 'changed'
  | 'notfound'
  | 'forbidden'
  | 'recovered'
  | 'network'
  | 'server'

export interface TurnError {
  kind: TurnErrorKind
  message: string
  question: string
  retryable: boolean
  /** 401 时是否可安全地按匿名语义重试（仅匿名/非账号会话为 true） */
  anonymousRetry?: boolean
}

/** 401 中断时暂存的未落库提问：登录或取消后据此恢复现场，不丢用户已输入的问题 */
export interface InterruptedTurn {
  conversationId: string
  question: string
  seq: number
}

export interface ConversationRuntime {
  summary: ConversationSummary
  messages: Message[]
  detailLoaded: boolean
  loading: boolean
  loadError: string | null
  pending: boolean
  unread: boolean
  turnError: TurnError | null
}

const PAGE_SIZE = 30

function makeRuntime(summary: ConversationSummary): ConversationRuntime {
  return {
    summary: { ...summary },
    messages: [],
    detailLoaded: false,
    loading: false,
    loadError: null,
    pending: false,
    unread: false,
    turnError: null,
  }
}

function lastSeq(messages: Message[]): number {
  return messages.reduce((max, message) => Math.max(max, message.seq), 0)
}

function compareSummaries(a: ConversationSummary, b: ConversationSummary): number {
  if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
  return b.updatedAt.localeCompare(a.updatedAt)
}

function toTurnError(error: unknown, question: string): TurnError {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return {
          kind: 'auth',
          message: '登录状态已失效，已清除本地登录态；可直接重试（匿名）或登录后继续',
          question,
          retryable: true,
        }
      case 403:
        return {
          kind: 'forbidden',
          message: error.message || '当前账号无权访问该会话',
          question,
          retryable: false,
        }
      case 404:
        return {
          kind: 'notfound',
          message: '会话不存在或已被删除，请新建会话',
          question,
          retryable: false,
        }
      case 409:
        return {
          kind: 'changed',
          message: '会话内容已变化，请重新打开会话后再试',
          question,
          retryable: false,
        }
      case 410:
        return {
          kind: 'deleted',
          message: '会话已被删除，本次回答已丢弃',
          question,
          retryable: false,
        }
      case 429:
        if (error.code === 'quota_exceeded') {
          return { kind: 'quota', message: error.message, question, retryable: false }
        }
        return {
          kind: 'rate',
          message: error.message || '请求过于频繁，请稍后再试',
          question,
          retryable: true,
        }
      case 0:
        return { kind: 'network', message: error.message, question, retryable: true }
      default:
        return {
          kind: 'server',
          message: error.message || '服务异常，请稍后重试',
          question,
          retryable: true,
        }
    }
  }
  return {
    kind: 'network',
    message: error instanceof Error ? error.message : '网络异常，请稍后重试',
    question,
    retryable: true,
  }
}

export const useConversationsStore = defineStore('conversations', () => {
  const conversations = ref<Record<string, ConversationRuntime>>({})
  const order = ref<string[]>([])
  const nextCursor = ref<string | null>(null)
  const listLoading = ref(false)
  const listError = ref<string | null>(null)
  const listLoaded = ref(false)
  const currentId = ref<string | null>(null)
  const anonymousIds = ref<string[]>(storage.getAnonymousIds())
  const interruptedTurn = ref<InterruptedTurn | null>(null)
  const claimNotice = ref('')
  const creating = ref(false)
  const booting = ref(true)
  const restoring = ref(false)

  const current = computed<ConversationRuntime | null>(() =>
    currentId.value ? conversations.value[currentId.value] ?? null : null,
  )
  const history = computed<ConversationRuntime[]>(() =>
    order.value.map((id) => conversations.value[id]).filter((item): item is ConversationRuntime => Boolean(item)),
  )
  const hasHistory = computed(() => history.value.length > 0)
  const pendingConversationIds = computed(() =>
    Object.values(conversations.value)
      .filter((runtime) => runtime.pending)
      .map((runtime) => runtime.summary.id),
  )

  function ensureRuntime(summary: ConversationSummary): ConversationRuntime {
    const existing = conversations.value[summary.id]
    if (existing) return existing
    const runtime = makeRuntime(summary)
    conversations.value[summary.id] = runtime
    return runtime
  }

  function sortOrder(): void {
    order.value = [...order.value].sort((a, b) => {
      const left = conversations.value[a]
      const right = conversations.value[b]
      if (!left || !right) return 0
      return compareSummaries(left.summary, right.summary)
    })
  }

  function addToOrder(id: string): void {
    if (!order.value.includes(id)) order.value.push(id)
    sortOrder()
  }

  function applySummary(summary: ConversationSummary): void {
    const runtime = ensureRuntime(summary)
    runtime.summary = { ...runtime.summary, ...summary }
  }

  function resetList(): void {
    order.value = []
    nextCursor.value = null
    listError.value = null
    listLoaded.value = false
  }

  async function loadAccountPage(): Promise<void> {
    resetList()
    listLoading.value = true
    try {
      const page: ConversationPage = await api.listConversations(null, PAGE_SIZE)
      page.items.forEach((item) => {
        applySummary(item)
        order.value.push(item.id)
      })
      nextCursor.value = page.nextCursor
      sortOrder()
      listLoaded.value = true
    } catch (error) {
      listError.value = error instanceof Error ? error.message : '历史读取失败'
      listLoaded.value = true
    } finally {
      listLoading.value = false
    }
  }

  async function loadAnonymous(): Promise<void> {
    resetList()
    if (anonymousIds.value.length === 0) {
      listLoaded.value = true
      return
    }
    listLoading.value = true
    try {
      const result = await api.lookupConversations([...anonymousIds.value])
      const returned = new Set(result.items.map((item) => item.id))
      result.items.forEach((item) => {
        applySummary(item)
        order.value.push(item.id)
      })
      sortOrder()
      // lookup 不返回的匿名 ID 视为已删除/已认领，从本机剔除，避免无限重试
      const stale = anonymousIds.value.filter((id) => !returned.has(id))
      if (stale.length > 0) anonymousIds.value = storage.removeAnonymousIds(stale)
      listLoaded.value = true
    } catch (error) {
      listError.value = error instanceof Error ? error.message : '匿名历史读取失败'
      listLoaded.value = true
    } finally {
      listLoading.value = false
    }
  }

  async function createConversation(force = false): Promise<string | null> {
    if (creating.value) return currentId.value
    if (!force) {
      const active = current.value
      if (active && active.summary.messageRounds === 0 && active.messages.length === 0) {
        navigateToConversation(active.summary.id)
        return active.summary.id
      }
    }
    creating.value = true
    try {
      const summary = await api.createConversation()
      ensureRuntime(summary)
      currentId.value = summary.id
      storage.setLastConversationId(summary.id)
      navigateToConversation(summary.id)
      return summary.id
    } catch {
      return null
    } finally {
      creating.value = false
    }
  }

  async function open(id: string): Promise<void> {
    currentId.value = id
    storage.setLastConversationId(id)
    navigateToConversation(id)
    let runtime = conversations.value[id]
    if (!runtime) {
      const now = nowIso()
      runtime = ensureRuntime({
        id,
        title: null,
        pinned: false,
        createdAt: now,
        updatedAt: now,
        messageRounds: 0,
      })
    }
    runtime.unread = false
    if (runtime.detailLoaded || runtime.loading) return
    runtime.loading = true
    runtime.loadError = null
    try {
      const detail: ConversationDetail = await api.getConversation(id)
      applyDetail(runtime, detail)
    } catch (error) {
      if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
        removeLocalConversation(id)
        if (currentId.value === id) currentId.value = null
        runtime.loadError = '会话不存在或已被删除'
      } else {
        runtime.loadError = error instanceof Error ? error.message : '历史读取失败'
      }
    } finally {
      runtime.loading = false
    }
  }

  function applyDetail(runtime: ConversationRuntime, detail: ConversationDetail): void {
    runtime.summary = { ...detail }
    runtime.messages = [...(detail.messages ?? [])].sort((a, b) => a.seq - b.seq)
    runtime.detailLoaded = true
    runtime.loadError = null
    if (runtime.summary.messageRounds > 0) addToOrder(detail.id)
  }

  function removeLocalConversation(id: string): void {
    delete conversations.value[id]
    order.value = order.value.filter((value) => value !== id)
    anonymousIds.value = storage.removeAnonymousIds([id])
  }

  function pushUserMessage(runtime: ConversationRuntime, question: string, retry: boolean): void {
    if (retry) {
      runtime.turnError = null
      return
    }
    const seq = lastSeq(runtime.messages) + 1
    runtime.messages.push({
      id: `local-user-${Date.now()}-${seq}`,
      seq,
      role: 'user',
      content: question,
      sources: null,
      gapReported: false,
      createdAt: nowIso(),
    })
  }

  function applyAnswer(runtime: ConversationRuntime, conversationId: string, answer: ChatAnswer, question: string): void {
    const seq = answer.messageSeq ?? lastSeq(runtime.messages) + 1
    runtime.messages.push({
      id: answer.messageId ?? `local-assistant-${Date.now()}-${seq}`,
      seq,
      role: 'assistant',
      content: answer.answer,
      sources: answer.sources ?? [],
      gapReported: Boolean(answer.gapReported),
      createdAt: nowIso(),
      completedAt: answer.completedAt ?? nowIso(),
    })
    const firstRound = runtime.summary.messageRounds === 0
    runtime.summary.messageRounds += 1
    if (!runtime.summary.title) runtime.summary.title = titleFromQuestion(question)
    runtime.summary.updatedAt = nowIso()
    if (firstRound) addToOrder(conversationId)
    sortOrder()
    if (!useAuthStore().isLoggedIn) {
      anonymousIds.value = storage.addAnonymousId(conversationId)
    }
  }

  async function send(question: string, options: { retry?: boolean } = {}): Promise<void> {
    const trimmed = question.trim()
    const runtime = current.value
    if (!trimmed || !runtime || runtime.pending) return
    const conversationId = runtime.summary.id
    pushUserMessage(runtime, trimmed, Boolean(options.retry))
    runtime.pending = true
    runtime.turnError = null
    try {
      const answer = await api.chat(trimmed, conversationId)
      const target = conversations.value[conversationId]
      if (!target) return
      applyAnswer(target, conversationId, answer, trimmed)
      if (interruptedTurn.value?.conversationId === conversationId) interruptedTurn.value = null
      if (currentId.value !== conversationId) target.unread = true
    } catch (error) {
      const failed = conversations.value[conversationId]
      if (!failed) return
      const wasLoggedIn = useAuthStore().isLoggedIn
      const turnError = toTurnError(error, trimmed)
      if (turnError.kind === 'auth') {
        turnError.anonymousRetry = !wasLoggedIn
        if (wasLoggedIn) turnError.message = '登录状态已失效，请重新登录后在原位置重试'
        interruptedTurn.value = {
          conversationId,
          question: trimmed,
          seq: lastSeq(failed.messages),
        }
        useAuthStore().invalidateSession()
      }
      failed.turnError = turnError
      if (turnError.kind === 'deleted') {
        removeLocalConversation(conversationId)
        if (currentId.value === conversationId) {
          currentId.value = null
          navigateToConversation(null)
        }
      }
    } finally {
      const settled = conversations.value[conversationId]
      if (settled) settled.pending = false
    }
  }

  function retry(): Promise<void> | undefined {
    const runtime = current.value
    if (!runtime || !runtime.turnError?.retryable || runtime.pending) return
    return send(runtime.turnError.question, { retry: true })
  }

  async function regenerate(): Promise<void> {
    const runtime = current.value
    if (!runtime || runtime.pending) return
    const index = runtime.messages.length - 1
    const last = runtime.messages[index]
    if (!last || last.role !== 'assistant') return
    const conversationId = runtime.summary.id
    const expectedLastSeq = last.seq
    runtime.pending = true
    runtime.turnError = null
    try {
      const answer = await api.regenerate(conversationId, expectedLastSeq)
      const target = conversations.value[conversationId]
      if (!target) return
      const currentIndex = target.messages.findIndex((message) => message.seq === expectedLastSeq && message.role === 'assistant')
      if (currentIndex >= 0) {
        target.messages.splice(currentIndex, 1, {
          ...target.messages[currentIndex],
          content: answer.answer,
          sources: answer.sources ?? [],
          gapReported: Boolean(answer.gapReported),
          completedAt: answer.completedAt ?? nowIso(),
        })
      }
      target.summary.updatedAt = nowIso()
      sortOrder()
      if (currentId.value !== conversationId) target.unread = true
    } catch (error) {
      const failed = conversations.value[conversationId]
      if (!failed) return
      const turnError = toTurnError(error, last.content)
      if (turnError.kind === 'auth') {
        turnError.anonymousRetry = false
        turnError.message = '登录状态已失效，请重新登录后再重新生成'
        useAuthStore().invalidateSession()
      }
      failed.turnError = turnError
      if (failed.turnError.kind === 'deleted') {
        removeLocalConversation(conversationId)
        if (currentId.value === conversationId) {
          currentId.value = null
          navigateToConversation(null)
        }
      }
    } finally {
      const settled = conversations.value[conversationId]
      if (settled) settled.pending = false
    }
  }

  async function rename(id: string, title: string): Promise<void> {
    const trimmed = title.trim()
    if (!trimmed) throw new Error('标题不能为空')
    const updated = await api.patchConversation(id, { title: trimmed })
    applySummary(updated)
    sortOrder()
  }

  async function togglePin(id: string): Promise<void> {
    const runtime = conversations.value[id]
    if (!runtime) return
    const updated = await api.patchConversation(id, { pinned: !runtime.summary.pinned })
    applySummary(updated)
    sortOrder()
  }

  async function remove(id: string): Promise<void> {
    try {
      await api.deleteConversation(id)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error
    }
    removeLocalConversation(id)
    if (currentId.value === id) {
      currentId.value = null
      navigateToConversation(null)
      await createConversation(true)
    }
  }

  async function loadMore(): Promise<void> {
    if (listLoading.value || !nextCursor.value) return
    listLoading.value = true
    try {
      const page = await api.listConversations(nextCursor.value, PAGE_SIZE)
      page.items.forEach((item) => {
        applySummary(item)
        if (!order.value.includes(item.id)) order.value.push(item.id)
      })
      nextCursor.value = page.nextCursor
      sortOrder()
    } catch (error) {
      listError.value = error instanceof Error ? error.message : '加载更多失败'
    } finally {
      listLoading.value = false
    }
  }

  async function reloadList(): Promise<void> {
    if (useAuthStore().isLoggedIn) {
      await loadAccountPage()
    } else {
      anonymousIds.value = storage.getAnonymousIds()
      await loadAnonymous()
    }
  }

  function restoreInterrupted(turn: InterruptedTurn, conversationId: string): void {
    const runtime = conversations.value[conversationId]
    if (!runtime) return
    const alreadyPersisted = runtime.messages.some(
      (message) => message.seq >= turn.seq && message.role === 'user' && message.content === turn.question,
    )
    if (!alreadyPersisted) {
      runtime.messages.push({
        id: `local-user-recovered-${Date.now()}`,
        seq: lastSeq(runtime.messages) + 1,
        role: 'user',
        content: turn.question,
        sources: null,
        gapReported: false,
        createdAt: nowIso(),
      })
    }
    runtime.turnError = {
      kind: 'recovered',
      message: '已恢复登录前未完成的提问，可在原位置手动重试',
      question: turn.question,
      retryable: true,
    }
    currentId.value = conversationId
    storage.setLastConversationId(conversationId)
    navigateToConversation(conversationId)
  }

  async function onLoggedIn(): Promise<void> {
    restoring.value = true
    try {
      await restoreAccountState()
    } finally {
      restoring.value = false
    }
  }

  async function restoreAccountState(): Promise<void> {
    const keep = currentId.value
    const interrupted = interruptedTurn.value
    const ids = [...new Set([...anonymousIds.value, ...(interrupted ? [interrupted.conversationId] : [])])]
    claimNotice.value = ''
    if (ids.length > 0) {
      try {
        const result = await api.claimConversations(ids)
        const resolved = [...result.claimed, ...result.alreadyOwned]
        if (resolved.length > 0) {
          anonymousIds.value = storage.removeAnonymousIds(resolved)
          claimNotice.value = `已将 ${resolved.length} 个匿名会话认领到当前账号`
        }
        if (result.rejected.length > 0) {
          claimNotice.value = `${claimNotice.value}，${result.rejected.length} 个会话无法认领（已归属其他账号或不存在）`
        }
      } catch {
        claimNotice.value = '匿名会话认领失败，本机记录已保留，可退出后重新登录重试'
      }
    }
    resetConversationState()
    await loadAccountPage()

    if (interrupted) {
      await open(interrupted.conversationId)
      if (conversations.value[interrupted.conversationId]) {
        restoreInterrupted(interrupted, interrupted.conversationId)
        interruptedTurn.value = null
        return
      }
      // 原会话已不可访问（被删除/归属他人）：新建空白会话恢复未落库问题，问题不丢
      const created = await createConversation(true)
      if (created) {
        restoreInterrupted(interrupted, created)
        interruptedTurn.value = null
        return
      }
    }

    if (keep && conversations.value[keep]) {
      await open(keep)
    } else if (order.value.length > 0) {
      await open(order.value[0])
    } else {
      await createConversation(true)
    }
  }

  function resetConversationState(): void {
    conversations.value = {}
    order.value = []
    currentId.value = null
    nextCursor.value = null
    listError.value = null
    listLoaded.value = false
  }

  async function logoutReset(): Promise<void> {
    resetConversationState()
    claimNotice.value = ''
    storage.setLastConversationId(null)
    navigateToConversation(null)
    await bootstrap()
  }

  async function bootstrap(): Promise<void> {
    booting.value = true
    try {
      if (useAuthStore().isLoggedIn) {
        await loadAccountPage()
      } else {
        anonymousIds.value = storage.getAnonymousIds()
        await loadAnonymous()
      }
      const hashMatch = /^#\/c\/([^/?#]+)/.exec(window.location.hash)
      const hashId = hashMatch ? decodeURIComponent(hashMatch[1]) : ''
      const candidate = hashId || storage.getLastConversationId()
      if (candidate) {
        await open(candidate)
        if (currentId.value) return
      }
      if (!hashId && order.value.length > 0) {
        await open(order.value[0])
        return
      }
      await createConversation(true)
    } finally {
      booting.value = false
    }
  }

  function clearClaimNotice(): void {
    claimNotice.value = ''
  }

  return {
    conversations,
    order,
    nextCursor,
    listLoading,
    listError,
    listLoaded,
    currentId,
    current,
    history,
    hasHistory,
    pendingConversationIds,
    anonymousIds,
    interruptedTurn,
    claimNotice,
    booting,
    restoring,
    bootstrap,
    createConversation,
    open,
    send,
    retry,
    regenerate,
    rename,
    togglePin,
    remove,
    loadMore,
    reloadList,
    onLoggedIn,
    logoutReset,
    clearClaimNotice,
  }
})
