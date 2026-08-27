<script setup lang="ts">
/**
 * 分组详情页（需求：分组详情页交互重构）
 *  - 点击侧边栏「对话分组」→ 主内容区渲染本页，列表/卡片展示组内全部对话
 *  - 顶部搜索框：按对话名称实时模糊过滤
 *  - 「新建对话」入口已移除：新对话只在历史记录创建，之后通过「操作」菜单移入本组
 *  - 支持批量管理：勾选/全选 → 批量删除、移动到其它分组、移出分组（回历史记录）
 * 数据直接响应 chat store（sessions / groups），增删改（移入/移出/删除/重命名）
 * 经 loadSessions() 后自动刷新，无需本地维护副本。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { useHistoryManager } from '@/composables/useHistoryManager'
import { useBatchSelection } from '@/composables/useBatchSelection'
import SessionActionMenu from '@/components/SessionActionMenu.vue'
import BatchActionBar from '@/components/BatchActionBar.vue'

const route = useRoute()
const router = useRouter()
const store = useChatStore()
const { onRenameGroup, onDeleteGroup } = useHistoryManager() // 复用侧边栏同名能力

// 批量管理状态（详情页内独立于历史区）
const { batchMode, selected, count, isSelected, toggle, toggleAll, clear, exit } =
  useBatchSelection()

const keyword = ref('') // 搜索关键词
const gid = computed(() => Number(route.params.id))
const group = computed(() => store.groups.find((g) => g.id === gid.value))

/** 分组内会话：非置顶（置顶会话在「置顶」区展示）；store 已按创建时间倒序 */
const items = computed(() =>
  store.sessions.filter((s) => !s.pinned && s.group_id === gid.value),
)

/** 需求一：按对话名称实时模糊过滤（大小写不敏感 + 包含匹配） */
const filteredItems = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return items.value
  return items.value.filter((s) => (s.title || '').toLowerCase().includes(kw))
})

/** 批量移动目标分组：排除当前分组（本组会话无需再移入本组） */
const moveGroups = computed(() => store.groups.filter((g) => g.id !== gid.value))

/** 分组不存在 / 已被删除 → 兜底态 */
const missing = computed(() => !group.value)

function onOpenSession(id: string) {
  router.push({ path: '/chat', query: { session: id } }) // 与侧边栏一致
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/chat')
}

/** 切换分组时清空搜索词 */
watch(
  () => route.params.id,
  () => {
    keyword.value = ''
  },
)

// ---------- 批量管理 ----------
/** 全选范围 = 当前过滤后的结果（批量与搜索可并存） */
const viewIds = computed(() => filteredItems.value.map((s) => s.session_id))

const allSelected = computed(
  () => viewIds.value.length > 0 && viewIds.value.every((id) => isSelected(id)),
)

function onBatchSelectAll() {
  toggleAll(viewIds.value)
}

