import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { storage } from '@/utils/storage'
import { installFetch, json } from './helpers/mock-api'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('auth store', () => {
  it('登录成功保存 token 并探测管理员入口', async () => {
    installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: true, registrationEnabled: true })
      if (request.path === '/api/auth/login') {
        return json(200, { token: 'jwt-token', uid: 7, username: 'alice', nickname: 'Alice' })
      }
      if (request.path === '/api/admin/settings') return json(200, { registrationEnabled: true })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    await auth.bootstrap()
    const ok = await auth.login('alice', 'password123')

    expect(ok).toBe(true)
    expect(auth.user?.username).toBe('alice')
    expect(auth.displayName).toBe('Alice')
    expect(auth.isAdmin).toBe(true)
    expect(storage.getToken()).toBe('jwt-token')
    expect(auth.dialogOpen).toBe(false)
  })

  it('登录失败显示语义化错误且不保存 token', async () => {
    installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: true, registrationEnabled: true })
      if (request.path === '/api/auth/login') return json(401, { error: 'invalid_credentials' })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    auth.openDialog('login')
    const ok = await auth.login('alice', 'wrong-password')

    expect(ok).toBe(false)
    expect(auth.error).toBe('用户名或密码错误')
    expect(auth.user).toBeNull()
    expect(storage.getToken()).toBe('')
    expect(auth.dialogOpen).toBe(true)
  })

  it('status 返回 memoryMode 时进入临时模式', async () => {
    installFetch((request) => {
      if (request.path === '/api/auth/status') {
        return json(200, { enabled: false, registrationEnabled: false, memoryMode: true })
      }
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    await auth.bootstrap()

    expect(auth.memoryMode).toBe(true)
    expect(auth.enabled).toBe(false)
  })

  it('注册关闭时提示联系管理员', async () => {
    installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: true, registrationEnabled: false })
      if (request.path === '/api/auth/register') return json(403, { error: 'registration_closed' })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    await auth.bootstrap()
    expect(auth.registrationEnabled).toBe(false)
    auth.openDialog('register')
    const ok = await auth.register('bob', 'password123')

    expect(ok).toBe(false)
    expect(auth.error).toContain('未开放注册')
    expect(auth.user).toBeNull()
  })

  it('非法 JWT 在 /me 返回 401 时清除本地登录态，而不是降级匿名请求', async () => {
    storage.setToken('expired-token')
    const fetchMock = installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: true, registrationEnabled: true })
      if (request.path === '/api/auth/me') return json(401, { error: 'unauthorized' })
      if (request.path === '/api/conversations/lookup') return json(200, { items: [] })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    await auth.bootstrap()

    expect(auth.isLoggedIn).toBe(false)
    expect(storage.getToken()).toBe('')
    const meCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/api/auth/me'))
    expect(meCall?.[1]?.headers).toMatchObject({ Authorization: 'Bearer expired-token' })
  })

  it('退出登录清除 token 与最近会话，不保留账号缓存', async () => {
    storage.setToken('jwt-token')
    storage.setLastConversationId('c1')
    installFetch((request) => {
      if (request.path === '/api/auth/status') return json(200, { enabled: true, registrationEnabled: true })
      if (request.path === '/api/auth/me') return json(200, { uid: 1, username: 'alice', nickname: 'Alice' })
      if (request.path === '/api/admin/settings') return json(403, { error: 'forbidden' })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    await auth.bootstrap()
    expect(auth.isLoggedIn).toBe(true)
    expect(auth.isAdmin).toBe(false)

    auth.logout()
    expect(auth.isLoggedIn).toBe(false)
    expect(storage.getToken()).toBe('')
    expect(storage.getLastConversationId()).toBe('')
  })
})
