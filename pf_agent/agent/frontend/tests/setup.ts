import { beforeEach, vi } from 'vitest'

class MemoryStorage implements Storage {
  private data = new Map<string, string>()

  get length(): number {
    return this.data.size
  }

  clear(): void {
    this.data.clear()
  }

  getItem(key: string): string | null {
    return this.data.has(key) ? this.data.get(key)! : null
  }

  key(index: number): string | null {
    return Array.from(this.data.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.data.delete(key)
  }

  setItem(key: string, value: string): void {
    this.data.set(key, String(value))
  }
}

beforeEach(() => {
  vi.unstubAllGlobals()
  // 部分宿主通过 --localstorage-file 注入 Node 原生 localStorage，会遮蔽 jsdom 实现
  // （缺少 clear 等方法），这里统一替换为内存实现。
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: new MemoryStorage(),
  })
  window.localStorage.clear()
  window.history.replaceState(null, '', '/')
})