async function onBatchDelete() {
  const ids = [...selected.value]
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 个对话吗？此操作不可撤销。`,
      '批量删除对话',
      {
        confirmButtonText: '批量删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return // 用户取消：留在批量模式
  }
  await store.batchDelete(ids)
  exit()
}

async function onBatchMove(groupId: number | null) {
  const ids = [...selected.value]
  if (!ids.length) return
  await store.assignSessions(ids, groupId)
  exit()
}
</script>

<template>
  <div class="group-detail">
    <!-- 页头：返回 / 分组名 + 会话数 / 分组操作 + 批量入口 -->
    <header class="gd-head">
      <button class="gd-back" title="返回" @click="goBack">
        <el-icon><Back /></el-icon>
      </button>
      <div class="gd-title">
        <h1>{{ group?.name ?? '分组详情' }}</h1>
        <span class="gd-count num">{{ items.length }} 个对话</span>
      </div>
      <div v-if="group" class="gd-actions">
        <button class="gd-btn" title="重命名分组" @click="onRenameGroup(gid)">
          <el-icon><EditPen /></el-icon><span>重命名</span>
        </button>
        <button class="gd-btn danger" title="删除分组" @click="onDeleteGroup(gid)">
          <el-icon><Delete /></el-icon><span>删除</span>
        </button>
        <button
          class="gd-btn"
          :class="{ 'is-active': batchMode }"
          title="批量管理"
          @click="batchMode = !batchMode"
        >
          <el-icon><Finished /></el-icon><span>批量</span>
        </button>
      </div>
    </header>

    <!-- 搜索框：输入关键词实时过滤 -->
    <div class="gd-search">
      <el-input v-model="keyword" placeholder="搜索对话" clearable>
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 会话列表 / 空态 -->
    <div
      v-loading="store.sessionsLoading"
      element-loading-background="rgba(255,255,255,0.7)"
      class="gd-list"
    >
      <div v-if="missing" class="gd-empty">分组不存在或已被删除</div>
      <div v-else-if="!filteredItems.length" class="gd-empty">
        {{
          keyword.trim()
            ? `未找到与「${keyword.trim()}」相关的对话`
            : '暂无对话，可在历史记录新建对话后，通过「操作」菜单移入本组'
        }}
      </div>

      <div
        v-for="s in filteredItems"
        :key="s.session_id"
        class="gd-item"
        :class="{
          active: !batchMode && s.session_id === store.activeSessionId,
          selected: batchMode && isSelected(s.session_id),
        }"
        :title="s.title"
        @click="batchMode ? toggle(s.session_id) : onOpenSession(s.session_id)"
      >
        <span
          v-if="batchMode"
          class="batch-check"
          :class="{ checked: isSelected(s.session_id) }"
        >
          <el-icon v-if="isSelected(s.session_id)"><Check /></el-icon>
        </span>
        <span class="gd-ico">
          <el-icon><ChatDotRound /></el-icon>
        </span>
        <div class="gd-main">
          <div class="gd-name">{{ s.title }}</div>
          <div class="gd-meta">
            <span v-if="s.message_count === 0" class="gd-tag">未使用</span>
            <span class="gd-msg">{{ s.message_count ?? 0 }} 条消息</span>
          </div>
        </div>
        <!-- 单条对话操作：重命名 / 置顶 / 移动分组（含移出）/ 删除（批量模式下隐藏） -->
        <SessionActionMenu v-if="!batchMode" :session="s" />
      </div>
    </div>

    <!-- 批量操作栏：全选 / 移动到其它分组 / 移出分组 / 批量删除 / 完成 -->
    <BatchActionBar
      v-if="batchMode"
      :count="count"
      :groups="moveGroups"
      :show-ungroup="true"
      :all-selected="allSelected"
      class="gd-batch"
      @select-all="onBatchSelectAll"
      @clear="clear"
      @delete="onBatchDelete"
      @move="onBatchMove"
      @done="exit"
    />
  </div>
</template>

<style scoped lang="scss">
.group-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ---------- 页头 ---------- */
.gd-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #eef1ea;
  flex: 0 0 auto;
}

.gd-back {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: #f2f5ef;
  color: #5c6b57;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: #e8f3e4;
    color: var(--crop-green);
  }
}

.gd-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex: 1;
  min-width: 0;

  h1 {
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.gd-count {
  font-size: 12px;
  color: #9aa892;
  background: #f2f5ef;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  flex: 0 0 auto;
}

.gd-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.gd-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border: 1px solid #dde6d8;
  border-radius: 8px;
  background: #fff;
  color: #3c4a3a;
  font-size: 13px;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: #f2f8ef;
    border-color: #bfd8b6;
    color: var(--crop-green);
  }

  &.danger:hover {
    background: #fdeceb;
    border-color: #ecc8c5;
    color: var(--crop-error);
  }

  &.is-active {
    background: #eaf3e5;
    border-color: #bfd8b6;
    color: #2e7a2a;
    font-weight: 600;
  }
}

/* ---------- 搜索框 ---------- */
.gd-search {
  padding: 14px 24px 4px;
  flex: 0 0 auto;

  :deep(.el-input__wrapper) {
    border-radius: 10px;
    box-shadow: 0 0 0 1px #e3e8de inset;
    background: #fff;
  }
}

/* ---------- 会话列表 ---------- */
.gd-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gd-empty {
  text-align: center;
  color: #a9b5a3;
  font-size: 13px;
  padding: 48px 8px;
}

.gd-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid #eef1ea;
  cursor: pointer;
  transition: all 150ms var(--ease);

  &:hover {
    background: #f4f8f1;
    border-color: #dde6d8;
  }

  &.active {
    background: #eaf3e5;
    border-color: #bfd8b6;
  }

  /* 批量模式下选中高亮 */
  &.selected {
    background: #eaf3e5;
    border-color: #bfd8b6;
  }

  /* 批量模式复选框 */
  .batch-check {
    width: 18px;
    height: 18px;
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1.5px solid #c4d0bd;
    border-radius: 5px;
    background: #fff;
    color: #fff;
    font-size: 12px;
    transition: all 120ms var(--ease);

    &.checked {
      background: var(--crop-green);
      border-color: var(--crop-green);
    }
  }

  .gd-ico {
    color: #a5b59e;
    font-size: 18px;
    flex: 0 0 auto;
    display: flex;
    align-items: center;
  }

  .gd-main {
    flex: 1;
    min-width: 0;
  }

  .gd-name {
    font-size: 14px;
    line-height: 1.5;
    color: #3d493b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .gd-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 2px;
  }

  .gd-tag {
    font-size: 11px;
    color: #b8860b;
    background: #fdf6e3;
    border-radius: var(--radius-pill);
    padding: 1px 8px;
  }

  .gd-msg {
    font-size: 12px;
    color: #a9b5a3;
  }
}

/* ---------- 批量操作栏 ---------- */
.gd-batch {
  flex: 0 0 auto;
  margin: 0 24px 16px;
}
</style>
