"""前后端契约 Pydantic 模型（统一响应格式）。"""
from typing import Any, List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    content: str


class FilePayload(BaseModel):
    """上传的普通文件（word/pdf/md/excel/文本 等）。"""

    name: str = "file"
    mime: str = ""
    data: str = ""  # base64 / dataURL


class MultimodalChatRequest(BaseModel):
    session_id: Optional[str] = None
    content: str = ""
    images: List[str] = []  # base64 dataURL
    files: List[FilePayload] = []  # 普通文件


class Source(BaseModel):
    doc_id: str
    chunk: str
    score: float


class SessionUpdateRequest(BaseModel):
    """会话更新：重命名 / 置顶（至少传一个字段）。"""

    title: Optional[str] = None
    pinned: Optional[bool] = None


class SessionCreateRequest(BaseModel):
    """创建会话（可选归属分组）。"""

    group_id: Optional[int] = None


class BatchDeleteRequest(BaseModel):
    """批量删除会话。"""

    session_ids: List[str]


class GroupCreateRequest(BaseModel):
    """新建自定义分区。"""

    name: str


class GroupUpdateRequest(BaseModel):
    """重命名自定义分区。"""

    name: str


class GroupAssignRequest(BaseModel):
    """批量把会话移入/移出分区：group_id 为 None 表示移出所有分区。"""

    session_ids: List[str]
    group_id: Optional[int] = None


class GroupBatchDeleteRequest(BaseModel):
    """批量删除分区（分区内会话自动释放回日期区）。"""

    group_ids: List[int]


class ApiResponse(BaseModel):
    code: int = 200
    data: dict = {}
    sources: List[Source] = []
    message: str = "success"

    @classmethod
    def ok(cls, data: dict, sources: Optional[List[Source]] = None) -> "ApiResponse":
        return cls(code=200, data=data, sources=sources or [], message="success")

    @classmethod
    def fail(cls, message: str, code: int = 500) -> "ApiResponse":
        return cls(code=code, data={}, sources=[], message=message)
