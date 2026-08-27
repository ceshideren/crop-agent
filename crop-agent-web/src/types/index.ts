export interface Source {
  doc_id: string
  chunk: string
  score: number
}

export interface ApiResponse<T = any> {
  code: number
  data: T
  sources: Source[]
  message: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  sources?: Source[]
  streaming?: boolean
  animate?: boolean
  failed?: boolean
  timestamp: number
}

export interface SessionItem {
  session_id: string
  title: string
  crop_context?: string | null
  pinned?: boolean
  group_id?: number | null
  /** 会话内消息条数（后端统计；0 表示空对话，新建对话时会被复用） */
  message_count?: number
  created_at: string | null
}

export interface SessionGroup {
  id: number
  name: string
  created_at: string | null
}

/** 发送时携带的普通文件（base64 dataURL）。 */
export interface AttachedFile {
  name: string
  mime: string
  data: string
}

/** 提问框内待发送的附件（图片缩略图 / 文件芯片）。 */
export interface AttachmentItem {
  kind: 'image' | 'file'
  name: string
  url?: string // 图片 dataURL（缩略图展示）
  mime?: string // 文件 MIME
  data?: string // 文件 dataURL
  size?: number // 文件字节数
}

export interface KnowledgeDoc {
  doc_id: string
  title: string
  source?: string
  file_name?: string
  category?: string
  status?: string // indexed | indexing | failed
  chunk_count?: number
  file_size?: number
  format?: string // md | txt | docx | pptx
  created_at?: string | null
  updated_at?: string | null
}

/** 文档内容（预览页使用）：content 为按格式提取后的文本。 */
export interface DocContent {
  doc_id: string
  title: string
  source: string
  file_name: string
  category: string
  format: string // md | txt | docx | pptx
  content: string
}

/** 检索结果中的单个命中片段。 */
export interface SearchChunk {
  chunk_id: string
  chunk_index: number
  text: string
  score: number
}

/** 检索结果：文档级对象（同一文档的多个 chunk 已合并）。 */
export interface SearchResultDoc {
  doc_id: string
  title: string
  category: string
  source: string
  file_name: string
  status: string
  score: number
  chunks: SearchChunk[]
  updated_at?: string | null
  file_size?: number
  chunk_count?: number
}

/** 文档 chunk 明细（drawer 展示）。 */
export interface ChunkDetail {
  chunk_id: string
  chunk_index: number
  text: string
  char_count: number
}
