<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import MessageBubble from '@/components/MessageBubble.vue'
import AttachmentUploader from '@/components/AttachmentUploader.vue'
import type { AttachmentItem } from '@/types'

const route = useRoute()
const router = useRouter()
const store = useChatStore()

const inputText = ref('')
const attachments = ref<AttachmentItem[]>([])
const scrollRef = ref<HTMLElement>()

const quickCommands = [
  '水稻稻瘟病怎么防治？',
  '番茄早疫病有什么症状？',
  '小麦如何施肥？',
  '番茄适宜什么气候种植？',
  '水稻和小麦哪个产量高？',
]

/** 提示词6：新消息到达自动滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    scrollRef.value?.scrollTo({
      top: scrollRef.value.scrollHeight,
      behavior: 'smooth',
    })
  })
}

watch(
  () => store.messages,
  () => scrollToBottom(),
  { deep: true },
)

function snapshotAttachments() {
  return {
    images: attachments.value
      .filter((a) => a.kind === 'image' && a.url)
      .map((a) => a.url as string),
    files: attachments.value
      .filter((a) => a.kind === 'file' && a.data)
      .map((a) => ({ name: a.name, mime: a.mime || '', data: a.data as string })),
  }
}

/** 发送后清空提问框（文字 + 图片 + 文件），附件随消息一并提交 */
async function onSend() {
  if (store.isStreaming) return
  const text = inputText.value
  const att = snapshotAttachments()
  if (!text.trim() && att.images.length === 0 && att.files.length === 0) return
  inputText.value = ''
  attachments.value = []
  await store.send(text, att)
}

/** 提示词2：新建对话 → 清空上下文 + 欢迎页（header 快捷入口；空对话阻断在 store 内） */
async function onNewChat() {
  const ok = await store.newChat()
  if (ok) router.replace({ path: '/chat' })
}

/** 提示词6：失败重试 */
function onRetry() {
  store.retry()
}

function onQuick(cmd: string) {
  inputText.value = cmd
  onSend()
}

onMounted(() => {
  const s = route.query.session as string | undefined
  if (s) store.switchSession(s)
})

watch(
  () => route.query.session,
  (s) => {
    if (s && typeof s === 'string') store.switchSession(s)
  },
)
</script>

<template>
  <div class="chat-view">
    <header class="chat-header">
      <div class="chat-title">
        <h1>对话</h1>
        <span v-if="store.activeSessionId" class="session-badge num">{{
          store.activeSessionId.slice(0, 8)
        }}</span>
      </div>
      <!-- <el-button text @click="onNewChat">
        <el-icon><EditPen /></el-icon>&nbsp;新建对话
      </el-button> -->
    </header>

    <div v-if="store.isStreaming" class="grow-bar" aria-label="正在生成"></div>

    <div ref="scrollRef" class="message-scroll">
      <div class="message-list">
        <!-- 空状态：种子等待发芽欢迎页（提示词2） -->
        <div v-if="!store.messages.length" class="empty-state">
          <div class="seed">🌱</div>
          <p class="empty-title">种子等待发芽</p>
          <p class="empty-sub">问我作物的识别、种植、病虫害，或上传一张照片 / 一份文档试试</p>
          <div class="quick-list">
            <button
              v-for="cmd in quickCommands"
              :key="cmd"
              class="chip"
              @click="onQuick(cmd)"
            >
              {{ cmd }}
            </button>
          </div>
        </div>

        <MessageBubble
          v-for="m in store.messages"
          :key="m.id"
          :message="m"
          @retry="onRetry"
        />
      </div>
    </div>

    <footer class="composer">
      <!-- 提示词6：错误提示 + 重试 -->
      <div v-if="store.error" class="composer-error">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ store.error }}</span>
        <button class="retry-link" @click="onRetry">重试</button>
      </div>
      <div class="composer-box">
        <!-- 多模态附件：图片/文件与文字同框，自动换行（类千问） -->
        <AttachmentUploader v-model="attachments" />
        <div class="composer-main">
          <textarea
            v-model="inputText"
            class="composer-input"
            rows="1"
            placeholder="输入你的问题，例如：番茄叶片有黑斑是什么病？"
            @keydown.enter.exact.prevent="onSend"
          ></textarea>
          <button
            class="send-btn"
            :disabled="store.isStreaming || (!inputText.trim() && !attachments.length)"
            aria-label="发送"
            @click="onSend"
          >
            <el-icon><Promotion /></el-icon>
          </button>
        </div>
      </div>
      <p class="composer-hint">
        Enter 发送 · Shift+Enter 换行 · 支持图片 JPG/PNG/WebP ≤10MB，文件 PDF/Word/Excel/文本 ≤20MB
      </p>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  background: #fff;
  border-bottom: 1px solid #eef1ea;
}

.chat-title {
  display: flex;
  align-items: baseline;
  gap: 10px;

  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: 700;
  }
}

.session-badge {
  font-size: 12px;
  color: #9aa892;
  background: #f2f5ef;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
}

.message-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 16px;
}

.message-list {
  max-width: 860px;
  margin: 0 auto;
  padding: 12px 0 24px;
}

.empty-state {
  text-align: center;
  padding: 64px 16px;
}

.seed {
  font-size: 56px;
  animation: seed-sway 3s ease-in-out infinite;
  transform-origin: bottom center;
  display: inline-block;
}

@keyframes seed-sway {
  0%,
  100% {
    transform: rotate(-6deg);
  }
  50% {
    transform: rotate(6deg);
  }
}

.empty-title {
  font-size: 22px;
  font-weight: 600;
  margin: 12px 0 4px;
}

.empty-sub {
  color: #8a9785;
  margin: 0 0 20px;
}

.quick-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  max-width: 560px;
  margin: 0 auto;
}

.composer {
  padding: 12px 16px 16px;
  background: #fff;
  border-top: 1px solid #eef1ea;
}

.composer-error {
  max-width: 860px;
  margin: 0 auto 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--crop-error);
}

.retry-link {
  border: 1px solid #ecc8c5;
  background: #fff;
  color: var(--crop-error);
  border-radius: var(--radius-pill);
  padding: 1px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: var(--crop-error);
    color: #fff;
  }
}

/* 提问框：附件与文字同框（纵向布局，附件区自动换行） */
.composer-box {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg-page);
  border: 1px solid #e3e8de;
  border-radius: var(--radius-card);
  padding: 10px 12px;
  transition: border-color 150ms var(--ease), box-shadow 150ms var(--ease);

  &:focus-within {
    border-color: var(--crop-green);
    box-shadow: 0 0 0 3px rgba(61, 139, 55, 0.12);
  }
}

.composer-main {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.composer-input {
  flex: 1;
  min-height: 44px;
  max-height: 140px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  font-size: 16px;
  font-family: inherit;
  line-height: 1.6;
  padding: 8px 4px;
}

.send-btn {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: var(--crop-green);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: all 150ms var(--ease);

  &:hover:not(:disabled) {
    background: #316f2c;
    transform: translateY(-1px);
  }

  &:disabled {
    background: #b7c6b1;
    cursor: not-allowed;
  }
}

.composer-hint {
  max-width: 860px;
  margin: 8px auto 0;
  font-size: 12px;
  color: #a9b5a3;
  text-align: center;
}
</style>
