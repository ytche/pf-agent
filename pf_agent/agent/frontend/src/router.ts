import { computed, ref } from 'vue'

const href = ref(window.location.hash || '#/')

window.addEventListener('hashchange', () => {
  href.value = window.location.hash || '#/'
})

/** hash 路由：#/ 与 #/c/{id}；刷新任意 hash 都命中同一 index.html */
export function useHashRoute() {
  const conversationId = computed(() => {
    const match = /^#\/c\/([^/?#]+)/.exec(href.value)
    return match ? decodeURIComponent(match[1]) : null
  })
  return { href, conversationId }
}

export function navigateToConversation(id: string | null): void {
  const next = id ? `#/c/${encodeURIComponent(id)}` : '#/'
  if (window.location.hash !== next) window.location.hash = next
}
