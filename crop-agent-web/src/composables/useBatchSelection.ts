/**
 * 批量选择状态（历史区 / 分组详情页共用）：
 *  - batchMode：是否处于批量管理模式
 *  - selected：已选 session_id 集合（Set 便于 O(1) 判断）
 *  - toggle / toggleAll / isSelected / clear / exit
 */
import { computed, ref } from 'vue'

export function useBatchSelection() {
  const batchMode = ref(false)
  const selected = ref<Set<string>>(new Set())

  const count = computed(() => selected.value.size)
  const hasSelected = computed(() => selected.value.size > 0)

  function isSelected(id: string) {
    return selected.value.has(id)
  }

  function toggle(id: string) {
    const next = new Set(selected.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selected.value = next
  }

  /** 全选 / 取消全选；返回操作后的全选状态（true=已全选）。 */
  function toggleAll(ids: string[]): boolean {
    const next = new Set(selected.value)
    if (ids.length && ids.every((id) => next.has(id))) {
      // 已全选 → 取消全选
      for (const id of ids) next.delete(id)
    } else {
      for (const id of ids) next.add(id)
    }
    selected.value = next
    return ids.length > 0 && ids.every((id) => next.has(id))
  }

  function clear() {
    selected.value = new Set()
  }

  /** 退出批量模式并清空选中。 */
  function exit() {
    batchMode.value = false
    selected.value = new Set()
  }

  return {
    batchMode,
    selected,
    count,
    hasSelected,
    isSelected,
    toggle,
    toggleAll,
    clear,
    exit,
  }
}
