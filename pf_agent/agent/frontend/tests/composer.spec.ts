import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import Composer from '@/components/Composer.vue'

describe('Composer', () => {
  it('切换会话清空未发送草稿并复位高度', async () => {
    const wrapper = mount(Composer, {
      props: { pending: false, disabled: false, conversationId: 'c1' },
    })
    const input = wrapper.find('textarea')
    await input.setValue('未发送草稿')
    ;(input.element as HTMLTextAreaElement).style.height = '120px'

    await wrapper.setProps({ conversationId: 'c2' })
    await nextTick()

    const next = wrapper.find('textarea').element as HTMLTextAreaElement
    expect(next.value).toBe('')
    expect(next.style.height).toBe('')
  })

  it('Enter 发送、Shift+Enter 换行，等待中不可发送', async () => {
    const wrapper = mount(Composer, {
      props: { pending: false, disabled: false, conversationId: 'c1' },
    })
    const input = wrapper.find('textarea')
    await input.setValue('第一行')
    await input.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('send')).toBeUndefined()

    await input.setValue('问题')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')?.[0]).toEqual(['问题'])
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe('')

    await wrapper.setProps({ pending: true })
    await input.setValue('等待中')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')).toHaveLength(1)
  })
})
