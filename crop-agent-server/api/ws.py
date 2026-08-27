"""WebSocket 流式路由（/ws/chat/stream）：逐块推送 LLM 回复。"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.registry import get_agent
from services.image_util import decode_data_url

router = APIRouter()


def _chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i : i + size]


@router.websocket("/ws/chat/stream")
async def chat_stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            agent = get_agent()

            content = data.get("content", "")
            image_urls = data.get("images", []) or []
            image_bytes = [decode_data_url(i) for i in image_urls if i]
            files = [
                {
                    "name": (f.get("name") or "file")[:128],
                    "mime": f.get("mime", "") or "",
                    "data": decode_data_url(f.get("data", "") or ""),
                }
                for f in (data.get("files", []) or [])
            ]
            session_id = data.get("session_id")

            try:
                res = await agent.run(
                    content,
                    images=image_bytes or None,
                    image_urls=image_urls,
                    files=files or None,
                    session_id=session_id,
                )
            except Exception as exc:  # 兜底：错误也通过流式返回
                await ws.send_json({"type": "error", "message": str(exc)})
                continue

            await ws.send_json(
                {
                    "type": "meta",
                    "session_id": res.session_id,
                    "sources": res.sources,
                }
            )
            for chunk in _chunk_text(res.reply):
                await ws.send_json({"type": "delta", "text": chunk})
                await asyncio.sleep(0.015)
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
