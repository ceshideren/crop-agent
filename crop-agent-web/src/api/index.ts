import axios from 'axios'
import type { ApiResponse, AttachedFile } from '@/types'

const http = axios.create({
  baseURL: '/',
  timeout: 60000,
})

export const api = {
  chat(content: string, sessionId: string | null) {
    return http.post<ApiResponse>('/api/chat', { content, session_id: sessionId })
  },
  chatMultimodal(
    content: string,
    images: string[],
    files: AttachedFile[],
    sessionId: string | null,
  ) {
    return http.post<ApiResponse>('/api/chat/multimodal', {
      content,
      images,
      files,
      session_id: sessionId,
    })
  },
  getHistory(sessionId: string) {
    return http.get<ApiResponse>('/api/chat/history', {
      params: { session_id: sessionId },
    })
  },
  getSessions() {
    return http.get<ApiResponse>('/api/sessions')
  },
  createSession(groupId?: number) {
    // group_id 为 undefined 时 axios 序列化自动省略，兼容旧调用
    return http.post<ApiResponse>('/api/sessions', { group_id: groupId })
  },
  deleteSession(sessionId: string) {
    return http.delete<ApiResponse>(`/api/sessions/${sessionId}`)
  },
  updateSession(
    sessionId: string,
    payload: { title?: string; pinned?: boolean },
  ) {
    return http.patch<ApiResponse>(`/api/sessions/${sessionId}`, payload)
  },
  batchDeleteSessions(sessionIds: string[]) {
    return http.post<ApiResponse>('/api/sessions/batch-delete', {
      session_ids: sessionIds,
    })
  },
  createGroup(name: string) {
    return http.post<ApiResponse>('/api/groups', { name })
  },
  renameGroup(groupId: number, name: string) {
    return http.patch<ApiResponse>(`/api/groups/${groupId}`, { name })
  },
  deleteGroup(groupId: number) {
    return http.delete<ApiResponse>(`/api/groups/${groupId}`)
  },
  batchDeleteGroups(groupIds: number[]) {
    return http.post<ApiResponse>('/api/groups/batch-delete', {
      group_ids: groupIds,
    })
  },
  assignSessions(sessionIds: string[], groupId: number | null) {
    return http.post<ApiResponse>('/api/sessions/assign-group', {
      session_ids: sessionIds,
      group_id: groupId,
    })
  },
  searchKnowledge(q: string, category?: string) {
    return http.get<ApiResponse>('/api/knowledge/search', {
      params: { q, category: category || undefined },
    })
  },
  listKnowledge() {
    return http.get<ApiResponse>('/api/knowledge')
  },
  uploadKnowledge(file: File, onProgress?: (percent: number) => void) {
    const fd = new FormData()
    fd.append('file', file)
    return http.post<ApiResponse>('/api/knowledge/upload', fd, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)))
        }
      },
    })
  },
  getDocChunks(docId: string) {
    return http.get<ApiResponse>(`/api/knowledge/${docId}/chunks`)
  },
  getDocContent(docId: string) {
    return http.get<ApiResponse>(`/api/knowledge/${docId}/content`)
  },
  deleteKnowledge(docId: string) {
    return http.delete<ApiResponse>(`/api/knowledge/${docId}`)
  },
  reindexKnowledge(docId: string) {
    return http.post<ApiResponse>(`/api/knowledge/${docId}/reindex`)
  },
  batchDeleteKnowledge(docIds: string[]) {
    return http.post<ApiResponse>('/api/knowledge/batch-delete', { doc_ids: docIds })
  },
  batchReindexKnowledge(docIds: string[]) {
    return http.post<ApiResponse>('/api/knowledge/batch-reindex', { doc_ids: docIds })
  },
  deleteChunk(chunkId: string) {
    return http.delete<ApiResponse>(`/api/knowledge/chunks/${chunkId}`)
  },
}
