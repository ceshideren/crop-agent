"""多模态图片理解：mimo-2.5 优先，未配置时降级为基础元信息 + 友好提示。"""
import base64
import io
from dataclasses import dataclass, field
from typing import List, Optional

from services.tracing import traceable


@dataclass
class VisionResult:
    task: str
    description: str = ""
    labels: List[dict] = field(default_factory=list)  # [{"label": str, "confidence": float}]
    simulated: bool = True


class ImageAnalyzer:
    def __init__(self, settings=None):
        from config import get_settings

        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.mimo_api_key and self.settings.mimo_base_url)

    @traceable("mimo.vision", run_type="tool", metadata={"provider": "mimo"})
    async def analyze(self, image_bytes: bytes, task: str = "identify") -> VisionResult:
        if self.available:
            result = await self._vlm_analyze(image_bytes, task)
            if result is not None:
                return result
        return self._fallback(image_bytes, task)

    async def _vlm_analyze(self, image_bytes: bytes, task: str) -> Optional[VisionResult]:
        """调用 mimo-2.5（OpenAI 兼容视觉端点）。失败则返回 None 走兜底。"""
        import httpx

        b64 = base64.b64encode(image_bytes).decode()
        prompt = (
            "请识别图片中的农作物种类，描述形态特征。"
            if task == "identify"
            else "请诊断图片中作物的病虫害，描述病斑特征并给出可能的病害名称。"
        )
        payload = {
            "model": self.settings.mimo_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.mimo_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.settings.mimo_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
            return VisionResult(task=task, description=text, simulated=False)
        except Exception:
            return None

    def _fallback(self, image_bytes: bytes, task: str) -> VisionResult:
        meta = _image_meta(image_bytes)
        hint = (
            "当前未配置多模态模型（mimo-2.5），暂无法识别具体作物。"
            "请补充文字描述（叶形/果形/颜色等），系统将基于知识库检索为您解答。"
            if task == "identify"
            else "当前未配置多模态模型（mimo-2.5），暂无法诊断病害。"
            "请补充病斑颜色、形态、部位等文字描述，系统将基于知识库检索为您解答。"
        )
        desc_parts = [hint]
        if meta:
            desc_parts.append(
                f"（图片信息：{meta['format']}，{meta['width']}×{meta['height']}px"
                + (f"，主色调偏向{meta['tone']}" if meta.get("tone") else "")
                + "）"
            )
        return VisionResult(
            task=task, description=" ".join(desc_parts), simulated=True
        )


def _image_meta(image_bytes: bytes) -> dict:
    info = {"format": "unknown", "width": 0, "height": 0}
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        info["format"] = (img.format or "unknown").lower()
        info["width"], info["height"] = img.size
        try:
            small = img.convert("RGB").resize((1, 1))
            r, g, b = small.getpixel((0, 0))
            info["tone"] = _tone(r, g, b)
        except Exception:
            pass
    except Exception:
        pass
    return info


def _tone(r: int, g: int, b: int) -> str:
    if g > r and g > b and g - max(r, b) > 10:
        return "绿色（可能为健康叶片/植株）"
    if r > g and g > b and r - b > 20:
        return "黄褐色（可能黄化/枯萎/病斑）"
    if r > g and b > g and r - b > 20:
        return "深褐色（可能为土壤/根茎/坏死组织）"
    return "中性色"
