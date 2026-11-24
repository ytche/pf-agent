import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AuthDialog from '@/components/AuthDialog.vue'
import { useAuthStore } from '@/stores/auth'

describe('AuthDialog 注册入口', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.dialogOpen = true
    auth.mode = 'login'
  })

  it('注册开放时显示切换入口', () => {
    const auth = useAuthStore()
    auth.registrationEnabled = true
    const wrapper = mount(AuthDialog, { global: { stubs: { teleport: true } } })
    expect(wrapper.find('.modal-links').text()).toContain('没有账号？注册')
  })

  it('注册关闭且处于登录模式时隐藏切换入口', () => {
    const auth = useAuthStore()
    auth.registrationEnabled = false
    const wrapper = mount(AuthDialog, { global: { stubs: { teleport: true } } })
    expect(wrapper.find('.modal-links').text()).not.toContain('没有账号？注册')
  })
})
