<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '@/types'
import StreamText from './StreamText.vue'
import SourceTag from './SourceTag.vue'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ (e: 'retry', message: ChatMessage): void }>()

const isUser = computed(() => props.message.role === 'user')
const thinking = computed(
  () => !isUser.value && props.message.streaming && !props.message.content,
)
</script>

<template>
  <div class="message-row" :class="isUser ? 'is-user' : 'is-agent'">
    <div class="avatar" :class="isUser ? 'avatar-user' : 'avatar-agent'">
      {{ isUser ? '农' : '🌾' }}
    </div>
    <div class="bubble-wrap">
      <div class="bubble" :class="isUser ? 'bubble-user' : 'bubble-agent'">
        <!-- 思考中 -->
        <div v-if="thinking" class="thinking-dots" aria-label="正在思考">
          <span></span><span></span><span></span>
        </div>

        <!-- 查询失败（提示词6：明确错误提示 + 重试按钮） -->
        <div v-else-if="message.failed" class="bubble-error">
          <el-icon><WarningFilled /></el-icon>
          <span>查询失败，请重试</span>
          <button class="retry-btn" @click="emit('retry', message)">重试</button>
        </div>

        <!-- 用户消息：纯文本 + 图片 -->
        <template v-else-if="isUser">
          <div v-if="message.images && message.images.length" class="user-images">
            <img
              v-for="(img, i) in message.images"
              :key="i"
              :src="img"
              alt="上传图片"
            />
          </div>
          <div v-if="message.content" class="user-text">{{ message.content }}</div>
        </template>

        <!-- Agent 消息：Markdown 渲染 -->
        <StreamText v-else :text="message.content" :animate="message.animate" />
      </div>

      <SourceTag
        v-if="!isUser && message.sources && message.sources.length"
        :sources="message.sources"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.message-row {
  display: flex;
  gap: 12px;
  margin: 14px 0;

  &.is-user {
    flex-direction: row-reverse;

    .bubble-wrap {
      align-items: flex-end;
    }
  }
}

.avatar {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  color: #fff;

  &.avatar-agent {
    background: linear-gradient(135deg, var(--crop-green), #5a9e54);
  }

  &.avatar-user {
    background: linear-gradient(135deg, var(--crop-gold), #d9a72b);
    color: #5a4310;
    font-size: 14px;
  }
}

.bubble-wrap {
  max-width: min(78%, 720px);
  display: flex;
  flex-direction: column;
}

.bubble {
  padding: 12px 16px;
  border-radius: var(--radius-card);
  line-height: 1.7;

  &.bubble-agent {
    background: #eff5ea;
    border-top-left-radius: var(--radius-sm);
    color: #2c332b;
  }

  &.bubble-user {
    background: var(--crop-green);
    color: #fff;
    border-top-right-radius: var(--radius-sm);
  }
}

.user-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.user-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;

  img {
    width: 84px;
    height: 84px;
    object-fit: cover;
    border-radius: var(--radius-sm);
    border: 2px solid rgba(255, 255, 255, 0.5);
  }
}

/* ---------- 失败气泡 ---------- */
.bubble-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--crop-error);
  font-size: 14px;
}

.retry-btn {
  border: 1px solid #ecc8c5;
  background: #fff;
  color: var(--crop-error);
  border-radius: var(--radius-pill);
  padding: 2px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: var(--crop-error);
    color: #fff;
  }
}
</style>
