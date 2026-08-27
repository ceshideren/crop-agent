<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { highlightHtml } from '@/utils/highlight'
import { formatDate } from '@/utils/time'
import type { ChunkDetail, KnowledgeDoc, SearchResultDoc } from '@/types'

/* ---------------- 分类与相关性元信息 ---------------- */

const CATEGORY_MAP: Record<string, { label: string; cls: string }> = {
  crops: { label: '作物', cls: 'cat-crops' },
  diseases: { label: '病害', cls: 'cat-diseases' },
  techniques: { label: '技术', cls: 'cat-techniques' },
}
const KNOWN_CATEGORIES = ['crops', 'diseases', 'techniques']

function catInfo(cat: string) {
  return CATEGORY_MAP[cat] || { label: '其他', cls: 'cat-other' }
}

function relevanceOf(score: number): { label: string; cls: string } {
  if (score >= 0.8) return { label: '高相关', cls: 'rel-high' }
  if (score >= 0.5) return { label: '相关', cls: 'rel-mid' }
  return { label: '低相关', cls: 'rel-low' }
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function extOf(name?: string): string {
  const i = (name || '').lastIndexOf('.')
  return i >= 0 ? (name || '').slice(i + 1).toLowerCase() : ''
}

/* ---------------- 状态 ---------------- */

const docs = ref<KnowledgeDoc[]>([])
const kbMeta = ref<{ threshold: number; embedder: string }>({ threshold: 0.15, embedder: '' })

const activeTab = ref<'search' | 'docs'>('search')
const query = ref('')
const category = ref('')
const searching = ref(false)
const searched = ref(false)
const results = ref<SearchResultDoc[]>([])
const expandedChunks = ref<Set<string>>(new Set())
const lowPanelOpen = ref<string[]>([])

// 文档管理
const selectedRows = ref<KnowledgeDoc[]>([])
const busyReindex = ref<Set<string>>(new Set())
const batchBusy = ref(false)
const highlightDocIds = ref<Set<string>>(new Set())
const fileInput = ref<HTMLInputElement>()
const router = useRouter()

// 文档管理：前端分页与分类筛选（保持列表接口不变）
const page = ref(1)
const pageSize = ref(10)
const catFilter = ref('')
const tableRef = ref<{ clearSelection: () => void } | null>(null)

// 修改分类弹窗
const catEditVisible = ref(false)
const catEditDoc = ref<KnowledgeDoc | null>(null)
const catEditValue = ref('')

// 抽屉
const previewVisible = ref(false)
const preview = ref({ title: '', category: '', content: '', loading: false })
const chunksVisible = ref(false)
const chunksDoc = ref<KnowledgeDoc | null>(null)
const chunkList = ref<ChunkDetail[]>([])
const chunksLoading = ref(false)

// 上传
const upload = ref({ active: false, phase: 'upload' as 'upload' | 'parsing', percent: 0 })

/* ---------------- 检索结果分级 ---------------- */

const highResults = computed(() => results.value.filter((d) => d.score >= 0.8))
const midResults = computed(() => results.value.filter((d) => d.score >= 0.5 && d.score < 0.8))
const lowResults = computed(() => results.value.filter((d) => d.score >= 0.3 && d.score < 0.5))
const visibleResults = computed(() => [...highResults.value, ...midResults.value, ...lowResults.value])

const stats = computed(() => {
  const totalChunks = visibleResults.value.reduce((n, d) => n + d.chunks.length, 0)
  return {
    totalChunks,
    docCount: visibleResults.value.length,
    high: highResults.value.length,
  }
})

const showEmptyHint = computed(() => searched.value && visibleResults.value.length === 0)

/* ---------------- 数据加载 ---------------- */

async function loadDocs() {
  try {
    const res = await api.listKnowledge()
    const data = res.data.data
    docs.value = data.docs || []
    kbMeta.value = data.meta || kbMeta.value
  } catch {
    ElMessage.error('加载知识库失败')
  }
}

/* ---------------- 文档管理：分页与筛选 ---------------- */

const filteredDocs = computed(() => {
  const list = docs.value
  if (!catFilter.value) return list
  if (catFilter.value === 'other') {
    return list.filter((d) => !KNOWN_CATEGORIES.includes(d.category || ''))
  }
  return list.filter((d) => d.category === catFilter.value)
})

const pagedDocs = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredDocs.value.slice(start, start + pageSize.value)
})

