<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { useHistoryManager } from '@/composables/useHistoryManager'
import { useBatchSelection } from '@/composables/useBatchSelection'
import PinIcon from '@/components/PinIcon.vue'
import SessionActionMenu from '@/components/SessionActionMenu.vue'
import BatchActionBar from '@/components/BatchActionBar.vue'

const props = defineProps<{ nav: { path: string; label: string; icon: string }[] }>()

const route = useRoute()
const router = useRouter()
const store = useChatStore()

// 分组区与历史区并列：分组区 = 全部自定义分组（空分组也展示）；历史区 = 置顶 + 日期
const { groupSections, historySections, onCreateGroup, onRenameGroup, onDeleteGroup } =
  useHistoryManager()

// 历史区批量管理状态
const { batchMode, selected, count, isSelected, toggle, toggleAll, clear, exit } =
  useBatchSelection()

// 挂载时拉取历史会话 + 分区列表（复用 store 已有逻辑）
onMounted(() => store.loadSessions())

/**
 * 重构：桌面侧边栏只保留「知识库」两个目的地导航，
 * 过滤掉与顶部「新建对话」功能重叠的「对话」入口（App.vue 的 nav 不动，
 * 移动端底部 Tab 仍需「对话」）。
 */
const navItems = computed(() => props.nav.filter((item) => item.path == '/knowledge'))

// ---------- 分区折叠状态（历史分区仍可折叠；分组改为点击导航到详情页） ----------
const collapsed = ref<Set<string>>(new Set())

/** 分组行 → 右侧分组详情页（不在侧边栏内联展开子列表） */
function isGroupActive(gid: number) {
  return route.path === `/group/${gid}`
}
function openGroup(gid: number) {
  router.push(`/group/${gid}`)
  closeMobile()
}

/**
 * 新建对话 → 只落在历史记录：历史区有未复用的空对话则复用进入，
 * 否则创建新会话（空对话复用/禁止规则在 store.newChat 内）
 */
async function onNewChat() {
  const ok = await store.newChat()
  if (!ok) return
  if (route.path !== '/chat') router.push('/chat')
  closeMobile()
}

/** 点击历史会话 → 切换主聊天区数据源 */
function onOpenSession(id: string) {
  router.push({ path: '/chat', query: { session: id } })
  closeMobile()
}

function closeMobile() {
  store.mobileSidebarOpen = false
}

// ---------- 历史区批量管理 ----------
/** 历史区全部条目 id（置顶 + 日期区，即未分组会话） */
const historyIds = computed(() =>
  historySections.value.flatMap((sec) => sec.items.map((s) => s.session_id)),
)

const allHistorySelected = computed(
  () => historyIds.value.length > 0 && historyIds.value.every((id) => isSelected(id)),
)

