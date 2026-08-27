import { marked } from 'marked'
import DOMPurify from 'dompurify'

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    (
      {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      } as Record<string, string>
    )[c],
  )
}

/**
 * Markdown → 安全 HTML，并解析自定义标记：
 *   [TABLE]...[/TABLE] 表格包裹（移除，保留内部 markdown 表格）
 *   [SOURCE:doc_id#chunk] 来源标签
 *   [IMAGE:url] 知识库图片引用
 */
export function renderMarkdown(md: string): string {
  if (!md) return ''
  let text = md.replace(/\[TABLE\]/g, '').replace(/\[\/TABLE\]/g, '')

  const raw = marked.parse(text, { gfm: true, breaks: true }) as string
  let html = DOMPurify.sanitize(raw)

  html = html.replace(/\[SOURCE:([^\]]+)\]/g, (_m, label: string) => {
    return `<span class="source-chip">📄 ${escapeHtml(label)}</span>`
  })
  html = html.replace(/\[IMAGE:([^\]]+)\]/g, (_m, url: string) => {
    const safe = /^(https?:\/\/|data:image\/)/.test(url.trim()) ? url.trim() : ''
    return safe ? `<img class="md-image" src="${escapeHtml(safe)}" alt="知识库图片" />` : ''
  })

  return html
}
