import { computed, ref } from 'vue'

const href = ref(window.location.hash || '#/')

window.addEventListener('hashchange', () => {
  href.value = window.location.hash || '#/'
})

/** hash 路由：#/、#/c/{id} 与 #/usage；刷新任意 hash 都命中同一 index.html */
export function useHashRoute() {
  const conversationId = computed(() => {
    const match = /^#\/c\/([^/?#]+)/.exec(href.value)
    return match ? decodeURIComponent(match[1]) : null
  })
  const isUsage = computed(() => /^#\/usage(?:[/?#]|$)/.test(href.value))
  return { href, conversationId, isUsage }
}

export function navigateToConversation(id: string | null): void {
  const next = id ? `#/c/${encodeURIComponent(id)}` : '#/'
  if (window.location.hash !== next) window.location.hash = next
}

export function navigateToUsage(): void {
  if (window.location.hash !== '#/usage') window.location.hash = '#/usage'
}