watch([filteredDocs, pageSize], () => {
  const max = Math.max(1, Math.ceil(filteredDocs.value.length / pageSize.value))
  if (page.value > max) page.value = max
})

function onCatFilterChange() {
  page.value = 1
}

function onDownload(row: KnowledgeDoc) {
  api.downloadKnowledge(row.doc_id)
}

/* ---------------- 修改分类 ---------------- */

function openCatEdit(row: KnowledgeDoc) {
  catEditDoc.value = row
  catEditValue.value = KNOWN_CATEGORIES.includes(row.category || '')
    ? (row.category as string)
    : 'other'
  catEditVisible.value = true
}

async function saveCatEdit() {
  if (!catEditDoc.value) return
  const doc = catEditDoc.value
  try {
    const res = await api.updateKnowledgeCategory(doc.doc_id, catEditValue.value)
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '修改分类失败')
      return
    }
    ElMessage.success(`已将「${doc.title}」分类改为 ${catInfo(catEditValue.value).label}`)
    catEditVisible.value = false
    await loadDocs()
  } catch {
    ElMessage.error('修改分类失败')
  }
}

/* ---------------- 检索 ---------------- */

async function onSearch() {
  const q = query.value.trim()
  if (!q) {
    results.value = []
    searched.value = false
    return
  }
  searching.value = true
  try {
    // "其他"为前端过滤（后端只支持精确分类匹配），不传给接口
    const cat = category.value === 'other' ? '' : category.value
    const res = await api.searchKnowledge(q, cat)
    let list: SearchResultDoc[] = res.data.data.results || []
    if (category.value === 'other') {
      list = list.filter((d) => !KNOWN_CATEGORIES.includes(d.category))
    }
    results.value = list
    searched.value = true
    expandedChunks.value = new Set()
  } catch {
    ElMessage.error('检索失败')
  } finally {
    searching.value = false
  }
}

function onClearQuery() {
  query.value = ''
  results.value = []
  searched.value = false
}

function onCategoryChange() {
  if (query.value.trim()) onSearch()
}

function toggleChunk(docId: string, chunkId: string) {
  const key = `${docId}:${chunkId}`
  const next = new Set(expandedChunks.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedChunks.value = next
}

/* ---------------- 文档管理 ---------------- */

function onSelectionChange(rows: KnowledgeDoc[]) {
  selectedRows.value = rows
}

async function onReindex(row: KnowledgeDoc) {
  const next = new Set(busyReindex.value)
  next.add(row.doc_id)
  busyReindex.value = next
  try {
    const res = await api.reindexKnowledge(row.doc_id)
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '重建索引失败')
    } else {
      ElMessage.success(`已重建「${row.title}」索引（${res.data.data.chunk_count} 个片段）`)
    }
    await loadDocs()
  } catch {
    ElMessage.error('重建索引失败')
  } finally {
    const done = new Set(busyReindex.value)
    done.delete(row.doc_id)
    busyReindex.value = done
  }
}

async function onDelete(row: KnowledgeDoc) {
  try {
    const res = await api.deleteKnowledge(row.doc_id)
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '删除失败')
      return
    }
    ElMessage.success(`已删除「${row.title}」`)
    await loadDocs()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function onBatchDelete() {
  const ids = selectedRows.value.map((r) => r.doc_id)
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${ids.length} 个文档？删除后不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  batchBusy.value = true
  try {
    const res = await api.batchDeleteKnowledge(ids)
    const data = res.data.data
    if (res.data.code === 200 && data.count > 0) {
      ElMessage.success(`已删除 ${data.count} 个文档`)
      if (data.failed?.length) ElMessage.warning(`${data.failed.length} 个文档删除失败`)
    } else {
      ElMessage.error(res.data.message || '批量删除失败')
    }
    selectedRows.value = []
    tableRef.value?.clearSelection()
    await loadDocs()
  } catch {
    ElMessage.error('批量删除失败')
  } finally {
    batchBusy.value = false
  }
}

