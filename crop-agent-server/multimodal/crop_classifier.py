"""作物识别辅助：基于文本关键词返回候选作物与置信度（VLM 缺省时的降级辅助）。"""

_CROP_KEYWORDS = {
    "水稻": ["稻", "水稻", "稻田", "稻穗", "稻谷"],
    "小麦": ["小麦", "麦穗", "麦田", "麦苗"],
    "玉米": ["玉米", "苞谷", "棒子", "玉米杆"],
    "番茄": ["番茄", "西红柿", "圣女果"],
    "马铃薯": ["马铃薯", "土豆", "洋芋"],
    "辣椒": ["辣椒", "青椒", "朝天椒"],
    "黄瓜": ["黄瓜", "青瓜"],
    "大豆": ["大豆", "黄豆", "毛豆"],
}


def classify_crop(text: str):
    """返回 [(label, confidence)]，按命中关键词数量估算置信度。"""
    text = text or ""
    scored = []
    for crop, kws in _CROP_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in text)
        if hits:
            confidence = min(0.95, 0.5 + 0.15 * hits)
            scored.append({"label": crop, "confidence": round(confidence, 2)})
    scored.sort(key=lambda x: -x["confidence"])
    return scored[:3]
