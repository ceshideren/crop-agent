/**
 * 关键词高亮工具：先 HTML 转义再包裹 <mark>，杜绝注入。
 * 用于检索结果正文/标题中高亮查询词，让用户一眼定位命中点。
 */

/** HTML 转义（& < > " '）。 */
export function escapeHtml(text: string): string {
  return (text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 查询词 → 高亮 token 列表：整体 + 空白分词（中英文连续片段）。 */
export function queryTokens(query: string): string[] {
  const q = (query || '').trim()
  if (!q) return []
  const tokens = q.split(/\s+/).filter(Boolean)
  // 整体查询串也参与高亮（如"稻瘟病"整体命中更醒目）
  return [q, ...tokens].filter((t, i, arr) => arr.indexOf(t) === i)
}

/**
 * 对 text 做关键词高亮，返回可直接用于 v-html 的安全 HTML。
 * 顺序：转义全文 → 单次正则交替匹配（token 按长度降序，长词优先）包裹 <mark>，
 * 避免短 token 嵌套进长 token 的 mark 内部。
 */
export function highlightHtml(text: string, query: string): string {
  const tokens = queryTokens(query)
  const html = escapeHtml(text)
  if (!tokens.length) return html
  const sorted = [...tokens].sort((a, b) => b.length - a.length)
  const escaped = sorted.map(escapeHtml).filter(Boolean)
  if (!escaped.length) return html
  const pattern = escaped
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  return html.replace(new RegExp(pattern, 'g'), (m) => `<mark>${m}</mark>`)
}
