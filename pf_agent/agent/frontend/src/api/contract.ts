export type Role = 'user' | 'assistant'

export interface Source {
  /** 兼容展示名：中文书名与缩写合并（如“核心规则书 (CRB)”）；旧快照只有此字段 */
  book: string
  /** 结构化中文书名（F-020 新增）；官方/未知来源可能为空，旧快照缺省 */
  bookNameCn?: string | null
  /** 结构化书名缩写（F-020 新增）；官方/未知来源可能为空，旧快照缺省 */
  bookAbbreviation?: string | null
  /** 展示标题兜底（F-002/KN-204/KN-219）：后端已去尾冒号并截断；旧快照缺省时前端回退 tocPath 末段 */
  title?: string | null
  tocPath: string
  content: string
  chunkId?: string | null
}

export interface Message {
  id: number | string
  seq: number
  role: Role
  content: string
  sources: Source[] | null
  gapReported: boolean
  createdAt: string
  completedAt?: string | null
}

export interface ConversationSummary {
  id: string
  title: string | null
  pinned: boolean
  createdAt: string
  updatedAt: string
  messageRounds: number
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[]
}

export interface ConversationPage {
  items: ConversationSummary[]
  nextCursor: string | null
}

export interface ClaimResult {
  claimed: string[]
  alreadyOwned: string[]
  rejected: string[]
}

export interface ChatAnswer {
  answer: string
  sources: Source[]
  gapReported: boolean
  conversationId: string
  messageId?: number | string
  messageSeq?: number
  completedAt?: string
}

export interface AuthUser {
  uid: number
  username: string
  nickname: string
}

export interface AuthResult {
  token: string
  uid: number
  username: string
  nickname: string
}

export interface AuthStatus {
  enabled: boolean
  registrationEnabled: boolean
  /** 可选：后端可选地暴露内存模式（重启清空历史）。缺省按 false 处理。 */
  memoryMode?: boolean
}

export interface FeedbackPayload {
  conversationId: string
  question: string
  answer: string
  sources: Source[]
  errorType: string
  correction?: string | null
  comment?: string | null
}

export type ConversationPatch = Partial<Pick<ConversationSummary, 'title' | 'pinned'>>
