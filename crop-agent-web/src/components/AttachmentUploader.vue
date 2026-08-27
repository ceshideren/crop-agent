<script setup lang="ts">
import { ref } from 'vue'
import type { AttachmentItem } from '@/types'

/**
 * 多模态附件选择器：图片缩略图 + 普通文件芯片，与文字同框换行展示（类千问）。
 * 状态完全由父级 v-model 控制 —— 发送后父级清空列表即清空提问框。
 */
const props = defineProps<{ modelValue: AttachmentItem[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: AttachmentItem[]): void }>()

const MAX_IMG_BYTES = 10 * 1024 * 1024
const MAX_FILE_BYTES = 20 * 1024 * 1024
const MAX_DIM = 1024
const tip = ref('')

const ACCEPT =
  'image/png,image/jpeg,image/webp,.pdf,.doc,.docx,.xls,.xlsx,.md,.txt,.csv,.log'

function readAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

/** 前端压缩：超过 1024px 或 1MB 时缩放并转 JPEG。 */
async function compress(file: File): Promise<string> {
  const raw = await readAsDataURL(file)
  const img = await loadImage(raw)
  const { width, height } = img
  const needScale = Math.max(width, height) > MAX_DIM
  if (!needScale && file.size <= 1024 * 1024) return raw
  const scale = Math.min(1, MAX_DIM / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(width * scale)
  canvas.height = Math.round(height * scale)
  canvas.getContext('2d')!.drawImage(img, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.85)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

async function onSelect(ev: Event) {
  tip.value = ''
  const input = ev.target as HTMLInputElement
  const list = input.files
  if (!list) return
  const next: AttachmentItem[] = [...props.modelValue]
  for (const f of Array.from(list)) {
    if (f.type.startsWith('image/')) {
      if (!/image\/(png|jpe?g|webp)/.test(f.type)) {
        tip.value = '图片仅支持 JPG / PNG / WebP'
        continue
      }
      if (f.size > MAX_IMG_BYTES) {
        tip.value = '图片不能超过 10MB'
        continue
      }
      try {
        next.push({ kind: 'image', name: f.name, url: await compress(f), size: f.size })
      } catch {
        tip.value = '图片读取失败'
      }
    } else {
      if (f.size > MAX_FILE_BYTES) {
        tip.value = '文件不能超过 20MB'
        continue
      }
      try {
        next.push({
          kind: 'file',
          name: f.name,
          mime: f.type || 'application/octet-stream',
          data: await readAsDataURL(f),
          size: f.size,
        })
      } catch {
        tip.value = '文件读取失败'
      }
    }
  }
  emit('update:modelValue', next)
  input.value = ''
}

function remove(i: number) {
  const next = props.modelValue.filter((_, idx) => idx !== i)
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="attachment-uploader">
    <div class="attachments">
      <div v-for="(a, i) in modelValue" :key="`${a.kind}-${i}`" class="att" :class="a.kind">
        <img v-if="a.kind === 'image'" :src="a.url" :alt="a.name" class="att-img" />
        <span v-else class="file-chip" :title="a.name">
          <el-icon class="file-ico"><Document /></el-icon>
          <span class="file-name">{{ a.name }}</span>
          <span v-if="a.size" class="file-size">{{ formatSize(a.size) }}</span>
        </span>
        <button class="remove" :aria-label="`移除${a.name}`" @click="remove(i)">×</button>
      </div>
      <label class="upload-btn" title="添加图片或文件">
        <el-icon><Plus /></el-icon>
        <input
          type="file"
          :accept="ACCEPT"
          multiple
          hidden
          @change="onSelect"
        />
      </label>
    </div>
    <p v-if="tip" class="tip">{{ tip }}</p>
  </div>
</template>

<style scoped lang="scss">
.attachment-uploader {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.attachments {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.att {
  position: relative;
  flex: 0 0 auto;
}

/* 图片缩略图 */
.att-img {
  width: 52px;
  height: 52px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid #e3e8de;
  display: block;
}

/* 普通文件芯片 */
.file-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 200px;
  padding: 6px 10px 6px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid #dde6d8;
  background: #f4f8f1;
  color: #4c5a48;
  font-size: 12.5px;

  .file-ico {
    color: var(--crop-green);
    font-size: 15px;
    flex: 0 0 auto;
  }

  .file-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 120px;
  }

  .file-size {
    color: #9aa892;
    font-size: 11px;
    flex: 0 0 auto;
  }

  .remove {
    top: -6px;
    right: -4px;
  }
}

/* 移除按钮 */
.remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: var(--crop-error);
  color: #fff;
  cursor: pointer;
  line-height: 1;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

/* 添加按钮 */
.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px dashed #c4d4bd;
  background: transparent;
  color: var(--crop-green);
  cursor: pointer;
  font-size: 16px;
  transition: all 150ms var(--ease);

  &:hover {
    background: #f2f8ef;
    border-color: var(--crop-green);
  }
}

.tip {
  margin: 0;
  font-size: 12px;
  color: var(--crop-error);
}
</style>
