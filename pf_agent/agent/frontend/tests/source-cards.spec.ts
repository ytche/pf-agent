import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SourceCards from '@/components/SourceCards.vue'
import type { Source } from '@/api/contract'

const sources: Source[] = [1, 2, 3, 4, 5].map((n) => ({
  book: `核心规则书${n}`,
  tocPath: `第一章/第 ${n} 节`,
  content: `来源正文 ${n}`,
  chunkId: `chunk-${n}`,
}))

describe('SourceCards', () => {
  it('默认展示 3 张，展开后展示全部', async () => {
    const wrapper = mount(SourceCards, { props: { sources } })
    expect(wrapper.findAll('.source-card')).toHaveLength(3)
    const expand = wrapper.find('.expand-sources')
    expect(expand.text()).toContain('查看全部 5 条')
    await expand.trigger('click')
    expect(wrapper.findAll('.source-card')).toHaveLength(5)
    expect(wrapper.find('.expand-sources').text()).toContain('收起来源')
  })

  it('上标定位会展开全部、滚动并高亮目标卡片', async () => {
    const wrapper = mount(SourceCards, { props: { sources }, attachTo: document.body })
    const instance = wrapper.vm as unknown as { focusSource: (n: number) => Promise<void> }
    const scrolled: Element[] = []
    Element.prototype.scrollIntoView = function scrollIntoView() {
      scrolled.push(this)
    }
    await instance.focusSource(4)
    expect(wrapper.findAll('.source-card')).toHaveLength(5)
    const fourth = wrapper.findAll('.source-card')[3]
    expect(fourth.classes()).toContain('cite-flash')
    expect(scrolled).toContain(fourth.element)
    wrapper.unmount()
  })

  it('历史消息无来源快照时显示降级提示', () => {
    const wrapper = mount(SourceCards, { props: { sources: null } })
    expect(wrapper.text()).toContain('历史来源未保存')
    expect(wrapper.findAll('.source-card')).toHaveLength(0)
  })

  it('新回答优先展示结构化书名与缩写', () => {
    const wrapper = mount(SourceCards, {
      props: {
        sources: [
          {
            book: '核心规则书 (CRB)',
            bookNameCn: '核心规则书',
            bookAbbreviation: 'CRB',
            tocPath: '战斗',
            content: '正文',
          },
        ],
      },
    })
    expect(wrapper.find('.source-book').text()).toBe('核心规则书')
    expect(wrapper.find('.source-abbr').text()).toBe('CRB')
    expect(wrapper.find('.source-head').text()).not.toContain('(CRB)')
  })

  it('历史快照缺结构化字段时回退兼容 book，不显示缩写', () => {
    const legacy = mount(SourceCards, {
      props: { sources: [{ book: '旧版规则书 (OLD)', tocPath: '战斗', content: '正文' }] },
    })
    expect(legacy.find('.source-book').text()).toBe('旧版规则书 (OLD)')
    expect(legacy.find('.source-abbr').exists()).toBe(false)

    const nullable = mount(SourceCards, {
      props: {
        sources: [
          {
            book: '旧版规则书 (OLD)',
            bookNameCn: null,
            bookAbbreviation: null,
            tocPath: '战斗',
            content: '正文',
          },
        ],
      },
    })
    expect(nullable.find('.source-book').text()).toBe('旧版规则书 (OLD)')
    expect(nullable.find('.source-abbr').exists()).toBe(false)
  })

  it('展示后端兜底标题，前端不做二次截断', () => {
    const longTitle = '长'.repeat(80)
    const wrapper = mount(SourceCards, {
      props: {
        sources: [{ book: '规则书', title: longTitle, tocPath: '规则 > 长标题', content: '正文' }],
      },
    })
    expect(wrapper.find('.source-title').text()).toBe(longTitle)
    expect(wrapper.find('.source-path').text()).toBe('规则 > 长标题')
  })

  it('旧快照无 title 时回退 tocPath 末段', () => {
    const wrapper = mount(SourceCards, {
      props: {
        sources: [
          { book: '旧版规则书', tocPath: '规则 → 战斗 → 追逐与休整', content: '正文' },
          { book: '规则书', title: null, tocPath: '核心职业/盗贼/page_49.md', content: '正文' },
        ],
      },
    })
    expect(wrapper.findAll('.source-title')[0].text()).toBe('追逐与休整')
    expect(wrapper.findAll('.source-title')[1].text()).toBe('page_49.md')
  })

  it('title 为空白时回退 tocPath 末段，不显示空标题行', () => {
    const wrapper = mount(SourceCards, {
      props: {
        sources: [
          { book: '规则书', title: '  ', tocPath: '规则 > 条目', content: '正文' },
          { book: '规则书', title: '', tocPath: '', content: '正文' },
        ],
      },
    })
    expect(wrapper.findAll('.source-title')[0].text()).toBe('条目')
    expect(wrapper.findAll('.source-title')).toHaveLength(1)
  })

  it('来源原文按纯文本渲染，不执行 HTML', () => {
    const wrapper = mount(SourceCards, {
      props: {
        sources: [{ book: '规则书', tocPath: '路径', content: '<img src=x onerror="window.__pwned=true">' }],
      },
    })
    expect(wrapper.find('.source-content').element.textContent).toBe('<img src=x onerror="window.__pwned=true">')
    expect(wrapper.find('.source-content img').exists()).toBe(false)
  })
})
