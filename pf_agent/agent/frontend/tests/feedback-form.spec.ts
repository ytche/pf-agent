import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import FeedbackForm from '@/components/FeedbackForm.vue'
import { useAuthStore } from '@/stores/auth'
import { storage } from '@/utils/storage'
import { installFetch, json } from './helpers/mock-api'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('FeedbackForm', () => {
  it('提交收到 401 时复用 invalidateSession 清除失效 token 并打开登录层', async () => {
    storage.setToken('expired-token')
    installFetch((request) => {
      if (request.path === '/api/chat/feedback') return json(401, { error: 'unauthorized' })
      return json(404, { error: 'not_found' })
    })

    const auth = useAuthStore()
    auth.token = 'expired-token'
    auth.user = { uid: 1, username: 'tester', nickname: 'tester' }

    const wrapper = mount(FeedbackForm, {
      props: {
        conversationId: 'c1',
        question: '问题',
        answer: '回答',
        sources: [],
      },
    })
    await wrapper.find('select').setValue('事实错误')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(auth.token).toBe('')
    expect(storage.getToken()).toBe('')
    expect(auth.isLoggedIn).toBe(false)
    expect(auth.dialogOpen).toBe(true)
    expect(wrapper.find('.feedback-status').text()).toContain('登录状态已失效')
  })
})
