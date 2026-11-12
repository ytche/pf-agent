import { storage } from '@/utils/storage'
import type {
  AuthResult,
  AuthStatus,
  AuthUser,
  ChatAnswer,
  ClaimResult,
  ConversationDetail,
  ConversationPage,
  ConversationPatch,
  ConversationSummary,
  FeedbackPayload,
  Source,
} from './contract'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
  signal?: AbortSignal
}

async function parseError(response: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `请求失败（${response.status}）`
  try {
    const data: unknown = await response.json()
    if (data && typeof data === 'object') {
      const body = data as { error?: unknown; message?: unknown }
      if (typeof body.error === 'string' && body.error) code = body.error
      if (typeof body.message === 'string' && body.message) message = body.message
    }
  } catch {
    // 非 JSON 错误体：保留按状态码生成的文案
  }
  return new ApiError(response.status, code, message)
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.auth !== false) {
    const token = storage.getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', '网络异常，请稍后重试')
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function pageQuery(cursor: string | null, limit: number): string {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return `?${params.toString()}`
}

export const api = {
  authStatus(): Promise<AuthStatus> {
    return request<AuthStatus>('/api/auth/status', { auth: false })
  },
  login(username: string, password: string): Promise<AuthResult> {
    return request<AuthResult>('/api/auth/login', {
      method: 'POST',
      auth: false,
      body: { username, password },
    })
  },
  register(username: string, password: string): Promise<AuthResult> {
    return request<AuthResult>('/api/auth/register', {
      method: 'POST',
      auth: false,
      body: { username, password },
    })
  },
  me(): Promise<AuthUser> {
    return request<AuthUser>('/api/auth/me')
  },
  /** 管理员探测：200 = admin，401/403 由调用方按非管理员处理 */
  adminSettings(): Promise<unknown> {
    return request<unknown>('/api/admin/settings')
  },

  createConversation(): Promise<ConversationSummary> {
    return request<ConversationSummary>('/api/conversations', { method: 'POST' })
  },
  listConversations(cursor: string | null = null, limit = 30): Promise<ConversationPage> {
    return request<ConversationPage>(`/api/conversations${pageQuery(cursor, limit)}`)
  },
  lookupConversations(ids: string[]): Promise<{ items: ConversationSummary[] }> {
    return request<{ items: ConversationSummary[] }>('/api/conversations/lookup', {
      method: 'POST',
      body: { ids },
    })
  },
  getConversation(id: string): Promise<ConversationDetail> {
    return request<ConversationDetail>(`/api/conversations/${encodeURIComponent(id)}`)
  },
  patchConversation(id: string, patch: ConversationPatch): Promise<ConversationSummary> {
    return request<ConversationSummary>(`/api/conversations/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: patch,
    })
  },
  deleteConversation(id: string): Promise<void> {
    return request<void>(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },
  claimConversations(conversationIds: string[]): Promise<ClaimResult> {
    return request<ClaimResult>('/api/conversations/claim', {
      method: 'POST',
      body: { conversationIds },
    })
  },
  regenerate(id: string, expectedLastSeq: number): Promise<ChatAnswer> {
    return request<ChatAnswer>(`/api/conversations/${encodeURIComponent(id)}/regenerate`, {
      method: 'POST',
      body: { expectedLastSeq },
    })
  },

  chat(question: string, conversationId: string): Promise<ChatAnswer> {
    return request<ChatAnswer>('/api/chat', {
      method: 'POST',
      body: { question, conversationId },
    })
  },
  feedback(payload: FeedbackPayload): Promise<{ ok: boolean; id?: number; reason?: string }> {
    return request<{ ok: boolean; id?: number; reason?: string }>('/api/chat/feedback', {
      method: 'POST',
      body: payload,
    })
  },
}

export type { Source }