async function onBatchReindex() {
  const ids = selectedRows.value.map((r) => r.doc_id)
  batchBusy.value = true
  try {
    const res = await api.batchReindexKnowledge(ids)
    const data = res.data.data
    if (res.data.code === 200 && data.count > 0) {
      ElMessage.success(`已重建 ${data.count} 个文档索引`)
      if (data.failed?.length) ElMessage.warning(`${data.failed.length} 个文档重建失败`)
    } else {
      ElMessage.error(res.data.message || '批量重建失败')
    }
    selectedRows.value = []
    tableRef.value?.clearSelection()
    await loadDocs()
  } catch {
    ElMessage.error('批量重建失败')
  } finally {
    batchBusy.value = false
  }
}

/* ---------------- 抽屉：预览 / 片段 ---------------- */

async function openPreview(row: KnowledgeDoc) {
  // Word/PPT 在新标签页预览；md/txt 沿用抽屉
  const ext = extOf(row.file_name || row.source)
  if (ext === 'docx' || ext === 'pptx') {
    window.open(
      router.resolve({ name: 'knowledge-preview', params: { docId: row.doc_id } }).href,
      '_blank',
    )
    return
  }
  preview.value = { title: row.title, category: row.category || '', content: '', loading: true }
  previewVisible.value = true
  try {
    const res = await api.getDocContent(row.doc_id)
    if (res.data.code !== 200) {
      preview.value.content = `（无法预览：${res.data.message || '源文件缺失'}）`
    } else {
      preview.value.content = res.data.data.content || ''
    }
  } catch {
    preview.value.content = '（预览加载失败）'
  } finally {
    preview.value.loading = false
  }
}

async function openChunks(row: KnowledgeDoc) {
  chunksDoc.value = row
  chunkList.value = []
  chunksVisible.value = true
  chunksLoading.value = true
  try {
    const res = await api.getDocChunks(row.doc_id)
    chunkList.value = res.data.data.chunks || []
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '片段加载失败')
    }
  } catch {
    ElMessage.error('片段加载失败')
  } finally {
    chunksLoading.value = false
  }
}

async function onDeleteChunk(chunk: ChunkDetail) {
  try {
    const res = await api.deleteChunk(chunk.chunk_id)
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '删除片段失败')
      return
    }
    ElMessage.success(`已删除片段 ${chunk.chunk_index + 1}`)
    chunkList.value = chunkList.value.filter((c) => c.chunk_id !== chunk.chunk_id)
    await loadDocs()
  } catch {
    ElMessage.error('删除片段失败')
  }
}

/* ---------------- 上传 ---------------- */

function triggerUpload() {
  fileInput.value?.click()
}

async function onUpload(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  upload.value = { active: true, phase: 'upload', percent: 0 }
  try {
    const res = await api.uploadKnowledge(file, (p) => {
      // 传输完毕（≥99%）后进入服务端解析阶段
      upload.value.phase = p >= 99 ? 'parsing' : 'upload'
      upload.value.percent = p
    })
    upload.value.phase = 'parsing'
    if (res.data.code !== 200) {
      ElMessage.error(res.data.message || '上传失败，仅支持 .md / .txt / .docx / .pptx')
    } else {
      ElMessage.success(
        `已入库 ${res.data.data.filename}，生成 ${res.data.data.chunks} 个片段`,
      )
      await loadDocs()
      const docId = res.data.data.doc_id
      if (docId) {
        const next = new Set(highlightDocIds.value)
        next.add(docId)
        highlightDocIds.value = next
        setTimeout(() => {
          const done = new Set(highlightDocIds.value)
          done.delete(docId)
          highlightDocIds.value = done
        }, 2200)
      }
    }
  } catch {
    ElMessage.error('上传失败，仅支持 .md / .txt / .docx / .pptx')
  } finally {
    upload.value.active = false
    input.value = ''
  }
}

function rowClassName({ row }: { row: KnowledgeDoc }) {
  return highlightDocIds.value.has(row.doc_id) ? 'row-flash' : ''
}

onMounted(loadDocs)
</script>

