import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '@/utils/markdown'

describe('renderMarkdown 安全与引用', () => {
  it('移除 script 标签与事件属性', () => {
    const html = renderMarkdown('<script>window.__pwned = true</script>\n\n<img src="x" onerror="window.__pwned = true">')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<img')
  })

  it('剥离 javascript: 链接，正常链接补 rel=noopener', () => {
    const html = renderMarkdown('[bad](javascript:alert(1)) 与 [good](https://example.com/docs)')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).toContain('target="_blank"')
  })

  it('把正文 [#N] 转为可点击 sup，且不处理代码块内的编号', () => {
    const html = renderMarkdown('规则见 [#1] 与 [#2]。\n\n```\n[#3]\n```')
    const container = document.createElement('div')
    container.innerHTML = html
    const sups = container.querySelectorAll('sup.cite')
    expect(sups).toHaveLength(2)
    expect(sups[0].getAttribute('data-n')).toBe('1')
    expect(sups[1].textContent).toBe('[2]')
    expect(container.querySelector('pre')?.textContent).toContain('[#3]')
    expect(container.querySelector('pre')?.querySelector('sup')).toBeNull()
  })

  it('保留表格与代码块结构', () => {
    const html = renderMarkdown('| A | B |\n| - | - |\n| 1 | 2 |\n\n`inline`\n\n```\ncode\n```')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>')
    expect(html).toContain('<pre>')
  })

  it('空内容返回空串而不抛错', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
  })
})
