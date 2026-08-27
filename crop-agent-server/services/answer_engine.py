"""离线模板回答引擎：无 LLM Key 时，基于检索片段拼装结构化回答。

输出遵循「全局提示词」第九节格式：核心结论 → 详细说明 → 来源标注 → 延伸建议。
"""
from typing import List, Optional


def _clip(text: str, limit: int) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _format_sources(hits) -> str:
    lines = ["**来源**"]
    for h in hits[:5]:
        lines.append(f"- `[{h.source_label}]` {h.title}（相似度 {h.score}）")
    return "\n".join(lines)


def build_fallback_answer(query: str, hits, vision=None) -> str:
    parts: List[str] = []

    if vision and vision.description:
        parts.append(f"**图片识别**：{vision.description}")

    if hits:
        top = hits[0]
        parts.append(f"根据知识库「{top.title}」检索结果，为您整理如下：")
        for h in hits[:3]:
            parts.append(f"**{h.title}**：{_clip(h.text, 260)}")
        parts.append(_format_sources(hits))
    else:
        parts.append("知识库中暂无与该问题高度匹配的内容。")
        tip = _builtin_hint(query)
        if tip:
            parts.append(f"以下为通用建议（⚠️ 非知识库内容）：\n\n{tip}")
        else:
            parts.append("建议您补充作物名称、症状（叶片/果实/根部表现）与所在地区，便于进一步检索。")

    parts.append("> 以上内容由本地知识引擎生成，仅供参考，请结合当地实际。配置 LLM Key 后可获得更完整的生成式回答。")
    return "\n\n".join(parts)


def _builtin_hint(query: str) -> str:
    """少量内置常识兜底（明确标注为非知识库内容）。"""
    q = query or ""
    hints = []
    if any(k in q for k in ("稻", "水稻")):
        hints.append(
            "- 水稻喜高温多湿，全生育期需充足水分，抽穗期注意防治稻瘟病与纹枯病。"
        )
    if any(k in q for k in ("麦", "小麦")):
        hints.append(
            "- 小麦为禾本科作物，冬小麦一般秋播，注意返青期追肥与拔节期防倒伏。"
        )
    if any(k in q for k in ("番茄", "西红柿")):
        hints.append(
            "- 番茄为茄科作物，喜温喜光，注意整枝打杈与早疫病、晚疫病的预防。"
        )
    return "\n".join(hints)
