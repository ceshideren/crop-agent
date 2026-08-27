<script setup lang="ts">
/**
 * 单条对话操作菜单（最终版）：
 *  - ✏️ 重命名
 *  - 📌 置顶此对话 / 取消置顶（按当前状态动态文案；置顶后列表强制排最前）
 *  - 📂 移动到分组（悬停向右展开二级子菜单：现有分区 + 新增分区；已所在分区显示对勾，
 *        点击可移出；另提供独立「移出分组」项）
 *  - 🗑️ 删除此对话（二次确认）
 *
 * 触发：左键点击省略号按钮弹出；点击菜单外部任意处或按 Esc 立即关闭。
 * 定位：fixed 定位相对触发按钮，自动做屏幕边缘防遮挡翻转/收拢。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import PinIcon from '@/components/PinIcon.vue'
import type { SessionItem } from '@/types'

const props = defineProps<{ session: SessionItem }>()
const store = useChatStore()

const open = ref(false)
const subOpen = ref(false)
const btnRef = ref<HTMLElement>()
const menuRef = ref<HTMLElement>()
const subRef = ref<HTMLElement>()
const menuPos = ref({ left: 0, top: 0 })
const subPos = ref({ left: 0, top: 0 })

const isPinned = computed(() => !!props.session.pinned)
const inGroup = computed(() => props.session.group_id != null)

// ---------- 开关 ----------
function close() {
  open.value = false
  subOpen.value = false
}

async function toggleMenu(e: MouseEvent) {
  e.stopPropagation()
  e.preventDefault()
  if (open.value) {
    close()
    return
  }
  open.value = true
  subOpen.value = false
  await nextTick()
  placeMenu()
}

// ---------- 定位（相对触发按钮 + 视口防遮挡） ----------
function placeMenu() {
  const btn = btnRef.value
  const menu = menuRef.value
  if (!btn || !menu) return
  const br = btn.getBoundingClientRect()
  const mw = menu.offsetWidth
  const mh = menu.offsetHeight
  const gap = 6
  const vw = window.innerWidth
  const vh = window.innerHeight
  // 默认菜单右缘与按钮右缘对齐
  let left = br.right - mw
  if (left < 8) left = 8
  if (left + mw > vw - 8) left = vw - mw - 8
  // 默认向下展开；底部放不下则向上翻转
  let top = br.bottom + gap
  if (top + mh > vh - 8) top = Math.max(8, br.top - mh - gap)
  menuPos.value = { left, top }
}

function openSub() {
  if (!subOpen.value) {
    subOpen.value = true
    nextTick(placeSub)
  }
}

/** 触屏无 hover：点击「移动到分组」同样展开/收起子菜单 */
function toggleSub() {
  if (subOpen.value) subOpen.value = false
  else openSub()
}

function placeSub() {
  const menu = menuRef.value
  const sub = subRef.value
  if (!menu || !sub) return
  const mr = menu.getBoundingClientRect()
  const sw = sub.offsetWidth
  const sh = sub.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight
  // 默认在主菜单右侧展开；右侧放不下则翻到左侧
  let left = mr.right + 2
  if (left + sw > vw - 8) left = mr.left - sw - 2
  let top = mr.top
  if (top + sh > vh - 8) top = Math.max(8, vh - sh - 8)
  subPos.value = { left, top }
}

// ---------- 外部点击 / Esc 关闭 ----------
function onDocMouseDown(e: MouseEvent) {
  if (!open.value) return
  const t = e.target as Node
  if (menuRef.value?.contains(t) || btnRef.value?.contains(t)) return
  close()
}
function onDocKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onDocKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  document.removeEventListener('keydown', onDocKeydown)
})

// ---------- 菜单动作 ----------
/** 重命名 */
function onRename() {
  ElMessageBox.prompt('请输入新的对话名称', '重命名对话', {
    inputValue: props.session.title,
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
  })
    .then(({ value }) => store.renameSession(props.session.session_id, value))
    .catch(() => {
      /* 用户取消 */
    })
    .finally(() => close())
}

/** 置顶 / 取消置顶（store 内部会重排序：置顶强制排最前） */
function onTogglePin() {
  store.togglePin(props.session.session_id)
  close()
}

/** 移入分区；点击当前所在分区 = 移出该分区 */
function onMoveToGroup(gid: number | null) {
  const target = props.session.group_id === gid ? null : gid
  store.assignSessions([props.session.session_id], target)
  close()
}

/** 新增分区并移入 */
async function onCreateGroupAndMove() {
  const name = await ElMessageBox.prompt('请输入分组名称', '新建分组并移入', {
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputValidator: (v: string) => (v && v.trim() ? true : '分组名称不能为空'),
  })
    .then(({ value }) => value.trim())
    .catch(() => null)
  if (!name) return
  const ok = await store.createGroup(name)
  if (!ok) return
  const g = store.groups[store.groups.length - 1]
  if (g) await store.assignSessions([props.session.session_id], g.id)
  close()
}

/** 删除（二次确认） */
function onDelete() {
  ElMessageBox.confirm('确定要删除此对话吗？此操作不可撤销。', '删除对话', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
    confirmButtonClass: 'el-button--danger',
  })
    .then(() => store.deleteSession(props.session.session_id))
    .catch(() => {
      /* 用户取消 */
    })
    .finally(() => close())
}
</script>

