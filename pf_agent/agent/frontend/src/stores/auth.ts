import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiError } from '@/api/client'
import type { AuthResult, AuthUser } from '@/api/contract'
import { storage } from '@/utils/storage'

export type AuthMode = 'login' | 'register'

const AUTH_ERROR_TEXT: Record<string, string> = {
  username_taken: '该用户名已被注册，换一个试试',
  invalid_credentials: '用户名或密码错误',
  registration_closed: '当前未开放注册，请联系管理员',
  invalid_request: '用户名或密码不符合要求',
  auth_unavailable: '当前运行模式不支持登录',
}

export const useAuthStore = defineStore('auth', () => {
  const enabled = ref(false)
  const registrationEnabled = ref(true)
  const memoryMode = ref(false)
  const token = ref(storage.getToken())
  const user = ref<AuthUser | null>(null)
  const isAdmin = ref(false)
  const dialogOpen = ref(false)
  const mode = ref<AuthMode>('login')
  const busy = ref(false)
  const error = ref('')
  const errorCode = ref('')

  const isLoggedIn = computed(() => user.value !== null)
  const displayName = computed(() => user.value?.nickname || user.value?.username || '')

  function clearLocal(): void {
    token.value = ''
    user.value = null
    isAdmin.value = false
    storage.clearAccount()
  }

  function applyAuth(result: AuthResult): void {
    token.value = result.token
    storage.setToken(result.token)
    user.value = { uid: result.uid, username: result.username, nickname: result.nickname }
  }

  /** 管理员入口探测：/api/admin/settings 200=admin，其余按非管理员 */
  async function probeAdmin(): Promise<void> {
    try {
      await api.adminSettings()
      isAdmin.value = true
    } catch {
      isAdmin.value = false
    }
  }

  async function bootstrap(): Promise<void> {
    try {
      const status = await api.authStatus()
      enabled.value = Boolean(status.enabled)
      registrationEnabled.value = status.registrationEnabled !== false
      memoryMode.value = status.memoryMode === true
    } catch {
      enabled.value = false
    }
    if (!enabled.value || !token.value) return
    try {
      user.value = await api.me()
      await probeAdmin()
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) clearLocal()
    }
  }

  function setError(err: unknown): void {
    if (err instanceof ApiError) {
      errorCode.value = err.code
      error.value = AUTH_ERROR_TEXT[err.code] ?? err.message
    } else {
      errorCode.value = 'network_error'
      error.value = '网络异常，请稍后重试'
    }
  }

  async function login(username: string, password: string): Promise<boolean> {
    busy.value = true
    error.value = ''
    errorCode.value = ''
    try {
      applyAuth(await api.login(username, password))
      await probeAdmin()
      dialogOpen.value = false
      return true
    } catch (err) {
      setError(err)
      return false
    } finally {
      busy.value = false
    }
  }

  async function register(username: string, password: string): Promise<boolean> {
    busy.value = true
    error.value = ''
    errorCode.value = ''
    try {
      applyAuth(await api.register(username, password))
      await probeAdmin()
      dialogOpen.value = false
      return true
    } catch (err) {
      setError(err)
      return false
    } finally {
      busy.value = false
    }
  }

  function logout(): void {
    clearLocal()
  }

  /** 收到 401 时清除本地失效登录态：后续重试不再携带旧 token（按匿名语义走） */
  function invalidateSession(): void {
    clearLocal()
    mode.value = 'login'
    error.value = ''
    errorCode.value = ''
    dialogOpen.value = true
  }

  function openDialog(nextMode: AuthMode = 'login'): void {
    mode.value = nextMode
    error.value = ''
    errorCode.value = ''
    dialogOpen.value = true
  }

  function closeDialog(): void {
    dialogOpen.value = false
    error.value = ''
    errorCode.value = ''
  }

  function switchMode(): void {
    mode.value = mode.value === 'login' ? 'register' : 'login'
    error.value = ''
    errorCode.value = ''
  }

  return {
    enabled,
    registrationEnabled,
    memoryMode,
    token,
    user,
    isAdmin,
    dialogOpen,
    mode,
    busy,
    error,
    errorCode,
    isLoggedIn,
    displayName,
    bootstrap,
    login,
    register,
    logout,
    invalidateSession,
    openDialog,
    closeDialog,
    switchMode,
  }
})
