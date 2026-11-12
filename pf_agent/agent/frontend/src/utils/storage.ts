const TOKEN_KEY = 'pf.auth.token'
const ANON_IDS_KEY = 'pf.anon.conversationIds'
const LAST_ID_KEY = 'pf.last.conversationId'

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeRaw(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    // 隐私模式/配额满时忽略：功能退化为本页内存态
  }
}

export const storage = {
  getToken(): string {
    return readRaw(TOKEN_KEY) ?? ''
  },
  setToken(token: string | null): void {
    writeRaw(TOKEN_KEY, token)
  },
  getAnonymousIds(): string[] {
    const raw = readRaw(ANON_IDS_KEY)
    if (!raw) return []
    try {
      const parsed: unknown = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []
    } catch {
      return []
    }
  },
  setAnonymousIds(ids: string[]): void {
    writeRaw(ANON_IDS_KEY, JSON.stringify(ids))
  },
  addAnonymousId(id: string): string[] {
    const next = [id, ...storage.getAnonymousIds().filter((v) => v !== id)].slice(0, 200)
    storage.setAnonymousIds(next)
    return next
  },
  removeAnonymousIds(ids: string[]): string[] {
    const remove = new Set(ids)
    const next = storage.getAnonymousIds().filter((v) => !remove.has(v))
    storage.setAnonymousIds(next)
    return next
  },
  getLastConversationId(): string {
    return readRaw(LAST_ID_KEY) ?? ''
  },
  setLastConversationId(id: string | null): void {
    writeRaw(LAST_ID_KEY, id)
  },
  clearAccount(): void {
    storage.setToken(null)
    writeRaw(LAST_ID_KEY, null)
  },
}
