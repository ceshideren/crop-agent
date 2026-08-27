<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/api'
import type { DocContent } from '@/types'

const route = useRoute()
const docId = route.params.docId as string

const loading = ref(true)
const error = ref('')
const doc = ref<DocContent | null>(null)

const CAT_LABEL: Record<string, string> = {
  crops: '作物',
  diseases: '病害',
  techniques: '技术',
}
const FORMAT_LABEL: Record<string, string> = {
  md: 'Markdown',
  txt: '文本',
  docx: 'Word',
  pptx: 'PPT',
}

function catLabel(cat: string) {
  return CAT_LABEL[cat] || '其他'
}

/** pptx 内容按 `--- 第 N 页 ---` 标记切分为幻灯片列表。 */
const slides = computed<{ n: number; text: string }[]>(() => {
  const d = doc.value
  if (!d || d.format !== 'pptx') return []
  const parts = (d.content || '').split(/^--- 第 (\d+) 页 ---$/m)
  const out: { n: number; text: string }[] = []
  for (let i = 1; i + 1 < parts.length; i += 2) {
    const text = (parts[i + 1] || '').trim()
    if (text) out.push({ n: Number(parts[i]), text })
  }
  return out
})

onMounted(async () => {
  try {
    const res = await api.getDocContent(docId)
    if (res.data.code !== 200) {
      error.value = res.data.message || '预览加载失败'
    } else {
      doc.value = res.data.data
    }
  } catch {
    error.value = '预览加载失败'
  } finally {
    loading.value = false
  }
})

function onDownload() {
  api.downloadKnowledge(docId)
}
</script>

<template>
  <div class="pv-view">
    <div v-if="loading" v-loading="true" class="pv-loading"></div>

    <div v-else-if="error" class="pv-error card">
      <el-icon class="pv-error-icon"><WarningFilled /></el-icon>
      <p class="pv-error-text">{{ error }}</p>
      <router-link to="/knowledge" class="pv-link">← 返回知识库</router-link>
    </div>

    <template v-else-if="doc">
      <header class="pv-header card">
        <div class="pv-head-left">
          <router-link to="/knowledge" class="pv-link">← 返回知识库</router-link>
          <h1 class="pv-title">{{ doc.title }}</h1>
          <div class="pv-tags">
            <el-tag v-if="doc.category" size="small" effect="light">
              {{ catLabel(doc.category) }}
            </el-tag>
            <el-tag size="small" effect="plain">
              {{ FORMAT_LABEL[doc.format] || doc.format }}
            </el-tag>
            <el-tooltip :content="doc.doc_id" placement="top">
              <span class="pv-docid">{{ doc.doc_id }}</span>
            </el-tooltip>
          </div>
        </div>
        <el-button type="primary" plain @click="onDownload">
          <el-icon><Download /></el-icon>&nbsp;下载原文件
        </el-button>
      </header>

      <!-- PPT：按页渲染幻灯片卡片 -->
      <div v-if="doc.format === 'pptx' && slides.length" class="pv-slides">
        <section v-for="s in slides" :key="s.n" class="pv-slide card">
          <h2 class="pv-slide-num">第 {{ s.n }} 页</h2>
          <p class="pv-slide-text">{{ s.text }}</p>
        </section>
      </div>

      <!-- Word / Markdown / 文本：文档阅读面板 -->
      <div v-else class="pv-body card">
        <pre class="pv-content">{{ doc.content }}</pre>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.pv-view {
  max-width: 920px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pv-loading {
  min-height: 300px;
}

.pv-error {
  padding: 48px 24px;
  text-align: center;
  color: #8a9785;

  .pv-error-icon {
    font-size: 28px;
    margin-bottom: 8px;
  }

  .pv-error-text {
    margin: 0 0 12px;
  }
}

.pv-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  flex-wrap: wrap;
}

.pv-head-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.pv-link {
  color: var(--crop-green);
  text-decoration: none;
  font-size: 14px;

  &:hover {
    text-decoration: underline;
  }
}

.pv-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.pv-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pv-docid {
  color: #9aa892;
  font-size: 12.5px;
  cursor: help;
}

.pv-slides {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pv-slide {
  padding: 16px 18px;
}

.pv-slide-num {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--crop-blue);
  font-weight: 600;
}

.pv-slide-text {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.8;
  color: #4a5646;
  font-size: 14px;
}

.pv-body {
  padding: 0;
  overflow: hidden;
}

.pv-content {
  margin: 0;
  padding: 18px 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13.5px;
  line-height: 1.8;
  color: #4a5646;
}
</style>
