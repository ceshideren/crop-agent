<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ text: string; animate?: boolean }>()

const shown = ref('')
let timer: number | undefined

watch(
  () => props.text,
  (val) => {
    if (timer) window.clearInterval(timer)
    if (!props.animate) {
      shown.value = val
      return
    }
    const target = val
    let i = 0
    shown.value = ''
    timer = window.setInterval(() => {
      i = Math.min(target.length, i + 8)
      shown.value = target.slice(0, i)
      if (i >= target.length) window.clearInterval(timer)
    }, 16)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

const html = computed(() => renderMarkdown(shown.value))
</script>

<template>
  <div class="stream-text markdown-body" v-html="html"></div>
</template>
