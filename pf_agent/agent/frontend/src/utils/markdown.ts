import DOMPurify from 'dompurify'
import { marked } from 'marked'

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote',
  'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'hr', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'sup', 'span', 'div',
]
const ALLOWED_ATTR = ['href', 'title', 'class', 'rel', 'target']

const CITATION_PATTERN = /\[#(\d+)\]/g

function replaceCitations(node: Text): void {
  const text = node.nodeValue ?? ''
  const pattern = new RegExp(CITATION_PATTERN.source, 'g')
  let match: RegExpExecArray | null
  let cursor = 0
  const fragment = document.createDocumentFragment()
  let replaced = false

  while ((match = pattern.exec(text)) !== null) {
    replaced = true
    if (match.index > cursor) fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)))
    const sup = document.createElement('sup')
    sup.className = 'cite'
    sup.dataset.n = match[1]
    sup.textContent = `[${match[1]}]`
    fragment.appendChild(sup)
    cursor = match.index + match[0].length
  }
  if (!replaced) return
  if (cursor < text.length) fragment.appendChild(document.createTextNode(text.slice(cursor)))
  node.parentNode?.replaceChild(fragment, node)
}

/**
 * 模型回答：marked 渲染 → DOMPurify 白名单消毒 → 文本节点中的 [#N] 转为
 * 组件内 sup 元素（通过 DOM 创建，不做 HTML 字符串事件绑定）。
 */
export function renderMarkdown(markdown: string | null | undefined): string {
  const source = typeof markdown === 'string' ? markdown : ''
  const raw = marked.parse(source, { async: false, gfm: true, breaks: false }) as string
  const container = document.createElement('div')
  container.innerHTML = DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
  })

  container.querySelectorAll('a').forEach((anchor) => {
    anchor.setAttribute('rel', 'noopener noreferrer')
    anchor.setAttribute('target', '_blank')
  })

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node: Node) {
      const value = node.nodeValue ?? ''
      if (!new RegExp(CITATION_PATTERN.source).test(value)) return NodeFilter.FILTER_REJECT
      const parent = node.parentElement
      if (parent?.closest('pre, code, a')) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const textNodes: Text[] = []
  while (walker.nextNode()) textNodes.push(walker.currentNode as Text)
  textNodes.forEach(replaceCitations)
  return container.innerHTML
}
