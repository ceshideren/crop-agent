/**
 * 全局会话状态（Pinia）—— 提示词5：会话独立性
 * - 每个 Session ID 对应独立的消息列表与上下文窗口
 * - 切换会话 = 彻底切换数据源，发送只追加到当前激活会话
 * - 侧边栏收起状态持久化到 localStorage（提示词1）
 */
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { useWebSocket } from '@/composables/useWebSocket'
import type { AttachedFile, ChatMessage, SessionGroup, SessionItem } from '@/types'

const SIDEBAR_KEY = 'hezhi:sidebar-collapsed'

/** 一次发送携带的全部附件。 */
export interface SendAttachments {
  images?: string[]
  files?: AttachedFile[]
}

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

export const useChatStore = defineStore('chat', () => {
  // ---------- 会话与消息 ----------
  const activeSessionId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const sessions = ref<SessionItem[]>([])
  const groups = ref<SessionGroup[]>([])
  const sessionsLoading = ref(false)
  const isStreaming = ref(false)
  const error = ref('')
  const lastQuery = ref<{ content: string; attachments: SendAttachments } | null>(null)

  // ---------- 侧边栏 UI 状态（提示词1）----------
  const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
  const mobileSidebarOpen = ref(false)

  const ws = useWebSocket()

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed.value ? '1' : '0')
  }

  // ---------- 历史会话列表（提示词4）----------
  /** 置顶优先，其次按创建时间倒序（空时间为 0 排最后） */
  function sortSessions(list: SessionItem[]) {
    return [...list].sort((a, b) => {
      const pa = a.pinned ? 1 : 0
      const pb = b.pinned ? 1 : 0
      if (pa !== pb) return pb - pa
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return tb - ta
    })
  }

  async function loadSessions() {
    sessionsLoading.value = true
    try {
      const res = await api.getSessions()
      const data = res.data.data || {}
      sessions.value = sortSessions(data.sessions || [])
      groups.value = data.groups || []
    } catch {
      // 静默失败：保留旧列表，不打断交互
    } finally {
      sessionsLoading.value = false
    }
  }

  // ---------- 加载单个会话的消息（提示词5）----------
  async function loadSession(id: string) {
    activeSessionId.value = id
    error.value = ''
    try {
      const res = await api.getHistory(id)
      const list = res.data.data.messages || []
      messages.value = list.map((m: any, i: number) => ({
        id: `${m.id ?? i}`,
        role: m.role,
        content: m.content,
        images: m.image_urls || [],
        sources: [],
        streaming: false,
        timestamp: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
      }))
    } catch {
      messages.value = []
      error.value = '加载历史会话失败'
    }
  }

  /** 切换到另一个会话：彻底替换消息列表 */
  async function switchSession(id: string) {
    if (isStreaming.value) {
      ElMessage.info('正在生成回答，请稍候再切换')
      return
    }
    if (id === activeSessionId.value) return
    await loadSession(id)
  }

  // ---------- 新建对话（提示词2 / 需求3&4 / 空对话复用规则）----------
  /**
   * 新建对话（类似千问的模式）：
   *  - 新建对话只落在历史记录（未分组），不会创建到分组内；
   *  - 历史记录存在空对话（message_count === 0 且未分组）时：
   *      · 第一次点「新建对话」→ 复用该空对话（进入它，不新增条目）；
   *      · 已被复用过的同一空对话再次触发 → 禁止新建并提示
   *        「已存在未使用的空对话，请先使用或清理后再新建」（grouping 防叠加）；
   *  - 空对话被使用（发出首条消息）/ 删除 / 移入分组后，lastReusedEmptyId 自然失效，
   *    之后可再次正常新建；
   *  - creatingSession 防重入：单次操作内最多处理一次，不重复弹窗、不重复请求。
   * 任一成功路径返回 true，由调用方负责跳转到对话页。
   */
  const creatingSession = ref(false)
  const lastReusedEmptyId = ref<string | null>(null)

  async function newChat(): Promise<boolean> {
    if (creatingSession.value) return false // 防重复触发：同一操作只处理一次
    if (isStreaming.value) {
      ElMessage.info({ message: '正在生成回答，请稍候再新建', grouping: true })
      return false
    }
    creatingSession.value = true
    try {
      // 历史记录里的空对话（未分组、0 消息）
      const empty = sessions.value.find(
        (s) => s.message_count === 0 && s.group_id == null,
      )
      if (empty) {
        // 该空对话已被复用过一次且仍为空 → 禁止新建
        if (empty.session_id === lastReusedEmptyId.value) {
          ElMessage.warning({
            message: '已存在未使用的空对话，请先使用或清理后再新建',
            grouping: true, // 连点不叠加弹窗
            // showClose:true,
          })
          return false // 禁止创建，不跳转
        }
        // 第一次：复用已有空对话（不新增条目）
        messages.value = []
        error.value = ''
        lastQuery.value = null
        activeSessionId.value = empty.session_id
        lastReusedEmptyId.value = empty.session_id // 标记已复用
        await loadSessions()
        return true
      }
      // 无空对话 → 创建新的空白会话（落在历史记录，不归属任何分组）
      lastReusedEmptyId.value = null
      messages.value = []
      error.value = ''
      lastQuery.value = null
      activeSessionId.value = null // 立即进入空白状态（种子等待发芽欢迎页）
      try {
        const res = await api.createSession()
        activeSessionId.value = res.data.data.session_id
        await loadSessions()
      } catch {
        // 后端不可用：保持本地空白态，首条消息会自动创建会话
      }
      return true
    } finally {
      creatingSession.value = false
    }
  }

  // ---------- 删除会话（提示词3：二次确认在组件层）----------
  async function deleteSession(id: string) {
    try {
      await api.deleteSession(id)
    } catch {
      ElMessage.error('删除失败，请重试')
      return
    }
    sessions.value = sessions.value.filter((s) => s.session_id !== id)
    if (id === activeSessionId.value) {
      activeSessionId.value = null
      messages.value = []
      error.value = ''
      lastQuery.value = null
      if (sessions.value.length) {
        // 跳转到最新一条历史会话（置顶优先）
        await loadSession(sessions.value[0].session_id)
      }
      // 没有剩余会话 → 停留在空白欢迎页
    }
  }

  // ---------- 重命名会话 ----------
  async function renameSession(id: string, title: string) {
    const name = (title || '').trim()
    if (!name) return
    try {
      const res = await api.updateSession(id, { title: name })
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '重命名失败，请重试')
        return
      }
    } catch {
      ElMessage.error('重命名失败，请重试')
      return
    }
    const s = sessions.value.find((x) => x.session_id === id)
    if (s) s.title = name
  }

  // ---------- 置顶 / 取消置顶 ----------
  async function togglePin(id: string) {
    const s = sessions.value.find((x) => x.session_id === id)
    if (!s) return
    const next = !s.pinned
    try {
      const res = await api.updateSession(id, { pinned: next })
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || (next ? '置顶失败，请重试' : '取消置顶失败，请重试'))
        return
      }
    } catch {
      ElMessage.error(next ? '置顶失败，请重试' : '取消置顶失败，请重试')
      return
    }
    s.pinned = next
    sessions.value = sortSessions(sessions.value)
  }

  // ---------- 批量删除会话 ----------
  async function batchDelete(ids: string[]) {
    const list = [...new Set(ids)]
    if (!list.length) return
    try {
      const res = await api.batchDeleteSessions(list)
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '批量删除失败，请重试')
        return
      }
    } catch {
      ElMessage.error('批量删除失败，请重试')
      return
    }
    const removed = new Set(list)
    sessions.value = sessions.value.filter((s) => !removed.has(s.session_id))
    if (activeSessionId.value && removed.has(activeSessionId.value)) {
      activeSessionId.value = null
      messages.value = []
      error.value = ''
      lastQuery.value = null
      if (sessions.value.length) {
        await loadSession(sessions.value[0].session_id)
      }
    }
  }

  // ---------- 自定义分组（历史对话分组）----------
  async function createGroup(name: string) {
    const trimmed = (name || '').trim()
    if (!trimmed) return false
    try {
      const res = await api.createGroup(trimmed)
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '创建分组失败，请重试')
        return false
      }
    } catch {
      ElMessage.error('创建分组失败，请重试')
      return false
    }
    await loadSessions()
    return true
  }

  async function renameGroup(id: number, name: string) {
    const trimmed = (name || '').trim()
    if (!trimmed) return
    try {
      const res = await api.renameGroup(id, trimmed)
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '重命名分组失败，请重试')
        return
      }
    } catch {
      ElMessage.error('重命名分组失败，请重试')
      return
    }
    const g = groups.value.find((x) => x.id === id)
    if (g) g.name = trimmed
  }

  /** 批量删除分组：分组内会话自动释放回日期区（原始顺序）。 */
  async function deleteGroups(ids: number[]) {
    const list = [...new Set(ids)]
    if (!list.length) return
    try {
      const res = await api.batchDeleteGroups(list)
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '删除分组失败，请重试')
        return
      }
    } catch {
      ElMessage.error('删除分组失败，请重试')
      return
    }
    await loadSessions()
  }

  /** 批量把会话移入/移出分组（groupId 为 null 表示移出所有分组）。 */
  async function assignSessions(ids: string[], groupId: number | null) {
    const list = [...new Set(ids)]
    if (!list.length) return
    try {
      const res = await api.assignSessions(list, groupId)
      if (res.data.code !== 200) {
        ElMessage.error(res.data.message || '移动会话失败，请重试')
        return
      }
    } catch {
      ElMessage.error('移动会话失败，请重试')
      return
    }
    await loadSessions()
  }

  // ---------- 发送消息（提示词5/6）----------
  async function send(
    content: string,
    attachments: SendAttachments = {},
    opts: { silent?: boolean } = {},
  ) {
    content = (content || '').trim()
    const images = attachments.images || []
    const files = attachments.files || []
    if (!content && images.length === 0 && files.length === 0) return
    if (isStreaming.value) return
    error.value = ''
    lastQuery.value = { content, attachments: { images, files } }
    isStreaming.value = true

    // ⚠ 必须用 reactive() 创建消息对象，不能 push 普通对象：
    // 响应式数组 push 时会把元素包装成 Proxy 存入数组，但下方 WS 流式回调
    // 闭包持有的是原始对象引用——对原始对象的修改不经过 Proxy 的 set 陷阱，
    // 视图永远收不到更新（表现为"发送后无回答，切走再切回才显示"）。
    // 用 reactive() 创建后，闭包与数组内持有的是同一个 Proxy，修改即时生效。
    const userMsg: ChatMessage = reactive({
      id: uid(),
      role: 'user',
      content,
      images,
      streaming: false,
      timestamp: Date.now(),
    })
    const assistantMsg: ChatMessage = reactive({
      id: uid(),
      role: 'assistant',
      content: '',
      sources: [],
      streaming: true,
      timestamp: Date.now(),
    })
    // 重试时不再重复追加用户消息（silent）
    if (!opts.silent) messages.value.push(userMsg)
    messages.value.push(assistantMsg)

    const payload = { session_id: activeSessionId.value, content, images, files }

    try {
      await ws.send(payload, {
        onMeta: (meta) => {
          if (meta.session_id) activeSessionId.value = meta.session_id
          assistantMsg.sources = meta.sources || []
        },
        onDelta: (text) => {
          assistantMsg.content += text
        },
        onError: (msg) => {
          error.value = msg
        },
      })
    } catch {
      // 流式失败，走 REST 兜底
    }

    // 流式未产出内容 → REST 兜底
    if (assistantMsg.content === '') {
      try {
        const res =
          images.length || files.length
            ? await api.chatMultimodal(content, images, files, activeSessionId.value)
            : await api.chat(content, activeSessionId.value)
        const data = res.data.data || {}
        assistantMsg.content = data.reply || ''
        assistantMsg.sources = res.data.sources || []
        if (data.session_id) activeSessionId.value = data.session_id
        assistantMsg.animate = true // REST 全文 → 客户端打字机动画
        error.value = '' // 兜底成功，清除流式阶段的错误提示
      } catch {
        assistantMsg.failed = true
        error.value = '查询失败，请重试'
      }
    }

    assistantMsg.streaming = false
    isStreaming.value = false

    // 会话可能刚由后端创建，或标题从"新对话"更新为首轮提问 → 刷新列表
    const sess = sessions.value.find((s) => s.session_id === activeSessionId.value)
    if (sess && (!sess.title || sess.title === '新对话')) {
      sess.title = content.slice(0, 20)
    }
    loadSessions()
  }

  /** 重试最后一次失败的查询（提示词6） */
  async function retry() {
    if (!lastQuery.value || isStreaming.value) return
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.failed) {
      messages.value.pop()
    }
    error.value = ''
    await send(lastQuery.value.content, lastQuery.value.attachments, { silent: true })
  }

  return {
    activeSessionId,
    messages,
    sessions,
    groups,
    sessionsLoading,
    isStreaming,
    error,
    sidebarCollapsed,
    mobileSidebarOpen,
    toggleSidebar,
    loadSessions,
    loadSession,
    switchSession,
    newChat,
    deleteSession,
    renameSession,
    togglePin,
    batchDelete,
    createGroup,
    renameGroup,
    deleteGroups,
    assignSessions,
    send,
    retry,
  }
})
