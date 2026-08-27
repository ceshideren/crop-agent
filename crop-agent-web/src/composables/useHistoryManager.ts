/**
 * 历史对话分组工具（AppSidebar 与 HistoryView 共用）：
 *  - 按「置顶区 / 自定义分组 / 日期区」划分展示结构
 *  - 新建 / 重命名 / 删除自定义分组（分组删除后会话自动释放回日期区）
 *  - 单条对话的 重命名/置顶/移动分组/删除 已收敛到 SessionActionMenu 组件
 */
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { buildHistorySections } from '@/utils/history'

const GROUP_NAME_VALIDATOR = (v: string) => (v && v.trim() ? true : '分组名称不能为空')

export function useHistoryManager() {
  const store = useChatStore()

  /** 按「置顶区 / 自定义分组 / 日期区」划分后的完整展示结构 */
  const sections = computed(() => buildHistorySections(store.sessions, store.groups))

  /** 独立「对话分组」区：仅自定义分组（空分组也展示），与历史对话区并列 */
  const groupSections = computed(() => sections.value.filter((s) => s.kind === 'group'))

  /** 「历史对话」区：置顶区 + 日期区（分组内的会话不再出现在这里） */
  const historySections = computed(() => sections.value.filter((s) => s.kind !== 'group'))

  function promptGroupName(
    title: string,
    inputValue?: string,
  ): Promise<string | null> {
    return ElMessageBox.prompt('请输入分组名称', title, {
      inputValue,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: GROUP_NAME_VALIDATOR,
    })
      .then(({ value }) => value.trim())
      .catch(() => null)
  }

  /** 新建分组 */
  async function onCreateGroup() {
    const name = await promptGroupName('新建分组')
    if (name) await store.createGroup(name)
  }

  /** 重命名分组 */
  async function onRenameGroup(gid: number) {
    const g = store.groups.find((x) => x.id === gid)
    if (!g) return
    const name = await promptGroupName('重命名分组', g.name)
    if (name && name !== g.name) await store.renameGroup(gid, name)
  }

  /** 删除单个分组 */
  function onDeleteGroup(gid: number) {
    const g = store.groups.find((x) => x.id === gid)
    ElMessageBox.confirm(
      `确定删除分组「${g?.name ?? ''}」吗？分组内的对话不会被删除，将按时间放回日期区。`,
      '删除分组',
      {
        confirmButtonText: '删除分组',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
      .then(() => store.deleteGroups([gid]))
      .catch(() => {
        /* 用户取消 */
      })
  }

  return {
    sections,
    groupSections,
    historySections,
    onCreateGroup,
    onRenameGroup,
    onDeleteGroup,
  }
}
