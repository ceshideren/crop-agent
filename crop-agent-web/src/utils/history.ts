/**
 * 历史对话分组工具：置顶区 / 自定义分组 / 日期区（今天·昨天·7日内·30日内·更早）。
 * 会话归属规则：
 *  - 置顶会话 → 「置顶」区（最高优先级，不参与分组与日期）；
 *  - 有 group_id 且分组仍存在 → 对应自定义分组；
 *  - 其余 → 按创建时间落入日期桶。
 * 删除分组只移除分组关系，会话自动回到日期区（原始顺序由日期排序保证）。
 *
 * 分组区强制完整展示：无论分组内是否有会话，分组标题都会出现在结果里
 * （空分组也要可见，保持界面结构完整）。
 *
 * 日期桶计算统一走 utils/time.ts 的 daysAgo（时区安全）：
 * 后端时间戳为 UTC 且带 Z 标记，客户端换算本地自然日后分桶，
 * 避免「今天」的会话因时区偏差被划进「昨天」。
 */
import type { SessionGroup, SessionItem } from '@/types'
import { daysAgo } from '@/utils/time'

export type HistorySectionKind = 'pinned' | 'group' | 'date'

export interface HistorySection {
  key: string
  title: string
  kind: HistorySectionKind
  groupId?: number | null
  items: SessionItem[]
}

/** 会话 → 日期桶标签：今天 / 昨天 / 7日内 / 30日内 / 更早 */
export function dateBucketLabel(iso: string | null): string {
  const days = daysAgo(iso)
  if (days == null) return '更早'
  if (days <= 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return '7日内'
  if (days < 30) return '30日内'
  return '更早'
}

const DATE_BUCKET_ORDER = ['今天', '昨天', '7日内', '30日内', '更早']

export function buildHistorySections(
  sessions: SessionItem[],
  groups: SessionGroup[],
): HistorySection[] {
  const sections: HistorySection[] = []

  // 1. 置顶区
  const pinned = sessions.filter((s) => s.pinned)
  if (pinned.length) {
    sections.push({ key: 'pinned', title: '置顶', kind: 'pinned', items: pinned })
  }

  // 2. 自定义分组（按分组创建顺序；空分组也强制展示，保证结构完整）
  for (const g of groups) {
    const items = sessions.filter((s) => !s.pinned && s.group_id === g.id)
    sections.push({
      key: `group-${g.id}`,
      title: g.name,
      kind: 'group',
      groupId: g.id,
      items,
    })
  }

  // 3. 日期区：非置顶且不在任何有效分区内
  const validGroupIds = new Set(groups.map((g) => g.id))
  const buckets = new Map<string, SessionItem[]>()
  for (const s of sessions) {
    if (s.pinned) continue
    if (s.group_id != null && validGroupIds.has(s.group_id)) continue
    const label = dateBucketLabel(s.created_at)
    if (!buckets.has(label)) buckets.set(label, [])
    buckets.get(label)!.push(s)
  }
  for (const title of DATE_BUCKET_ORDER) {
    const items = buckets.get(title) || []
    if (items.length) {
      sections.push({ key: `date-${title}`, title, kind: 'date', items })
    }
  }

  return sections
}
