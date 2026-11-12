<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ content: string }>()
const emit = defineEmits<{ cite: [n: number] }>()

const container = ref<HTMLElement | null>(null)
const html = computed(() => renderMarkdown(props.content))

function onClick(event: MouseEvent): void {
  const target = event.target
  if (!(target instanceof Element)) return
  const sup = target.closest('sup.cite')
  if (!sup || !container.value?.contains(sup)) return
  const raw = sup.getAttribute('data-n')
  if (!raw) return
  const n = Number(raw)
  if (Number.isFinite(n) && n > 0) emit('cite', n)
}
</script>

<template>
  <div ref="container" class="answer-body" @click="onClick" v-html="html"></div>
</template>
