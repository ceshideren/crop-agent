"""图片 base64 / dataURL 工具。"""
import base64


def decode_data_url(data_url: str) -> bytes:
    """支持 `data:image/png;base64,...` 与纯 base64 字符串。"""
    if not data_url:
        return b""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        return base64.b64decode(data_url)
    except Exception:
        return b""