<template>
  <div class="kb-view">
    <header class="kb-header">
      <div>
        <h1>知识库</h1>
        <p class="sub">
          已索引 {{ docs.length }} 篇文档 · 检索阈值 ≥{{ kbMeta.threshold }} ·
          {{ kbMeta.embedder || '本地嵌入' }}
        </p>
      </div>
      <div class="header-actions">
        <label class="upload-btn" :class="{ disabled: upload.active }">
          <el-icon v-if="!upload.active"><Upload /></el-icon>
          <el-icon v-else class="is-loading"><Loading /></el-icon>
          &nbsp;{{ upload.active ? '上传中…' : '上传文档' }}
          <input
            ref="fileInput"
            type="file"
            accept=".md,.txt,.docx,.pptx"
            hidden
            @change="onUpload"
          />
        </label>
      </div>
    </header>

    <!-- 上传进度反馈 -->
    <div v-if="upload.active" class="upload-progress card">
      <template v-if="upload.phase === 'upload'">
        <div class="progress-head">
          <span>正在上传… {{ upload.percent }}%</span>
          <span class="num">{{ upload.percent }}%</span>
        </div>
        <el-progress :percentage="upload.percent" :show-text="false" :stroke-width="6" />
      </template>
      <template v-else>
        <div class="progress-head"><span>正在解析文档并建立索引…</span></div>
        <div class="grow-bar"></div>
      </template>
    </div>

    <el-tabs v-model="activeTab" class="kb-tabs">
      <!-- ==================== 检索测试 ==================== -->
      <el-tab-pane label="检索测试" name="search">
        <div class="search-bar card">
          <el-select
            v-model="category"
            class="cat-select"
            placeholder="全部分类"
            @change="onCategoryChange"
          >
            <el-option label="全部分类" value="" />
            <el-option label="作物" value="crops" />
            <el-option label="病害" value="diseases" />
            <el-option label="技术" value="techniques" />
            <el-option label="其他" value="other" />
          </el-select>
          <el-input
            v-model="query"
            placeholder="检索知识库，例如：稻瘟病"
            clearable
            @keyup.enter="onSearch"
            @clear="onClearQuery"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button type="primary" :loading="searching" @click="onSearch">
            检索
          </el-button>
        </div>

        <!-- 检索结果 -->
        <div v-if="searched" class="results">
          <div class="results-head">
            <h2>检索结果</h2>
            <span class="stats">
              共找到 {{ stats.totalChunks }} 条结果，来自 {{ stats.docCount }} 个文档，
              其中高相关 {{ stats.high }} 条
            </span>
          </div>

          <!-- 高相关 / 相关 -->
          <div v-for="d in [...highResults, ...midResults]" :key="d.doc_id" class="result-item card">
            <div class="result-head">
              <span class="cat-bar" :class="catInfo(d.category).cls"></span>
              <el-tag class="cat-tag" :class="catInfo(d.category).cls" size="small" effect="light">
                {{ catInfo(d.category).label }}
              </el-tag>
              <span class="result-title" v-html="highlightHtml(d.title, query)"></span>
              <span class="result-meta">
                <el-tag
                  class="rel-tag"
                  :class="relevanceOf(d.score).cls"
                  size="small"
                  effect="light"
                >
                  {{ relevanceOf(d.score).label }}
                </el-tag>
                <span class="num result-score">{{ d.score.toFixed(3) }}</span>
              </span>
            </div>

            <div class="chunk-list">
              <div
                v-for="c in d.chunks"
                :key="c.chunk_id"
                class="chunk-item"
                :class="{ expanded: expandedChunks.has(`${d.doc_id}:${c.chunk_id}`) }"
              >
                <div class="chunk-head">
                  <el-tooltip :content="c.chunk_id" placement="top">
                    <span class="chunk-label">片段 {{ c.chunk_index + 1 }}</span>
                  </el-tooltip>
                  <span class="num chunk-score">{{ c.score.toFixed(3) }}</span>
                </div>
                <p class="chunk-text" v-html="highlightHtml(c.text, query)"></p>
                <button
                  v-if="c.text.length > 80"
                  class="expand-btn"
                  @click="toggleChunk(d.doc_id, c.chunk_id)"
                >
                  {{ expandedChunks.has(`${d.doc_id}:${c.chunk_id}`) ? '收起' : '展开全文' }}
                </button>
              </div>
            </div>
            <p class="chunk-count-tip">该文档共命中 {{ d.chunks.length }} 个片段</p>
          </div>

          <!-- 低相关：折叠面板 -->
          <el-collapse v-if="lowResults.length" v-model="lowPanelOpen">
            <el-collapse-item :title="`可能相关（${lowResults.length} 条）`" name="low">
              <div
                v-for="d in lowResults"
                :key="d.doc_id"
                class="result-item card low-card"
              >
                <div class="result-head">
                  <span class="cat-bar" :class="catInfo(d.category).cls"></span>
                  <el-tag class="cat-tag" :class="catInfo(d.category).cls" size="small" effect="light">
                    {{ catInfo(d.category).label }}
                  </el-tag>
                  <span class="result-title" v-html="highlightHtml(d.title, query)"></span>
                  <span class="result-meta">
                    <el-tag
                      class="rel-tag"
                      :class="relevanceOf(d.score).cls"
                      size="small"
                      effect="light"
                    >
                      {{ relevanceOf(d.score).label }}
                    </el-tag>
                    <span class="num result-score">{{ d.score.toFixed(3) }}</span>
                  </span>
                </div>
                <div class="chunk-list">
                  <div v-for="c in d.chunks" :key="c.chunk_id" class="chunk-item">
                    <el-tooltip :content="c.chunk_id" placement="top">
                      <span class="chunk-label">片段 {{ c.chunk_index + 1 }}</span>
                    </el-tooltip>
                    <p class="chunk-text" v-html="highlightHtml(c.text, query)"></p>
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 空结果提示 -->
          <div v-if="showEmptyHint" class="empty-hint card">
            <el-icon class="empty-icon"><Search /></el-icon>
            <p>未找到高相关度内容，建议更换关键词或上传相关文档</p>
          </div>
        </div>
        <div v-else-if="searching" class="grow-bar"></div>
      </el-tab-pane>

      <!-- ==================== 文档管理 ==================== -->
      <el-tab-pane label="文档管理" name="docs">
        <!-- 批量操作工具栏 -->
        <div v-if="selectedRows.length" class="batch-toolbar card">
          <span class="batch-count">已选 {{ selectedRows.length }} 项</span>
          <el-button size="small" type="danger" plain :loading="batchBusy" @click="onBatchDelete">
            批量删除
          </el-button>
          <el-button size="small" type="primary" plain :loading="batchBusy" @click="onBatchReindex">
            批量重建索引
          </el-button>
          <el-button size="small" text @click="selectedRows = []">取消选择</el-button>
        </div>

        <!-- 空状态 -->
        <el-empty
          v-if="!docs.length"
          description="暂无文档，点击右上角上传"
          class="empty-docs card"
        >
          <el-button type="primary" @click="triggerUpload">上传文档</el-button>
        </el-empty>

        <!-- 文档表格 -->
        <div v-else class="table-card card">
          <div class="table-toolbar">
            <el-select
              v-model="catFilter"
              class="cat-select"
              placeholder="全部分类"
              clearable
              @change="onCatFilterChange"
            >
              <el-option label="全部分类" value="" />
              <el-option label="作物" value="crops" />
              <el-option label="病害" value="diseases" />
              <el-option label="技术" value="techniques" />
              <el-option label="其他" value="other" />
            </el-select>
          </div>
          <div class="table-scroll">
            <el-table
              ref="tableRef"
              :data="pagedDocs"
              style="width: 100%"
              row-key="doc_id"
              :reserve-selection="true"
              :row-class-name="rowClassName"
              @selection-change="onSelectionChange"
            >
              <el-table-column type="selection" width="44" />
              <el-table-column prop="title" label="标题" min-width="160" sortable>
                <template #default="{ row }">
                  <span class="doc-title" @click="openPreview(row)">{{ row.title }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="96">
                <template #default="{ row }">
                  <el-tag class="cat-tag" :class="catInfo(row.category).cls" size="small" effect="light">
                    {{ catInfo(row.category).label }}
                  </el-tag>
                </template>
              </el-table-column>
              <!-- <el-table-column prop="doc_id" label="文档 ID" width="110">
                <template #default="{ row }">
                  <span class="num doc-id">{{ row.doc_id }}</span>
                </template>
              </el-table-column> -->
              <el-table-column prop="chunk_count" label="片段数" width="90" align="center">
                <template #default="{ row }">
                  <el-tag
                    class="chunk-tag"
                    size="small"
                    effect="plain"
                    @click="openChunks(row)"
                  >
                    {{ row.chunk_count }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="130">
                <template #default="{ row }">
                  <span class="status-cell">
                    <el-tag
                      v-if="row.status === 'indexed'"
                      size="small"
                      type="success"
                      effect="light"
                    >
                      已索引
                    </el-tag>
                    <el-tag
                      v-else-if="row.status === 'indexing' || busyReindex.has(row.doc_id)"
                      size="small"
                      type="primary"
                      effect="light"
                    >
                      <el-icon class="is-loading"><Loading /></el-icon>&nbsp;索引中
                    </el-tag>
                    <el-tag v-else size="small" type="danger" effect="light">失败</el-tag>
                    <el-button
                      v-if="row.status === 'failed'"
                      class="retry-btn"
                      size="small"
                      text
                      type="danger"
                      @click="onReindex(row)"
                    >
                      重试
                    </el-button>
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" min-width="140">
                <template #default="{ row }">
                  <el-tooltip :content="row.source" placement="top" :show-after="300">
                    <span class="source-name">{{ row.file_name || row.source }}</span>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column prop="updated_at" label="更新时间" width="120" sortable>
                <template #default="{ row }">
                  <span class="num">{{ formatDate(row.updated_at) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="file_size" label="文件大小" width="100" align="right">
                <template #default="{ row }">
                  <span class="num">{{ formatSize(row.file_size) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="380" fixed="right">
                <template #default="{ row }">
                  <span class="row-actions">
                    <el-button size="small" text type="primary" @click="onDownload(row)">
                      <el-icon><Download /></el-icon>&nbsp;下载
                    </el-button>
                    <el-button size="small" text type="primary" @click="openPreview(row)">
                      预览
                    </el-button>
                    <el-button
                      size="small"
                      text
                      type="primary"
                      :loading="busyReindex.has(row.doc_id)"
                      @click="onReindex(row)"
                    >
                      重建索引
                    </el-button>
                    <el-button size="small" text type="primary" @click="openCatEdit(row)">
                      <el-icon><EditPen /></el-icon>&nbsp;改分类
                    </el-button>
                    <el-popconfirm
                      title="确认删除该文档？删除后不可恢复"
                      confirm-button-text="删除"
                      cancel-button-text="取消"
                      @confirm="onDelete(row)"
                    >
                      <template #reference>
                        <el-button size="small" text type="danger">删除</el-button>
                      </template>
                    </el-popconfirm>
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="table-pager">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="filteredDocs.length"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
            />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 预览 drawer -->
    <el-drawer
      v-model="previewVisible"
      :title="preview.title"
      size="42%"
      class="preview-drawer"
    >
      <div v-if="preview.category" class="drawer-tags">
        <el-tag class="cat-tag" :class="catInfo(preview.category).cls" size="small" effect="light">
          {{ catInfo(preview.category).label }}
        </el-tag>
      </div>
      <div v-loading="preview.loading" class="preview-body">
        <pre class="preview-content">{{ preview.content }}</pre>
      </div>
    </el-drawer>

    <!-- 片段 drawer -->
    <el-drawer
      v-model="chunksVisible"
      :title="chunksDoc ? `${chunksDoc.title} · 片段列表` : '片段列表'"
      size="42%"
      class="chunks-drawer"
    >
      <div v-loading="chunksLoading" class="chunk-drawer-list">
        <p v-if="!chunksLoading && !chunkList.length" class="drawer-empty">该文档暂无片段</p>
        <div v-for="(c, i) in chunkList" :key="c.chunk_id" class="drawer-chunk">
          <div class="drawer-chunk-head">
            <el-tooltip :content="c.chunk_id" placement="top">
              <span class="chunk-label">片段 {{ i + 1 }}</span>
            </el-tooltip>
            <span class="drawer-chunk-meta">
              <span class="num">{{ c.char_count }} 字</span>
              <el-popconfirm
                v-if="chunkList.length > 1"
                title="确认删除该片段？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="onDeleteChunk(c)"
              >
                <template #reference>
                  <el-button size="small" text type="danger">删除</el-button>
                </template>
              </el-popconfirm>
              <el-tooltip v-else content="至少保留一个片段" placement="top">
                <el-button size="small" text type="info" disabled>删除</el-button>
              </el-tooltip>
            </span>
          </div>
          <p class="drawer-chunk-text">{{ c.text.slice(0, 100) }}{{ c.text.length > 100 ? '…' : '' }}</p>
        </div>
      </div>
    </el-drawer>

    <!-- 修改分类弹窗 -->
    <el-dialog
      v-model="catEditVisible"
      :title="catEditDoc ? `修改分类 · ${catEditDoc.title}` : '修改分类'"
      width="360px"
    >
      <el-select v-model="catEditValue" style="width: 100%">
        <el-option label="作物" value="crops" />
        <el-option label="病害" value="diseases" />
        <el-option label="技术" value="techniques" />
        <el-option label="其他" value="other" />
      </el-select>
      <template #footer>
        <el-button @click="catEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCatEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.kb-view {
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px;
}

.kb-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;

  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 700;
  }
}

.sub {
  margin: 4px 0 0;
  color: #8a9785;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.upload-btn {
  display: inline-flex;
  align-items: center;
  padding: 10px 20px;
  border-radius: var(--radius-pill);
  background: var(--crop-green);
  color: #fff;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: #316f2c;
  }

  &.disabled {
    opacity: 0.7;
    cursor: progress;
  }
}

/* ---------- 上传进度 ---------- */
.upload-progress {
  margin-bottom: 14px;
  padding: 14px 16px;

  .progress-head {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
    color: #4a5646;
  }
}

/* ---------- Tabs ---------- */
.kb-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 16px;
  }
}

