import type { Page, Route } from '@playwright/test'

export interface StubSource {
  book: string
  bookNameCn?: string | null
  bookAbbreviation?: string | null
  tocPath: string
  content: string
  chunkId?: string
}

export interface StubMessage {
  id: number
  seq: number
  role: 'user' | 'assistant'
  content: string
  sources: StubSource[] | null
  gapReported: boolean
  createdAt: string
  completedAt: string | null
}

export interface StubConversation {
  id: string
  title: string | null
  pinned: boolean
  createdAt: string
  updatedAt: string
  messageRounds: number
  messages: StubMessage[]
  owner: string | null
  deleted: boolean
}

export interface StubOptions {
  /** 每个问答/重新生成的模拟耗时，用于验证后台完成与等待态 */
  delayMs?: number
  /** 自定义回答内容（打桩 ChatModel 语义）；默认回答引用 [#4] 便于验证上标定位 */
  answer?: (question: string) => { answer: string; sources: StubSource[]; gapReported?: boolean }
  /** 模拟限频/配额 */
  throttle?: 'quota' | 'rate' | null
}

export interface StubState {
  conversations: Map<string, StubConversation>
  username: string | null
  counter: number
}

const TOKEN = 'stub-token'

function defaultAnswer(question: string) {
  return {
    answer: `${question}\n\n规则说明：当敌人离开你的威胁范围时触发借机攻击 [#4]。`,
    sources: [1, 2, 3, 4].map((n) => ({
      book: `核心规则书 ${n}`,
      bookNameCn: `核心规则书 ${n}`,
      bookAbbreviation: `CRB${n}`,
      tocPath: `战斗章节 / 第 ${n} 节`,
      content: `这是第 ${n} 条来源原文，用于核对规则引用。`,
      chunkId: `chunk-${n}`,
    })),
    gapReported: false,
  }
}

function summary(conversation: StubConversation) {
  return {
    id: conversation.id,
    title: conversation.title,
    pinned: conversation.pinned,
    createdAt: conversation.createdAt,
    updatedAt: conversation.updatedAt,
    messageRounds: conversation.messageRounds,
  }
}