<template>
  <span class="sa-wrap" @click.stop>
    <button
      ref="btnRef"
      class="sa-trigger"
      :class="{ open }"
      type="button"
      title="对话操作"
      aria-label="对话操作"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggleMenu"
    >
      <el-icon><MoreFilled /></el-icon>
    </button>

    <!-- 挂载到 body：避免被侧边栏 overflow:hidden 裁剪，fixed 定位以视口为基准 -->
    <Teleport to="body">
      <div
        v-if="open"
        ref="menuRef"
        class="sa-menu"
        role="menu"
        :style="{ left: `${menuPos.left}px`, top: `${menuPos.top}px` }"
        @mouseleave="subOpen = false"
      >
        <button type="button" class="sa-item" role="menuitem" @click="onRename">
          <el-icon><EditPen /></el-icon>
          <span>重命名</span>
        </button>

        <button type="button" class="sa-item" role="menuitem" @click="onTogglePin">
          <PinIcon :filled="isPinned" />
          <span>{{ isPinned ? '取消置顶' : '置顶此对话' }}</span>
        </button>

        <!-- 移动到分组：悬停或点击展开二级子菜单 -->
        <div class="sa-item sa-has-sub" role="menuitem" @mouseenter="openSub" @click="toggleSub">
          <el-icon><FolderOpened /></el-icon>
          <span>移动到分组</span>
          <el-icon class="sa-sub-arrow"><ArrowRight /></el-icon>
        </div>

        <div class="sa-divider"></div>

        <button type="button" class="sa-item sa-danger" role="menuitem" @click="onDelete">
          <el-icon><Delete /></el-icon>
          <span>删除此对话</span>
        </button>

        <!-- 二级子菜单：现有分区 + 新增分区 -->
        <div
          v-if="subOpen"
          ref="subRef"
          class="sa-submenu"
          role="menu"
          :style="{ left: `${subPos.left}px`, top: `${subPos.top}px` }"
        >
          <template v-if="store.groups.length">
            <button
              v-for="g in store.groups"
              :key="g.id"
              type="button"
              class="sa-item"
              :class="{ active: session.group_id === g.id }"
              role="menuitem"
              @click="onMoveToGroup(g.id)"
            >
              <el-icon><Folder /></el-icon>
              <span class="sa-sub-name">{{ g.name }}</span>
              <el-icon v-if="session.group_id === g.id" class="sa-check">
                <Check />
              </el-icon>
            </button>
            <div class="sa-divider"></div>
          </template>
          <button
            v-if="inGroup"
            type="button"
            class="sa-item"
            role="menuitem"
            @click="onMoveToGroup(null)"
          >
            <el-icon><FolderDelete /></el-icon>
            <span>移出分组</span>
          </button>
          <button type="button" class="sa-item" role="menuitem" @click="onCreateGroupAndMove">
            <el-icon><Plus /></el-icon>
            <span>新增分组</span>
          </button>
        </div>
      </div>
    </Teleport>
  </span>
</template>

<style scoped lang="scss">
.sa-wrap {
  flex: 0 0 auto;
  display: inline-flex;
}

/* ---------- 省略号触发按钮 ---------- */
.sa-trigger {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #7d8b77;
  cursor: pointer;
  transition: all 120ms var(--ease);

  .el-icon {
    font-size: 16px;
  }

  &:hover,
  &.open {
    background: #e8f3e4;
    color: var(--crop-green);
  }
}

/* ---------- 主菜单 ---------- */
.sa-menu {
  position: fixed;
  z-index: 3000;
  min-width: 192px;
  padding: 5px;
  background: #fff;
  border: 1px solid #eef1ea;
  border-radius: 12px;
  box-shadow: 0 6px 24px rgba(31, 61, 29, 0.14), 0 2px 8px rgba(31, 61, 29, 0.08);
}

.sa-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #3d493b;
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
  transition: background 120ms var(--ease), color 120ms var(--ease);

  .el-icon,
  .pin-icon {
    font-size: 15px;
    color: #7d8b77;
    flex: 0 0 auto;
  }

  &:hover {
    background: #f2f8ef;
    color: var(--crop-green);

    .el-icon,
    .pin-icon {
      color: var(--crop-green);
    }
  }

  &.active {
    color: var(--crop-green);
    font-weight: 600;

    .el-icon {
      color: var(--crop-green);
    }
  }

  &.sa-danger:hover {
    background: #fdeceb;
    color: var(--crop-error);

    .el-icon {
      color: var(--crop-error);
    }
  }
}

/* 含二级子菜单的项 */
.sa-has-sub {
  position: relative;

  .sa-sub-arrow {
    margin-left: auto;
    font-size: 13px;
  }

  &:hover {
    background: #f2f8ef;
    color: var(--crop-green);

    .el-icon {
      color: var(--crop-green);
    }
  }
}

.sa-divider {
  height: 1px;
  margin: 4px 6px;
  background: #f0f3ec;
}

/* ---------- 二级子菜单 ---------- */
.sa-submenu {
  position: fixed;
  z-index: 3001;
  min-width: 176px;
  max-width: 260px;
  padding: 5px;
  background: #fff;
  border: 1px solid #eef1ea;
  border-radius: 12px;
  box-shadow: 0 6px 24px rgba(31, 61, 29, 0.14), 0 2px 8px rgba(31, 61, 29, 0.08);

  .sa-sub-name {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sa-check {
    font-size: 14px;
    color: var(--crop-green);
  }
}
</style>
