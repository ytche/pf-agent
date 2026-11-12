import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useConversationsStore } from '@/stores/conversations'
import { storage } from '@/utils/storage'
import type { ConversationDetail, ConversationSummary, Message } from '@/api/contract'
import { empty, installFetch, json, type MockRequest } from './helpers/mock-api'

const BASE = '2026-11-11T01:00:00Z'

function summary(id: string, over: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id,
    title: `会话 ${id}`,
    pinned: false,
    createdAt: BASE,
    updatedAt: BASE,
    messageRounds: 1,
    ...over,
  }
}

function userMessage(id: string, seq: number, content: string): Message {
  return {
    id,
    seq,
    role: 'user',
    content,
    sources: null,
    gapReported: false,
    createdAt: BASE,
  }
}

function assistantMessage(id: string, seq: number, content: string): Message {
  return {
    id,
    seq,
    role: 'assistant',
    content,
    sources: [{ book: '核心规则书', tocPath: '第一章', content: '原文' }],
    gapReported: false,
    createdAt: BASE,
    completedAt: BASE,
  }
}

function detail(id: string, messages: Message[] = [userMessage('m1', 1, '问题'), assistantMessage('m2', 2, '回答')]): ConversationDetail {
  return { ...summary(id, { messageRounds: Math.ceil(messages.length / 2) }), messages }
}

function loginAs(username = 'tester'): void {
  const auth = useAuthStore()
  auth.user = { uid: 1, username, nickname: username }
}

let pinia: Pinia

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})