/* ---------- 搜索区 ---------- */
.search-bar {
  display: flex;
  gap: 12px;
  padding: 16px;
  margin-bottom: 20px;

  .cat-select {
    width: 130px;
    flex: 0 0 auto;
  }
}

/* ---------- 检索结果 ---------- */
.results {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.results-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;

  h2 {
    font-size: 22px;
    font-weight: 600;
    margin: 0;
  }

  .stats {
    color: #8a9785;
    font-size: 13px;
  }
}

.result-item {
  padding: 16px;
  overflow: hidden;
  position: relative;

  &.low-card {
    box-shadow: none;
    border-color: #eef1ea;
  }
}

.cat-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;

  &.cat-crops {
    background: #3d8b37;
  }

  &.cat-diseases {
    background: #d9534f;
  }

  &.cat-techniques {
    background: #4a9bd5;
  }

  &.cat-other {
    background: #9aa892;
  }
}

.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.result-title {
  font-weight: 600;
  color: var(--crop-green);
  overflow-wrap: anywhere;
  flex: 1 1 auto;
  min-width: 0;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.result-score {
  color: var(--crop-gold);
  font-weight: 600;
  font-size: 13px;
}

/* ---------- 分类 / 相关性标签 ---------- */
.cat-tag {
  flex: 0 0 auto;

  &.cat-crops {
    --el-tag-bg-color: #ebf4eb;
    --el-tag-border-color: #bcd8b8;
    --el-tag-text-color: #2f7a2a;
  }

  &.cat-diseases {
    --el-tag-bg-color: #fdf0ef;
    --el-tag-border-color: #f0c4c2;
    --el-tag-text-color: #c24540;
  }

  &.cat-techniques {
    --el-tag-bg-color: #edf5fb;
    --el-tag-border-color: #c2dcf0;
    --el-tag-text-color: #2f7fb8;
  }

  &.cat-other {
    --el-tag-bg-color: #f3f5f1;
    --el-tag-border-color: #d8ddd2;
    --el-tag-text-color: #7c8775;
  }
}

.rel-tag {
  &.rel-high {
    --el-tag-bg-color: #ebf4eb;
    --el-tag-border-color: #bcd8b8;
    --el-tag-text-color: #2f7a2a;
  }

  &.rel-mid {
    --el-tag-bg-color: #edf5fb;
    --el-tag-border-color: #c2dcf0;
    --el-tag-text-color: #2f7fb8;
  }

  &.rel-low {
    --el-tag-bg-color: #f3f5f1;
    --el-tag-border-color: #d8ddd2;
    --el-tag-text-color: #7c8775;
  }
}

/* ---------- 片段列表 ---------- */
.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chunk-item {
  border: 1px solid #eef1ea;
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  background: #fbfcfa;
}

.chunk-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.chunk-label {
  font-size: 12px;
  color: var(--crop-blue);
  cursor: help;
}

.chunk-score {
  font-size: 12px;
  color: #9aa892;
}

.chunk-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #4a5646;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.chunk-item.expanded .chunk-text {
  -webkit-line-clamp: unset;
  overflow: visible;
}

