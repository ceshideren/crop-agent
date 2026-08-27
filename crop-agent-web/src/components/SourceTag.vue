<script setup lang="ts">
import type { Source } from '@/types'

defineProps<{ sources: Source[] }>()
</script>

<template>
  <div v-if="sources && sources.length" class="source-tags">
    <span
      v-for="s in sources"
      :key="s.chunk"
      class="source-tag"
      :title="`知识库相似度 ${s.score}`"
    >
      📄 {{ s.chunk }}
      <span class="num score">{{ s.score.toFixed(2) }}</span>
    </span>
  </div>
</template>

<style scoped lang="scss">
.source-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  font-size: 12px;
  border-radius: var(--radius-pill);
  background: #eef4f9;
  color: var(--crop-blue);
  border: 1px solid #d6e6f2;

  .score {
    color: var(--crop-brown);
  }
}
</style>
