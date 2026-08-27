"""文本生成层：DeepSeek（OpenAI 兼容端点）优先，缺省时降级为本地模板引擎。"""
from config import get_settings
from services.tracing import traceable


class LLMClient:
    """封装 deepseek 文本生成调用。未配置 API Key 时 available=False。"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    @traceable("deepseek.chat", run_type="llm", metadata={"provider": "deepseek"})
    async def generate(self, messages: list) -> str:
        """messages: [{role, content}]，返回模型生成的完整文本。"""
        if not self.available:
            return ""
        import httpx

        payload = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "temperature": 0.6,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.settings.deepseek_api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.settings.deepseek_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
