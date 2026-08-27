"""Agent 工具定义。

与「全局提示词」第六节 LangChain Tools 一一对应。这里采用轻量 ToolRegistry，
便于在无 LLM 时也走确定性编排；生产环境可将每个函数包成 langchain 的 @tool。
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable
    trigger: str = ""


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self.tools[spec.name] = spec

    def call(self, name: str, **kwargs) -> Any:
        spec = self.tools[name]
        return spec.func(**kwargs)

    def names(self):
        return list(self.tools.keys())


# ---- 工具实现（依赖通过闭包注入）----

def make_search_knowledge_base(retriever):
    def search_knowledge_base(query: str, top_k: int = None):
        hits = retriever.search(query, top_k)
        return [
            {
                "doc_id": h.doc_id,
                "chunk_id": h.chunk_id,
                "title": h.title,
                "text": h.text,
                "score": h.score,
            }
            for h in hits
        ]

    return search_knowledge_base


def make_identify_crop_image(analyzer):
    def identify_crop_image(image_bytes: bytes):
        return analyzer.analyze(image_bytes, task="identify")

    return identify_crop_image


def make_diagnose_disease_image(analyzer):
    def diagnose_disease_image(image_bytes: bytes):
        return analyzer.analyze(image_bytes, task="diagnose")

    return diagnose_disease_image


def get_region_climate(region: str):
    """内置少量常见产区气候参考（演示用）；生产环境接外部气象 API。"""
    region = (region or "").strip()
    table = {
        "东北": "温带季风气候，≥10℃ 积温 2200–3100℃，一年一熟，适宜春玉米、大豆、水稻。",
        "华北": "暖温带季风气候，≥10℃ 积温 3400–4500℃，两年三熟或一年两熟，适宜冬小麦、玉米。",
        "长江中下游": "亚热带季风气候，≥10℃ 积温 4500–5500℃，一年两熟，适宜水稻、油菜、棉花。",
        "华南": "热带/亚热带季风气候，≥10℃ 积温 6500℃ 以上，一年三熟，适宜水稻、甘蔗、荔枝。",
        "西南": "地形复杂、立体气候明显，适宜水稻、玉米、烟草、茶叶。",
        "西北": "温带大陆性气候，降水少、光照足，适宜小麦、棉花、瓜果（灌溉农业）。",
    }
    for key, val in table.items():
        if key in region:
            return val
    return (
        f"暂无「{region}」的精细化气候数据（外部气象 API 未接入）。"
        "建议补充所在省/市或积温带，以便给出更准确的种植建议。"
    )


def get_market_price(crop: str):
    """行情工具占位：生产环境接外部行情 API，此处返回演示说明。"""
    crop = (crop or "").strip() or "该作物"
    return (
        f"实时行情接口未接入，暂无法提供「{crop}」的精确市场价格。"
        "建议参考当地批发市场或全国农产品商务信息公共服务平台的最新报价。"
    )


def make_get_chat_history(get_messages):
    def get_chat_history(session_id: str, n: int = 6):
        return get_messages(session_id, n)

    return get_chat_history
