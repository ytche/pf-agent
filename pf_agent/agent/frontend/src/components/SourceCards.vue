<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { Source } from '@/api/contract'

const props = defineProps<{
  sources: Source[] | null
}>()

const expanded = ref(false)
const cardRefs = ref<HTMLElement[]>([])

const visible = computed<Source[]>(() => {
  if (!props.sources) return []
  return expanded.value ? props.sources : props.sources.slice(0, 3)
})

const hiddenCount = computed(() => Math.max(0, (props.sources?.length ?? 0) - 3))

/** 优先结构化中文书名，缺失回退兼容字段 book，再回退未知来源 */
function bookTitle(source: Source): string {
  return source.bookNameCn?.trim() || source.book?.trim() || '未知来源'
}

/** 仅当有结构化书名时单独展示缩写徽标；旧快照/无缩写返回空串 */
function bookAbbreviation(source: Source): string {
  const name = source.bookNameCn?.trim()
  const abbreviation = source.bookAbbreviation?.trim()
  if (!name || !abbreviation || abbreviation === name) return ''
  return abbreviation
}

/** 展示标题：优先后端兜底 title（已去冒号/截断），缺失时回退 tocPath 末段；前端不二次截断 */
function sourceTitle(source: Source): string {
  const title = source.title?.trim()
  if (title) return title
  return tocPathTail(source.tocPath)
}

/** tocPath 末段：兼容 "→" / ">" / "/" 分隔，取最后一个非空段 */
function tocPathTail(tocPath: string | null | undefined): string {
  const segments = (tocPath ?? '').split(/\s*(?:→|>|\/)\s*/)
  for (let i = segments.length - 1; i >= 0; i--) {
    const segment = segments[i]?.trim()
    if (segment) return segment
  }
  return ''
}

function setCardRef(element: Element | null, index: number): void {
  if (element instanceof HTMLElement) cardRefs.value[index] = element
}

async function focusSource(n: number): Promise<void> {
  const list = props.sources
  if (!list || list.length === 0) return
  const index = n - 1
  if (index < 0 || index >= list.length) return
  if (index >= 3 && !expanded.value) {
    expanded.value = true
    await nextTick()
  }
  const element = cardRefs.value[index]
  if (!element) return
  element.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  element.classList.remove('cite-flash')
  void element.offsetWidth
  element.classList.add('cite-flash')
  setTimeout(() => element.classList.remove('cite-flash'), 1900)
}

defineExpose({ focusSource })
</script>

<template>
  <p v-if="sources === null" class="source-note">历史来源未保存</p>

  <section v-else-if="sources.length" class="sources" aria-label="来源">
    <article
      v-for="(source, index) in visible"
      :key="`${index}-${bookTitle(source)}-${source.tocPath}`"
      :ref="(element) => setCardRef(element as Element | null, index)"
      class="source-card"
      :data-source-index="index + 1"
    >
      <header class="source-head">
        <span class="source-badge">[{{ index + 1 }}]</span>
        <span class="source-book">{{ bookTitle(source) }}</span>
        <span v-if="bookAbbreviation(source)" class="source-abbr">{{ bookAbbreviation(source) }}</span>
      </header>
      <p v-if="sourceTitle(source)" class="source-title">{{ sourceTitle(source) }}</p>
      <p v-if="source.tocPath" class="source-path">{{ source.tocPath }}</p>
      <pre class="source-content">{{ source.content }}</pre>
    </article>

    <button v-if="hiddenCount > 0" class="ghost small expand-sources" type="button" @click="expanded = !expanded">
      {{ expanded ? '收起来源' : `查看全部 ${sources.length} 条` }}
    </button>
  </section>
</template>

<style scoped>
.source-abbr {
  flex: none;
  font-size: 11.5px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0 5px;
}
</style>
