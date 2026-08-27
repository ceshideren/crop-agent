/**
 * 相对时间格式化：今天 / 昨天 / N天前 / 具体日期
 * 提示词4：会话列表需显示相对时间。
 *
 * 时区契约（关键修复）：
 * 后端把时间统一按「naive UTC」入库，并序列化为带 Z 后缀的 ISO 串。
 * 无时区标记的字符串会被浏览器 new Date() 当作「本地时间」解析——
 * 例如 UTC+8 下，今天凌晨新建的会话（UTC 仍是昨天）会被误读成昨天，
 * 导致「今天」的对话错误落入「昨天」分组。因此：
 *  1) 解析时若缺少时区标记，一律按 UTC 补 Z；
 *  2) 日期分桶基于「本地自然日」对齐计算，与用户所在时区一致。
 */
const DAY_MS = 24 * 60 * 60 * 1000

/** 解析后端时间戳；无法解析时返回 null。 */
export function parseServerDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  let s = iso.trim()
  // 末尾无时区标记（Z / ±hh:mm / ±hhmm）→ 按 UTC 补 Z
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(s)) s += 'Z'
  const t = new Date(s).getTime()
  if (Number.isNaN(t)) return null
  return new Date(t)
}

/** 某时刻对应的「本地自然日 00:00」时间戳（用于跨日比较）。 */
function localDayStart(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/**
 * 距今的自然日天数差：今天=0、昨天=1、前天=2……（按本地日历日对齐）。
 * 解析失败返回 null。
 */
export function daysAgo(iso: string | null | undefined): number | null {
  const d = parseServerDate(iso)
  if (!d) return null
  const todayStart = localDayStart(new Date())
  const thatDayStart = localDayStart(d)
  // 两个本地零点之差必为整 24h 倍数，Math.round 在此精确无损
  return Math.round((todayStart - thatDayStart) / DAY_MS)
}

export function formatRelativeTime(iso: string | null): string {
  const days = daysAgo(iso)
  if (days == null) return ''
  if (days <= 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days}天前`
  const d = parseServerDate(iso)!
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

/** 绝对日期格式化：YYYY-MM-DD（知识库表格"更新时间"列）。解析失败返回空串。 */
export function formatDate(iso: string | null | undefined): string {
  const d = parseServerDate(iso)
  if (!d) return ''
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}
