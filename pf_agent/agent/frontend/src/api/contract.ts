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
  /** 无合法逐句引用时保留请求级检索证据；缺省为 false */
  citationDegraded?: boolean
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

/** 用量汇总（F-009 /api/usage/summary）：token 与 cost 为 null 表示无可用数据，不是 0 */
export interface UsageTotals {
  calls: number
  promptTokens: number | null
  completionTokens: number | null
  totalTokens: number | null
  cost: number | null
  currency: string | null
  missingUsageCount: number
}

export interface UsageGroup {
  key: string
  label: string
  calls: number
  promptTokens: number | null
  completionTokens: number | null
  totalTokens: number | null
  cost: number | null
  missingUsageCount: number
}

export interface UsageForecast {
  timezone: string
  monthToDateCost: number | null
  dailyAverageCost: number | null
  /** 日均分母：min(7, 本月已过天数)，无成本日按 0 计入 */
  windowDays: number
  /** 窗口内实际有成本数据的天数（仅供展示） */
  dataDays: number
  remainingDays: number
  predictedMonthCost: number | null
  formula: string
}

export type UsageScope = 'global' | 'owner' | 'conversation'
export type UsageRange = 'today' | 'month' | 'all'
export type UsageGroupBy = 'day' | 'conversation' | 'owner'

export interface UsageSummary {
  range: UsageRange
  groupBy: UsageGroupBy
  scope: UsageScope
  timezone: string
  formula: string
  from: string | null
  to: string
  totals: UsageTotals
  groups: UsageGroup[]
  forecast: UsageForecast
}

export interface UsageQuery {
  range?: UsageRange
  groupBy?: UsageGroupBy
  conversationId?: string | null
}