function onBatchSelectAll() {
  toggleAll(historyIds.value)
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
  <aside
    class="sidebar"
    :class="{ collapsed: store.sidebarCollapsed, 'mobile-open': store.mobileSidebarOpen }"
  >
    <div class="brand">
      <span class="brand-logo">🌾</span>
      <div class="brand-text">
        <div class="brand-name">禾知</div>
        <div class="brand-sub">农作物智能助手</div>
      </div>
      <button class="sidebar-close" aria-label="关闭菜单" @click="closeMobile">
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <!-- 新建对话：高频操作 · Notion 式幽灵按钮（折叠态变主色 FAB） -->
    <button class="new-chat-btn" title="新建对话" @click="onNewChat">
      <el-icon><Plus /></el-icon>
      <span class="btn-text">新建对话</span>
    </button>

    <!-- 核心导航：知识库 / 历史对话 -->
    <nav class="nav" aria-label="主导航">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        active-class="active"
        :title="item.label"
        @click="closeMobile"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span class="nav-label">{{ item.label }}</span>
        <span v-if="item.path === '/knowledge'" class="nav-tag">核心</span>
      </router-link>
    </nav>

    <!-- 对话分组区：独立于历史对话，与「历史对话」区域并列；空分组也强制展示 -->
    <div class="groups">
      <div class="groups-head">
        <span class="groups-title">对话分组</span>
        <button class="head-btn" title="新建分组" @click="onCreateGroup">
          <el-icon><FolderAdd /></el-icon>
          <span class="btn-text">新建分组</span>
        </button>
      </div>

      <div class="groups-list">
        <div v-if="!groupSections.length" class="groups-empty">暂无分组，点击右上角新建</div>

        <!-- 分组导航项：点击进入右侧分组详情页（不在侧边栏内联展开） -->
        <div
          v-for="sec in groupSections"
          :key="sec.key"
          class="group-row"
          :class="{ active: isGroupActive(sec.groupId!) }"
          :title="sec.title"
          @click="openGroup(sec.groupId!)"
        >
          <el-icon class="group-ico"><Folder /></el-icon>
          <span class="group-name">{{ sec.title }}</span>
          <!-- <span class="sec-count num">{{ sec.items.length }}</span>
          <div class="sec-actions" @click.stop>
            <button class="act-btn" title="重命名分组" @click="onRenameGroup(sec.groupId!)">
              <el-icon><EditPen /></el-icon>
            </button>
            <button class="act-btn danger" title="删除分组" @click="onDeleteGroup(sec.groupId!)">
              <el-icon><Delete /></el-icon>
            </button>
          </div> -->
        </div>
      </div>
    </div>

    <!-- 历史对话区：置顶区 / 日期区（分组内的会话不在此重复展示） -->
    <div class="history">
      <div class="history-head">
        <span class="history-title">历史对话</span>
        <span v-if="store.sessions.length" class="history-count num">{{
          store.sessions.length
        }}</span>
        <button
          class="head-btn"
          :class="{ 'is-active': batchMode }"
          title="批量管理"
          @click="batchMode = !batchMode"
        >
          <el-icon><Finished /></el-icon>
          <span class="btn-text">批量</span>
        </button>
      </div>

      <div
        v-loading="store.sessionsLoading"
        element-loading-background="rgba(255,255,255,0.7)"
        class="history-list"
      >
        <div v-if="!store.sessions.length && !store.sessionsLoading" class="history-empty">
          暂无历史对话
        </div>

        <template v-for="sec in historySections" :key="sec.key">
          <!-- 分区头 -->
          <div class="sec-head">
            <span v-if="sec.kind === 'pinned'" class="sec-ico">
              <PinIcon :filled="true" />
            </span>
            <span class="sec-title">{{ sec.title }}</span>
            <span class="sec-count num">{{ sec.items.length }}</span>
          </div>

          <!-- 分区内会话 -->
          <div v-show="!collapsed.has(sec.key)" class="sec-items">
            <div
              v-for="s in sec.items"
              :key="s.session_id"
              class="history-item"
              :class="{
                active: !batchMode && s.session_id === store.activeSessionId,
                selected: batchMode && isSelected(s.session_id),
                'is-pinned': s.pinned,
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
              <span class="item-icon">
                <PinIcon v-if="s.pinned" :filled="true" />
                <el-icon v-else><ChatDotRound /></el-icon>
              </span>
              <div class="item-main">
                <div class="item-title-line">
                  <div class="item-title">{{ s.title }}</div>
                  <!-- 空对话文字提示（需求2） -->
                  <span v-if="s.message_count === 0" class="item-tag">未使用</span>
                </div>
              </div>
              <!-- 单条对话操作菜单：重命名 / 置顶 / 移动分组 / 删除（批量模式下隐藏） -->
              <SessionActionMenu v-if="!batchMode" :session="s" />
            </div>
          </div>
        </template>
      </div>

      <!-- 批量操作栏：全选 / 移动到分组 / 批量删除 / 完成 -->
      <BatchActionBar
        v-if="batchMode"
        :count="count"
        :groups="store.groups"
        :all-selected="allHistorySelected"
        class="history-batch"
        @select-all="onBatchSelectAll"
        @clear="clear"
        @delete="onBatchDelete"
        @move="onBatchMove"
        @done="exit"
      />
    </div>

    <div class="sidebar-foot">
      <button
        class="collapse-btn"
        :title="store.sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="store.toggleSidebar"
      >
        <el-icon>
          <component :is="store.sidebarCollapsed ? 'Expand' : 'Fold'" />
        </el-icon>
        <span v-if="!store.sidebarCollapsed" class="btn-text">收起侧边栏</span>
      </button>
      <div v-if="!store.sidebarCollapsed" class="foot-text">智慧农业 × AI Agent</div>
    </div>
  </aside>
</template>

<style scoped lang="scss">
.sidebar {
  width: 260px;
  flex: 0 0 auto;
  background: #fff;
  border-right: 1px solid #eef1ea;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 12px 14px;
  overflow: hidden;
  /* 平滑过渡动画 */
  transition: width 250ms var(--ease);

  &.collapsed {
    width: 76px;
  }

  /* ---------- 品牌 ---------- */
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 2px 8px 14px;
  }

  .brand-logo {
    font-size: 26px;
    line-height: 1;
  }

  .brand-name {
    font-size: 18px;
    font-weight: 700;
    color: var(--crop-green);
    line-height: 1.2;
  }

  .brand-sub {
    font-size: 11px;
    color: #9aa894;
  }

  .sidebar-close {
    display: none;
  }

  /* ---------- 新建对话：Notion 式幽灵按钮 ---------- */
  .new-chat-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 9px 12px;
    border: 1px solid #dde6d8;
    border-radius: 10px;
    background: #fff;
    color: #3c4a3a;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 150ms var(--ease);

    .el-icon {
      color: var(--crop-green);
      font-size: 16px;
      transition: transform 150ms var(--ease);
    }

    &:hover {
      background: #f2f8ef;
      border-color: #bfd8b6;
      color: var(--crop-green);

      .el-icon {
        transform: rotate(90deg);
      }
    }
  }

  /* ---------- 核心导航 ---------- */
  .nav {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 4px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: 10px;
    color: #55614f;
    text-decoration: none;
    font-size: 14px;
    transition: all 150ms var(--ease);

    .el-icon {
      font-size: 17px;
      color: #93a58c;
      transition: color 150ms var(--ease);
    }

    &:hover {
      background: #f4f8f1;
      color: #3c4a3a;

      .el-icon {
        color: var(--crop-green);
      }
    }

    &.active {
      background: #eaf3e5;
      color: #2e7a2a;
      font-weight: 600;

      .el-icon {
        color: var(--crop-green);
      }
    }
  }

  /* 知识库「核心」标签：强化特色入口感 */
  .nav-tag {
    margin-left: auto;
    font-size: 10px;
    line-height: 1;
    padding: 3px 7px;
    border-radius: var(--radius-pill);
    background: #e7f2e2;
    color: #3d8b37;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  /* ---------- 对话分组区（独立于历史对话，与「历史对话」并列） ---------- */
  .groups {
    flex: 0 1 auto;
    display: flex;
    flex-direction: column;
    margin-top: 8px;
    border-top: 1px solid #f2f5ef;
    padding-top: 10px;
    max-height: 40%;
    min-height: 0;
  }

  .groups-head {
    display: flex;
    align-items: center;
    padding: 2px 10px 6px;
  }

  .groups-title {
    font-size: 12px;
    font-weight: 600;
    color: #8a9785;
    letter-spacing: 1px;
  }

  .groups-list {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-right: 2px;
    min-height: 0;
  }

  .groups-empty {
    text-align: center;
    color: #a9b5a3;
    font-size: 12px;
    padding: 10px 8px 12px;
  }

  /* ---------- 分组导航项（点击进入右侧详情页，不内联展开） ---------- */
  .group-row {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 6px 7px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 150ms var(--ease);

    &:hover {
      background: #f4f8f1;

      .group-ico,
      .group-name {
        color: var(--crop-green);
      }

      .sec-actions {
        opacity: 1;
      }
    }

    &.active {
      background: #eaf3e5;

      .group-name {
        color: #2e7a2a;
        font-weight: 600;
      }

      .group-ico {
        color: var(--crop-green);
      }
    }

    .group-ico {
      color: #a5b59e;
      font-size: 15px;
      flex: 0 0 auto;
      display: flex;
      align-items: center;
    }

    .group-name {
      flex: 1;
      min-width: 0;
      font-size: 13.5px;
      line-height: 1.5;
      color: #3d493b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding-right: 4px;
    }
  }

  /* ---------- 历史会话列表 ---------- */
  .history {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    margin-top: 8px;
    border-top: 1px solid #f2f5ef;
    padding-top: 10px;
  }

  .history-head {
    display: flex;
    align-items: center;
    padding: 2px 10px 6px;
  }

  .history-title {
    font-size: 12px;
    font-weight: 600;
    color: #8a9785;
    letter-spacing: 1px;
  }

  .history-count {
    font-size: 11px;
    color: #a9b5a3;
    background: #f4f7f1;
    border-radius: var(--radius-pill);
    padding: 0 7px;
    margin-left: 6px;
  }

  /* 头部小按钮：新建分组 */
  .head-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: 4px;
    padding: 3px 8px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #8a9785;
    font-size: 12px;
    cursor: pointer;
    transition: all 150ms var(--ease);

    &:hover {
      background: #f2f8ef;
      color: var(--crop-green);
    }

    &.is-active {
      background: #eaf3e5;
      color: var(--crop-green);
      font-weight: 600;
    }

    &:last-child {
      margin-left: auto;
    }
  }

  .history-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-right: 2px;
    min-height: 80px;
  }

  .history-empty {
    text-align: center;
    color: #a9b5a3;
    font-size: 13px;
    padding: 24px 8px;
  }

  /* 批量操作栏（历史区底部） */
  .history-batch {
    flex: 0 0 auto;
    margin-top: 8px;
  }

  /* ---------- 分区头 ---------- */
  .sec-head {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 8px 3px;
    margin-top: 4px;
    border-radius: 6px;

    &:hover .sec-actions {
      opacity: 1;
    }

    .sec-ico {
      display: flex;
      align-items: center;
      color: var(--crop-green);
      font-size: 12px;
      width: 18px;
      justify-content: center;
    }

    .sec-title {
      font-size: 11.5px;
      font-weight: 600;
      color: #7d8b77;
      letter-spacing: 0.5px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
      min-width: 0;
    }

    .sec-count {
      font-size: 10.5px;
      color: #a9b5a3;
      background: #f2f5ef;
      border-radius: var(--radius-pill);
      padding: 0 6px;
      flex: 0 0 auto;
    }

    /* 分区头悬停操作（重命名 / 删除） */
    .sec-actions {
      display: flex;
      align-items: center;
      gap: 1px;
      opacity: 0;
      transition: opacity 150ms var(--ease);

      .act-btn {
        width: 20px;
        height: 20px;

        .el-icon {
          font-size: 11px;
        }
      }
    }
  }

  .sec-items {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* ---------- 历史条目 ---------- */
  .history-item {
    position: relative;
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 6px 7px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 150ms var(--ease);

    &:hover {
      background: #f4f8f1;
    }

    /* 当前会话高亮 */
    &.active {
      background: #eaf3e5;

      .item-title {
        color: #2e7a2a;
        font-weight: 600;
      }

      .item-icon {
        color: var(--crop-green);
      }
    }

    /* 置顶会话：图钉主色 */
    &.is-pinned .item-icon {
      color: var(--crop-green);
    }

    /* 批量模式下选中高亮 */
    &.selected {
      background: #eaf3e5;
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

    .item-icon {
      color: #a5b59e;
      font-size: 15px;
      flex: 0 0 auto;
      display: flex;
      align-items: center;
    }

    .item-main {
      flex: 1;
      min-width: 0;
    }

    .item-title-line {
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;

      .item-title {
        flex: 1;
        min-width: 0;
      }

      /* 空对话「未使用」标签（需求2 文字提示） */
      .item-tag {
        flex: 0 0 auto;
        font-size: 10.5px;
        line-height: 1;
        color: #b8860b;
        background: #fdf6e3;
        border-radius: var(--radius-pill);
        padding: 2px 7px;
        white-space: nowrap;
      }
    }

    .item-title {
      font-size: 13.5px;
      line-height: 1.5;
      color: #3d493b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding-right: 4px;
    }
  }

  .act-btn {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #7d8b77;
    cursor: pointer;
    transition: all 120ms var(--ease);

    .el-icon,
    .pin-icon {
      font-size: 13px;
    }

    &:hover {
      background: #e8f3e4;
      color: var(--crop-green);
    }

    &.danger:hover {
      background: #fdeceb;
      color: var(--crop-error);
    }
  }

  /* ---------- 底部：收起/展开 ---------- */
  .sidebar-foot {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
    border-top: 1px solid #f2f5ef;
    padding-top: 8px;
  }

  .collapse-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    padding: 8px 12px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: #8a9785;
    font-size: 12.5px;
    cursor: pointer;
    transition: all 150ms var(--ease);

    &:hover {
      background: #f2f8ef;
      color: var(--crop-green);
    }
  }

  .foot-text {
    font-size: 11px;
    color: #bdc7b9;
  }

  /* ---------- 收起状态：仅显示图标 ---------- */
  &.collapsed {
    .brand {
      justify-content: center;
      padding-left: 0;
      padding-right: 0;
    }

    .brand-text,
    .btn-text,
    .nav-label,
    .nav-tag,
    .groups,
    .history,
    .foot-text {
      display: none;
    }

    .new-chat-btn {
      width: 42px;
      height: 42px;
      margin: 2px auto 0;
      padding: 0;
      justify-content: center;
      border: none;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--crop-green), #55a14f);
      color: #fff;
      box-shadow: 0 4px 10px rgba(61, 139, 55, 0.25);

      .el-icon {
        color: #fff;
        font-size: 18px;
        transform: none;
      }

      &:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 14px rgba(61, 139, 55, 0.32);
      }
    }

    .nav {
      margin-top: 10px;
    }

    .nav-item {
      justify-content: center;
      padding: 10px 0;
    }

    .collapse-btn {
      width: 100%;
      height: 36px;
      padding: 0;
    }
  }

  /* ---------- 移动端：汉堡菜单呼出的抽屉 ---------- */
  @media (max-width: 767px) {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 210;
    width: 280px;
    transform: translateX(-105%);
    box-shadow: 4px 0 24px rgba(31, 61, 29, 0.12);
    transition: transform 250ms var(--ease);

    &.mobile-open {
      transform: translateX(0);
    }

    /* 移动端抽屉始终展示完整内容（忽略 localStorage 的收起状态） */
    &.collapsed {
      width: 280px;

      .brand {
        justify-content: flex-start;
        padding-left: 8px;
        padding-right: 8px;
      }

      .brand-text,
      .btn-text,
      .nav-label,
      .nav-tag,
      .foot-text {
        display: block;
      }

      .groups,
      .history {
        display: flex;
      }

      .new-chat-btn {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 9px 12px;
        justify-content: flex-start;
        border: 1px solid #dde6d8;
        border-radius: 10px;
        background: #fff;
        color: #3c4a3a;
        box-shadow: none;

        .el-icon {
          color: var(--crop-green);
          font-size: 16px;
        }

        &:hover {
          background: #f2f8ef;
          transform: none;
        }
      }

      .nav-item {
        justify-content: flex-start;
        padding: 9px 12px;
      }

      .collapse-btn {
        width: 100%;
        height: auto;
        padding: 8px 12px;
      }
    }

    .sidebar-close {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-left: auto;
      width: 30px;
      height: 30px;
      border: none;
      border-radius: 50%;
      background: #f2f5ef;
      color: #5c6b57;
      cursor: pointer;

      &:hover {
        background: #e8f3e4;
        color: var(--crop-green);
      }
    }

    /* 移动端抽屉不使用收起/展开按钮（桌面端偏好由 localStorage 记忆） */
    .collapse-btn {
      display: none;
    }
  }

  /* 触屏设备（移动端抽屉）：分区头/分组操作常显，保证可点 */
  @media (hover: none) {
    .sec-head .sec-actions,
    .group-row .sec-actions {
      opacity: 1;
    }
  }
}
</style>