.expand-btn {
  margin-top: 6px;
  border: none;
  background: none;
  color: var(--crop-green);
  font-size: 13px;
  cursor: pointer;
  padding: 0;

  &:hover {
    text-decoration: underline;
  }
}

.chunk-count-tip {
  margin: 8px 0 0;
  font-size: 12px;
  color: #9aa892;
}

/* ---------- 空结果 ---------- */
.empty-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  color: #8a9785;

  .empty-icon {
    font-size: 20px;
  }

  p {
    margin: 0;
  }
}

/* ---------- 批量工具栏 ---------- */
.batch-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 14px;

  .batch-count {
    font-size: 13px;
    color: #4a5646;
    margin-right: auto;
  }
}

/* ---------- 表格 ---------- */
.table-card {
  padding: 4px 8px;
}

.table-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 10px 8px 0;
}

.table-pager {
  display: flex;
  justify-content: flex-end;
  padding: 12px 8px 8px;
}

.table-scroll {
  overflow-x: auto;
}

.doc-title {
  color: var(--crop-green);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;

  &:hover {
    text-decoration: underline;
  }
}

.doc-id {
  color: #9aa892;
  font-size: 12.5px;
}

.chunk-tag {
  cursor: pointer;
}

.source-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
  display: inline-block;
  vertical-align: bottom;
}