function detail(conversation: StubConversation) {
  return { ...summary(conversation), messages: conversation.messages }
}

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function noContent(route: Route): Promise<void> {
  return route.fulfill({ status: 204, body: '' })
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function installStubApi(page: Page, options: StubOptions = {}): Promise<StubState> {
  const state: StubState = { conversations: new Map(), username: null, counter: 0 }

  function visibleConversations(): StubConversation[] {
    const all = [...state.conversations.values()].filter((c) => !c.deleted && c.messageRounds > 0)
    const scoped = state.username
      ? all.filter((c) => c.owner === state.username)
      : all.filter((c) => c.owner === null)
    return scoped.sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return b.updatedAt.localeCompare(a.updatedAt)
    })
  }

  function canAccess(conversation: StubConversation): 'ok' | 'forbidden' | 'notfound' {
    if (conversation.deleted) return 'notfound'
    if (conversation.owner === null) return state.username ? 'forbidden' : 'ok'
    return state.username === conversation.owner ? 'ok' : 'notfound'
  }

  function newConversation(): StubConversation {
    state.counter += 1
    const now = new Date().toISOString()
    const conversation: StubConversation = {
      id: `conv-${state.counter}`,
      title: null,
      pinned: false,
      createdAt: now,
      updatedAt: now,
      messageRounds: 0,
      messages: [],
      owner: state.username,
      deleted: false,
    }
    state.conversations.set(conversation.id, conversation)
    return conversation
  }

  function appendRound(conversation: StubConversation, question: string) {
    const now = new Date().toISOString()
    const nextSeq = conversation.messages.reduce((max, message) => Math.max(max, message.seq), 0) + 1
    conversation.messages.push({
      id: nextSeq,
      seq: nextSeq,
      role: 'user',
      content: question,
      sources: null,
      gapReported: false,
      createdAt: now,
      completedAt: null,
    })
    const payload = (options.answer ?? defaultAnswer)(question)
    conversation.messages.push({
      id: nextSeq + 1,
      seq: nextSeq + 1,
      role: 'assistant',
      content: payload.answer,
      sources: payload.sources,
      gapReported: Boolean(payload.gapReported),
      createdAt: now,
      completedAt: now,
    })
    conversation.messageRounds += 1
    if (!conversation.title) conversation.title = question.slice(0, 26)
    conversation.updatedAt = now
    return {
      answer: payload.answer,
      sources: payload.sources,
      gapReported: Boolean(payload.gapReported),
      conversationId: conversation.id,
      messageId: nextSeq + 1,
      messageSeq: nextSeq + 1,
      completedAt: now,
    }
  }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const authHeader = request.headers()['authorization'] ?? ''
    let body: any = null
    if (method !== 'GET' && method !== 'DELETE') {
      try {
        body = request.postDataJSON()
      } catch {
        body = null
      }
    }

    if (path === '/api/auth/status') {
      return json(route, 200, { enabled: true, registrationEnabled: true, memoryMode: false })
    }
    if (path === '/api/auth/me') {
      if (!state.username || authHeader !== `Bearer ${TOKEN}`) return json(route, 401, { error: 'unauthorized' })
      return json(route, 200, { uid: 1, username: state.username, nickname: state.username })
    }
    if (path === '/api/auth/login' || path === '/api/auth/register') {
      if (method === 'POST') {
        if (path === '/api/auth/register' && body?.username === 'taken') {
          return json(route, 409, { error: 'username_taken' })
        }
        state.username = String(body?.username ?? 'tester')
        return json(route, 200, { token: TOKEN, uid: 1, username: state.username, nickname: state.username })
      }
    }
    if (path === '/api/admin/settings') {
      if (state.username === 'admin') return json(route, 200, { registrationEnabled: true })
      return json(route, 403, { error: 'forbidden' })
    }

    if (path === '/api/conversations' && method === 'POST') {
      return json(route, 200, summary(newConversation()))
    }
    if (path === '/api/conversations' && method === 'GET') {
      if (!state.username) return json(route, 401, { error: 'unauthorized' })
      return json(route, 200, { items: visibleConversations().map(summary), nextCursor: null })
    }
    if (path === '/api/conversations/lookup' && method === 'POST') {
      const ids: string[] = Array.isArray(body?.ids) ? body.ids : []
      const items = ids
        .map((id) => state.conversations.get(id))
        .filter((c): c is StubConversation => Boolean(c) && c!.owner === null && c!.messageRounds > 0 && !c!.deleted)
        .map(summary)
      return json(route, 200, { items })
    }
    if (path === '/api/conversations/claim' && method === 'POST') {
      if (!state.username) return json(route, 401, { error: 'unauthorized' })
      const ids: string[] = Array.isArray(body?.conversationIds) ? body.conversationIds : []
      const claimed: string[] = []
      const alreadyOwned: string[] = []
      const rejected: string[] = []
      for (const id of ids) {
        const conversation = state.conversations.get(id)
        if (!conversation || conversation.deleted) {
          rejected.push(id)
        } else if (conversation.owner === null) {
          conversation.owner = state.username
          claimed.push(id)
        } else if (conversation.owner === state.username) {
          alreadyOwned.push(id)
        } else {
          rejected.push(id)
        }
      }
      return json(route, 200, { claimed, alreadyOwned, rejected })
    }

    const conversationMatch = /^\/api\/conversations\/([^/]+)(\/regenerate)?$/.exec(path)
    if (conversationMatch) {
      const id = decodeURIComponent(conversationMatch[1])
      const isRegenerate = Boolean(conversationMatch[2])
      const conversation = state.conversations.get(id)
      if (!conversation || conversation.deleted) {
        return json(route, isRegenerate || method !== 'GET' ? 410 : 404, {
          error: isRegenerate || method !== 'GET' ? 'conversation_deleted' : 'conversation_not_found',
        })
      }
      const access = canAccess(conversation)
      if (access === 'forbidden') return json(route, 403, { error: 'forbidden' })
      if (access === 'notfound') return json(route, 404, { error: 'conversation_not_found' })

      if (method === 'GET') return json(route, 200, detail(conversation))
      if (method === 'PATCH') {
        if (typeof body?.title === 'string') conversation.title = body.title
        if (typeof body?.pinned === 'boolean') conversation.pinned = body.pinned
        return json(route, 200, summary(conversation))
      }
      if (method === 'DELETE') {
        conversation.deleted = true
        return noContent(route)
      }
      if (isRegenerate && method === 'POST') {
        if (options.delayMs) await delay(options.delayMs)
        const last = conversation.messages[conversation.messages.length - 1]
        if (!last || last.role !== 'assistant') return json(route, 409, { error: 'conversation_changed' })
        if (body?.expectedLastSeq !== last.seq) return json(route, 409, { error: 'conversation_changed' })
        const payload = (options.answer ?? defaultAnswer)('重新生成')
        last.content = payload.answer
        last.sources = payload.sources
        last.gapReported = Boolean(payload.gapReported)
        last.completedAt = new Date().toISOString()
        conversation.updatedAt = last.completedAt
        return json(route, 200, {
          answer: payload.answer,
          sources: payload.sources,
          gapReported: Boolean(payload.gapReported),
          conversationId: conversation.id,
          messageId: last.id,
          messageSeq: last.seq,
          completedAt: last.completedAt,
        })
      }
    }

    if (path === '/api/chat' && method === 'POST') {
      if (options.delayMs) await delay(options.delayMs)
      if (options.throttle === 'quota') {
        return json(route, 429, { error: 'quota_exceeded', message: '本会话免费额度已用完' })
      }
      if (options.throttle === 'rate') {
        return json(route, 429, { error: 'rate_limited', message: '请求过于频繁，请稍后再试' })
      }
      const conversation = state.conversations.get(String(body?.conversationId))
      if (!conversation || conversation.deleted) {
        return json(route, 410, { error: 'conversation_deleted' })
      }
      const access = canAccess(conversation)
      if (access === 'forbidden') return json(route, 403, { error: 'forbidden' })
      if (access === 'notfound') return json(route, 404, { error: 'conversation_not_found' })
      return json(route, 200, appendRound(conversation, String(body?.question ?? '')))
    }

    if (path === '/api/chat/feedback' && method === 'POST') {
      return json(route, 200, { ok: true, id: 1 })
    }

    return route.fulfill({ status: 404, body: 'not found' })
  })

  return state
}
