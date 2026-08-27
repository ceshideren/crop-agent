<script setup lang="ts">
/**
 * 批量操作栏（历史区 / 分组详情页共用）：
 *  - 显示已选数量；全选/取消全选；移动到分组（Popover 列出分组，详情页可移出分组）；
 *  - 批量删除由父组件做二次确认；「完成」退出批量模式。
 */
import { ref } from 'vue'
import type { SessionGroup } from '@/types'

defineProps<{
  count: number
  groups: SessionGroup[]
  allSelected: boolean
  showUngroup?: boolean
}>()

const emit = defineEmits<{
  (e: 'select-all'): void
  (e: 'clear'): void
  (e: 'delete'): void
  (e: 'move', groupId: number | null): void
  (e: 'done'): void
}>()

const moveOpen = ref(false)

function pickGroup(gid: number | null) {
  moveOpen.value = false
  emit('move', gid)
}
</script>

<template>
  <div class="batch-bar">
    <span class="bb-count">已选 {{ count }} 项</span>
    <button type="button" class="bb-btn" @click="emit('select-all')">
      {{ allSelected ? '取消全选' : '全选' }}
    </button>

    <!-- 移动到分组 -->
    <div class="bb-move">
      <button
        type="button"
        class="bb-btn"
        :disabled="!count"
        title="移动到分组"
        @click="moveOpen = !moveOpen"
      >
        <el-icon><FolderOpened /></el-icon>
        <span>移动到分组</span>
      </button>
      <template v-if="moveOpen">
        <div class="bb-mask" @click="moveOpen = false"></div>
        <div class="bb-pop">
          <button
            v-for="g in groups"
            :key="g.id"
            type="button"
            class="bb-item"
            @click="pickGroup(g.id)"
          >
            <el-icon><Folder /></el-icon>
            <span class="bb-name">{{ g.name }}</span>
          </button>
          <button
            v-if="showUngroup"
            type="button"
            class="bb-item"
            @click="pickGroup(null)"
          >
            <el-icon><FolderDelete /></el-icon>
            <span>移出分组</span>
          </button>
          <div v-if="!groups.length && !showUngroup" class="bb-empty">暂无分组，请先在分组区新建</div>
        </div>
      </template>
    </div>

    <button
      type="button"
      class="bb-btn danger"
      :disabled="!count"
      title="批量删除"
      @click="emit('delete')"
    >
      <el-icon><Delete /></el-icon>
      <span>批量删除</span>
    </button>

    <button type="button" class="bb-btn done" @click="emit('done')">完成</button>
  </div>
</template>

<style scoped lang="scss">
.batch-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #e3e8de;
  border-radius: 10px;
  box-shadow: 0 -2px 12px rgba(31, 61, 29, 0.06);
  position: relative;
}

.bb-count {
  font-size: 12.5px;
  color: var(--crop-green);
  font-weight: 600;
  white-space: nowrap;
}

.bb-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  border: 1px solid #dde6d8;
  border-radius: 7px;
  background: #fff;
  color: #3c4a3a;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 150ms var(--ease);

  .el-icon {
    font-size: 13px;
  }

  &:hover:not(:disabled) {
    background: #f2f8ef;
    border-color: #bfd8b6;
    color: var(--crop-green);
  }

  &:disabled {
    color: #b7c6b1;
    border-color: #eef1ea;
    cursor: not-allowed;
  }

  &.danger:hover:not(:disabled) {
    background: #fdeceb;
    border-color: #ecc8c5;
    color: var(--crop-error);
  }

  &.done {
    border-color: transparent;
    background: #eaf3e5;
    color: #2e7a2a;
    font-weight: 600;

    &:hover {
      background: #dcecd5;
    }
  }
}

/* ---------- 移动到分组 Popover ---------- */
.bb-move {
  position: relative;
}

.bb-mask {
  position: fixed;
  inset: 0;
  z-index: 2999;
}

.bb-pop {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  z-index: 3000;
  min-width: 168px;
  max-width: 240px;
  padding: 5px;
  background: #fff;
  border: 1px solid #eef1ea;
  border-radius: 10px;
  box-shadow: 0 6px 24px rgba(31, 61, 29, 0.14), 0 2px 8px rgba(31, 61, 29, 0.08);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #3d493b;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  transition: background 120ms var(--ease);

  .el-icon {
    font-size: 14px;
    color: #7d8b77;
    flex: 0 0 auto;
  }

  &:hover {
    background: #f2f8ef;
    color: var(--crop-green);

    .el-icon {
      color: var(--crop-green);
    }
  }
}

.bb-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bb-empty {
  font-size: 12px;
  color: #a9b5a3;
  padding: 8px 10px;
}
</style>