.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.retry-btn {
  padding: 0 4px;
}

/* 行操作按钮：常显（避免删除等按钮被误以为缺失） */
.row-actions {
  white-space: nowrap;

  :deep(.el-button + .el-button) {
    margin-left: 8px;
  }
}

/* 新增行高亮闪烁（上传完成后 2 秒） */
:deep(.el-table__row.row-flash) {
  animation: row-flash 2s var(--ease);
}

@keyframes row-flash {
  0% {
    background: #d8e8d7;
  }

  60% {
    background: #d8e8d7;
  }

  100% {
    background: transparent;
  }
}

/* ---------- 抽屉 ---------- */
.drawer-tags {
  margin-bottom: 10px;
}

.preview-body {
  min-height: 200px;
}

.preview-content {
  margin: 0;
  padding: 14px;
  background: #f7f9f5;
  border: 1px solid #eef1ea;
  border-radius: var(--radius-sm);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 70vh;
  overflow: auto;
}

.chunk-drawer-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drawer-chunk {
  border: 1px solid #eef1ea;
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  background: #fbfcfa;
}

.drawer-chunk-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.drawer-chunk-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #9aa892;
}

.drawer-chunk-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #4a5646;
  overflow-wrap: anywhere;
}

.drawer-empty {
  color: #9aa892;
  text-align: center;
}

/* ---------- 空状态 ---------- */
.empty-docs {
  padding: 40px 0;
}
</style>

<!-- 关键词高亮（v-html 注入的 mark 不带 scoped 属性，需全局样式） -->
<style lang="scss">
.kb-view mark {
  background: #fdf3c9;
  color: #7a5b00;
  border-radius: 3px;
  padding: 0 2px;
}
</style>