describe('conversations store：匿名恢复与分页', () => {
  it('匿名启动按本机 ID lookup 并恢复会话', async () => {
    storage.setAnonymousIds(['c1'])
    installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: false, registrationEnabled: false })
      if (request.path === '/api/conversations/lookup') return json(200, { items: [summary('c1')] })
      if (request.path === '/api/conversations/c1') return json(200, detail('c1'))
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    const conversations = useConversationsStore()
    await auth.bootstrap()
    await conversations.bootstrap()

    expect(conversations.currentId).toBe('c1')
    expect(conversations.history.map((item) => item.summary.id)).toEqual(['c1'])
    expect(conversations.current?.messages).toHaveLength(2)
    expect(window.location.hash).toBe('#/c/c1')
  })

  it('登录用户分批加载并在加载更多时追加', async () => {
    loginAs()
    installFetch((request) => {
      if (request.path === '/api/conversations') {
        if (request.query.get('cursor') === 'cursor-2') {
          return json(200, { items: [summary('c', { updatedAt: '2026-11-11T00:00:00Z' })], nextCursor: null })
        }
        return json(200, {
          items: [
            summary('a', { updatedAt: '2026-11-11T03:00:00Z' }),
            summary('b', { updatedAt: '2026-11-11T02:00:00Z' }),
          ],
          nextCursor: 'cursor-2',
        })
      }
      if (request.path === '/api/conversations/a') {
        return json(200, { ...detail('a'), updatedAt: '2026-11-11T03:00:00Z' })
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.bootstrap()
    expect(conversations.currentId).toBe('a')
    expect(conversations.history.map((item) => item.summary.id)).toEqual(['a', 'b'])

    await conversations.loadMore()
    expect(conversations.history.map((item) => item.summary.id)).toEqual(['a', 'b', 'c'])
    expect(conversations.nextCursor).toBeNull()
  })

  it('历史首次加载失败后 reloadList 会真正重新请求（不依赖 nextCursor）', async () => {
    loginAs()
    let listCalls = 0
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'GET') {
        listCalls += 1
        if (listCalls === 1) return json(500, { error: 'server_error', message: '历史读取失败' })
        return json(200, { items: [summary('a')], nextCursor: null })
      }
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('blank', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/conversations/a') return json(200, detail('a'))
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.bootstrap()
    expect(conversations.listError).toBeTruthy()
    expect(conversations.nextCursor).toBeNull()

    await conversations.reloadList()
    expect(listCalls).toBe(2)
    expect(conversations.listError).toBeNull()
    expect(conversations.history.map((item) => item.summary.id)).toEqual(['a'])
  })
})

describe('conversations store：问答与后台状态', () => {
  it('成功问答写入轮次、标题与匿名 ID', async () => {
    let created = 0
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        created += 1
        return json(200, summary(`c${created}`, { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        return json(200, {
          answer: '借机攻击在敌人离开威胁范围时触发 [#1]',
          sources: [{ book: '核心规则书', tocPath: '战斗', content: '原文' }],
          gapReported: false,
          conversationId: 'c1',
          messageId: 2,
          messageSeq: 2,
          completedAt: BASE,
        })
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('借机攻击什么时候触发？')

    const runtime = conversations.conversations['c1']
    expect(runtime.messages).toHaveLength(2)
    expect(runtime.messages[1].content).toContain('借机攻击')
    expect(runtime.summary.messageRounds).toBe(1)
    expect(runtime.summary.title).toBe('借机攻击什么时候触发？')
    expect(conversations.history.map((item) => item.summary.id)).toContain('c1')
    expect(conversations.anonymousIds).toContain('c1')
    expect(storage.getAnonymousIds()).toContain('c1')
  })

  it('切换会话后后台完成标记未读，打开后清除', async () => {
    loginAs()
    let created = 0
    let resolveChat!: (response: Response) => void
    const chatResponse = new Promise<Response>((resolve) => {
      resolveChat = resolve
    })
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        created += 1
        return json(200, summary(`c${created}`, { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        return chatResponse
      }
      if (request.path === '/api/conversations/c1') {
        return json(200, detail('c1', [userMessage('u1', 1, '后台问题'), assistantMessage('a1', 2, '后台回答')]))
      }
      if (request.path === '/api/conversations/c2') return json(200, detail('c2', []))
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    const sending = conversations.send('后台问题')
    await vi.waitFor(() => expect(conversations.conversations['c1'].pending).toBe(true))
    await conversations.createConversation(true)
    expect(conversations.currentId).toBe('c2')

    resolveChat(
      json(200, {
        answer: '后台回答',
        sources: [],
        gapReported: false,
        conversationId: 'c1',
        messageId: 2,
        messageSeq: 2,
        completedAt: BASE,
      }),
    )
    await sending

    expect(conversations.conversations['c1'].pending).toBe(false)
    expect(conversations.conversations['c1'].unread).toBe(true)
    expect(conversations.conversations['c1'].messages.slice(-1)[0].content).toBe('后台回答')

    await conversations.open('c1')
    expect(conversations.conversations['c1'].unread).toBe(false)
  })

  it('同会话禁止并发发送，不同会话可以并行', async () => {
    loginAs()
    let created = 0
    const resolvers: Array<(response: Response) => void> = []
    const chatBodies: string[] = []
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        created += 1
        return json(200, summary(`c${created}`, { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        chatBodies.push(request.body.conversationId)
        return new Promise<Response>((resolve) => resolvers.push(resolve))
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    const first = conversations.send('问题一')
    void conversations.send('重复问题')
    expect(chatBodies).toHaveLength(1)

    await conversations.createConversation(true)
    const second = conversations.send('另一个会话的问题')
    expect(chatBodies).toEqual(['c1', 'c2'])

    resolvers[0](json(200, { answer: '回答一', sources: [], gapReported: false, conversationId: 'c1', messageSeq: 2 }))
    resolvers[1](json(200, { answer: '回答二', sources: [], gapReported: false, conversationId: 'c2', messageSeq: 2 }))
    await Promise.all([first, second])
    expect(conversations.conversations['c1'].pending).toBe(false)
    expect(conversations.conversations['c2'].pending).toBe(false)
  })

  it('401 保留当前问题并打开登录弹层，不写成 AI 消息', async () => {
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('c1', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') return json(401, { error: 'unauthorized' })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('需要登录的问题')

    const runtime = conversations.conversations['c1']
    expect(runtime.turnError?.kind).toBe('auth')
    expect(runtime.messages.map((message) => message.role)).toEqual(['user'])
    expect(runtime.pending).toBe(false)
    expect(auth.dialogOpen).toBe(true)
  })

  it('401 清除失效 token，登录后恢复未落库问题并可重试成功', async () => {
    storage.setToken('expired-token')
    let chatCalls = 0
    const fetchMock = installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('c1', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        chatCalls += 1
        if (chatCalls === 1) return json(401, { error: 'unauthorized' })
        return json(200, {
          answer: '登录后的回答 [#1]',
          sources: [{ book: '核心规则书', tocPath: '战斗', content: '原文' }],
          gapReported: false,
          conversationId: 'c1',
          messageId: 2,
          messageSeq: 2,
          completedAt: BASE,
        })
      }
      if (request.path === '/api/conversations/claim') {
        return json(200, { claimed: ['c1'], alreadyOwned: [], rejected: [] })
      }
      if (request.path === '/api/conversations') {
        return json(200, { items: [], nextCursor: null })
      }
      if (request.path === '/api/conversations/c1') return json(200, detail('c1', []))
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    auth.token = 'expired-token'
    auth.user = { uid: 1, username: 'tester', nickname: 'tester' }
    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('登录后才可继续的问题')

    expect(auth.token).toBe('')
    expect(storage.getToken()).toBe('')
    expect(auth.isLoggedIn).toBe(false)
    const authError = conversations.current?.turnError
    expect(authError?.kind).toBe('auth')
    expect(authError?.anonymousRetry).toBe(false)
    expect(authError?.message).not.toContain('匿名')
    const firstChat = fetchMock.mock.calls.find(([input]) => String(input).includes('/api/chat'))
    expect(firstChat?.[1]?.headers).toMatchObject({ Authorization: 'Bearer expired-token' })

    storage.setToken('valid-token')
    auth.user = { uid: 1, username: 'tester', nickname: 'tester' }
    await conversations.onLoggedIn()

    expect(conversations.currentId).toBe('c1')
    expect(conversations.current?.messages.map((message) => message.role)).toEqual(['user'])
    expect(conversations.current?.messages[0].content).toBe('登录后才可继续的问题')
    expect(conversations.current?.turnError?.kind).toBe('recovered')
    expect(conversations.current?.turnError?.retryable).toBe(true)

    await conversations.retry()
    expect(chatCalls).toBe(2)
    expect(conversations.current?.turnError).toBeNull()
    expect(conversations.current?.messages.map((message) => message.role)).toEqual(['user', 'assistant'])
    expect(conversations.current?.messages[1].content).toBe('登录后的回答 [#1]')
    const lastChat = fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/chat')).at(-1)
    expect(lastChat?.[1]?.headers).toMatchObject({ Authorization: 'Bearer valid-token' })
  })

  it('登录恢复同文本问题时按 seq 追加，不误判为已落库', async () => {
    loginAs()
    const messages: Message[] = [
      userMessage('u1', 1, '同一问题文本'),
      assistantMessage('a1', 2, '第一次回答'),
    ]
    installFetch((request) => {
      if (request.path === '/api/conversations') {
        return json(200, { items: [summary('c1')], nextCursor: null })
      }
      if (request.path === '/api/conversations/c1') return json(200, detail('c1', messages))
      if (request.path === '/api/conversations/claim') {
        return json(200, { claimed: [], alreadyOwned: [], rejected: [] })
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    conversations.interruptedTurn = { conversationId: 'c1', question: '同一问题文本', seq: 3 }
    await conversations.onLoggedIn()

    const userBubbles = conversations.current?.messages.filter((message) => message.role === 'user')
    expect(userBubbles).toHaveLength(2)
    expect(userBubbles?.[1].seq).toBe(3)
    expect(conversations.current?.turnError?.kind).toBe('recovered')
  })

  it('取消登录后仍可用无 token 的匿名语义重试', async () => {
    storage.setToken('expired-token')
    let chatCalls = 0
    const fetchMock = installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('c1', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        chatCalls += 1
        if (chatCalls === 1) return json(401, { error: 'unauthorized' })
        return json(200, {
          answer: '匿名重试成功',
          sources: [],
          gapReported: false,
          conversationId: 'c1',
          messageId: 2,
          messageSeq: 2,
        })
      }
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    auth.token = 'expired-token'
    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('匿名重试问题')
    auth.closeDialog()

    expect(auth.token).toBe('')
    expect(conversations.current?.turnError?.anonymousRetry).toBe(true)
    await conversations.retry()

    expect(chatCalls).toBe(2)
    const lastChat = fetchMock.mock.calls.filter(([input]) => String(input).includes('/api/chat')).at(-1)
    expect((lastChat?.[1]?.headers as Record<string, string> | undefined)?.Authorization).toBeUndefined()
    expect(conversations.current?.messages.map((message) => message.role)).toEqual(['user', 'assistant'])
  })

  it('429 区分配额与普通限频', async () => {
    let mode: 'quota' | 'rate' = 'quota'
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('c1', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') {
        return mode === 'quota'
          ? json(429, { error: 'quota_exceeded', message: '本会话免费额度已用完' })
          : json(429, { error: 'rate_limited', message: '请求过于频繁' })
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('配额问题')
    const quotaRuntime = conversations.conversations['c1']
    expect(quotaRuntime.turnError?.kind).toBe('quota')
    expect(quotaRuntime.turnError?.retryable).toBe(false)

    mode = 'rate'
    conversations.conversations['c1'].turnError = null
    await conversations.send('限频问题')
    const rateRuntime = conversations.conversations['c1']
    expect(rateRuntime.turnError?.kind).toBe('rate')
    expect(rateRuntime.turnError?.retryable).toBe(true)
  })

  it('410 丢弃晚到结果、清理请求状态且不留在历史', async () => {
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('c1', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') return json(410, { error: 'conversation_deleted' })
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    await conversations.send('会被删除的问题')

    expect(conversations.conversations['c1']).toBeUndefined()
    expect(conversations.currentId).toBeNull()
    expect(conversations.history).toHaveLength(0)
  })

  it('删除进行中的会话后晚到成功结果不复活', async () => {
    let created = 0
    let resolveChat!: (response: Response) => void
    const chatResponse = new Promise<Response>((resolve) => {
      resolveChat = resolve
    })
    installFetch((request) => {
      if (request.path === '/api/conversations' && request.method === 'POST') {
        created += 1
        return json(200, summary(`c${created}`, { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/chat') return chatResponse
      if (request.path === '/api/conversations/c1' && request.method === 'DELETE') return empty(204)
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.createConversation(true)
    const sending = conversations.send('将被删除的问题')
    await vi.waitFor(() => expect(conversations.conversations['c1'].pending).toBe(true))

    await conversations.remove('c1')
    expect(conversations.currentId).toBe('c2')

    resolveChat(
      json(200, {
        answer: '晚到的回答',
        sources: [],
        gapReported: false,
        conversationId: 'c1',
        messageId: 2,
        messageSeq: 2,
      }),
    )
    await sending

    expect(conversations.conversations['c1']).toBeUndefined()
    expect(conversations.history.map((item) => item.summary.id)).not.toContain('c1')
    expect(conversations.current?.pending).toBe(false)
  })

  it('历史消息保留自己的 ID、完成时间与来源快照', async () => {
    const messages: Message[] = [
      userMessage('u1', 1, '问题一'),
      { ...assistantMessage('a1', 2, '回答一'), sources: [{ book: '书一', tocPath: '一', content: '一' }] },
      userMessage('u2', 3, '问题二'),
      {
        ...assistantMessage('a2', 4, '回答二'),
        sources: [{ book: '书二', tocPath: '二', content: '二' }],
        completedAt: '2026-11-11T02:00:00Z',
      },
    ]
    installFetch((request) => {
      if (request.path === '/api/conversations/c1') return json(200, detail('c1', messages))
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.open('c1')
    const loaded = conversations.current!.messages
    expect(loaded[1].id).toBe('a1')
    expect(loaded[3].id).toBe('a2')
    expect(loaded[1].completedAt).not.toBe(loaded[3].completedAt)
    expect(loaded[1].sources?.[0].book).toBe('书一')
    expect(loaded[3].sources?.[0].book).toBe('书二')
  })

  it('历史读取 404 显示可重试错误而不是空历史', async () => {
    installFetch((request) => {
      if (request.method === 'POST' && request.path === '/api/conversations') {
        return json(200, summary('fresh', { title: null, messageRounds: 0 }))
      }
      if (request.path === '/api/conversations/missing') return json(404, { error: 'conversation_not_found' })
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.open('missing')
    expect(conversations.currentId).toBeNull()
    expect(conversations.conversations['missing']).toBeUndefined()
  })
})

describe('conversations store：重新生成、删除与认领', () => {
  it('重新生成 409 保留旧回答', async () => {
    installFetch((request) => {
      if (request.path === '/api/conversations/c1') return json(200, detail('c1'))
      if (request.path === '/api/conversations/c1/regenerate') return json(409, { error: 'conversation_changed' })
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.open('c1')
    const before = conversations.current?.messages[1].content
    await conversations.regenerate()

    expect(conversations.current?.messages[1].content).toBe(before)
    expect(conversations.current?.messages[1].id).toBe('m2')
    expect(conversations.current?.turnError?.kind).toBe('changed')
  })

  it('重新生成成功只替换最后一条助手消息且 ID 不变', async () => {
    installFetch((request) => {
      if (request.path === '/api/conversations/c1') return json(200, detail('c1'))
      if (request.path === '/api/conversations/c1/regenerate') {
        return json(200, {
          answer: '新的回答',
          sources: [],
          gapReported: true,
          conversationId: 'c1',
          messageId: 'm2',
          messageSeq: 2,
          completedAt: BASE,
        })
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.open('c1')
    await conversations.regenerate()
    expect(conversations.current?.messages).toHaveLength(2)
    expect(conversations.current?.messages[1].content).toBe('新的回答')
    expect(conversations.current?.messages[1].id).toBe('m2')
    expect(conversations.current?.messages[1].gapReported).toBe(true)
  })

  it('删除当前会话后进入新的空白会话', async () => {
    installFetch((request) => {
      if (request.path === '/api/conversations/c1' && request.method === 'GET') return json(200, detail('c1'))
      if (request.path === '/api/conversations/c1' && request.method === 'DELETE') return empty(204)
      if (request.path === '/api/conversations' && request.method === 'POST') {
        return json(200, summary('blank', { title: null, messageRounds: 0 }))
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.open('c1')
    await conversations.remove('c1')
    expect(conversations.conversations['c1']).toBeUndefined()
    expect(conversations.currentId).toBe('blank')
    expect(conversations.history).toHaveLength(0)
  })

  it('登录认领后移除已归属的匿名 ID 并刷新账号历史', async () => {
    loginAs()
    storage.setAnonymousIds(['a', 'b'])
    installFetch((request) => {
      if (request.path === '/api/conversations/claim') {
        return json(200, { claimed: ['a'], alreadyOwned: [], rejected: ['b'] })
      }
      if (request.path === '/api/conversations') return json(200, { items: [summary('a')], nextCursor: null })
      if (request.path === '/api/conversations/a') return json(200, detail('a'))
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.onLoggedIn()

    expect(storage.getAnonymousIds()).not.toContain('a')
    expect(storage.getAnonymousIds()).toContain('b')
    expect(conversations.claimNotice).toContain('1 个匿名会话')
    expect(conversations.claimNotice).toContain('1 个会话无法认领')
    expect(conversations.currentId).toBe('a')
  })

  it('置顶后排在历史最前', async () => {
    loginAs()
    installFetch((request: MockRequest) => {
      if (request.path === '/api/conversations') {
        return json(200, {
          items: [
            summary('a', { updatedAt: '2026-11-11T03:00:00Z' }),
            summary('b', { updatedAt: '2026-11-11T02:00:00Z' }),
          ],
          nextCursor: null,
        })
      }
      if (request.path === '/api/conversations/a') return json(200, detail('a'))
      if (request.path === '/api/conversations/b' && request.method === 'PATCH') {
        return json(200, summary('b', { pinned: true, updatedAt: '2026-11-11T02:00:00Z' }))
      }
      return json(404, { error: 'not_found' })
    })

    const conversations = useConversationsStore()
    await conversations.bootstrap()
    await conversations.togglePin('b')
    expect(conversations.history.map((item) => item.summary.id)).toEqual(['b', 'a'])
  })
})
