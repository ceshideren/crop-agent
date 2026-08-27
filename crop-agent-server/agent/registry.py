"""进程级 Agent 单例持有，供 HTTP 与 WebSocket 路由共用。"""

_agent = None


def set_agent(agent) -> None:
    global _agent
    _agent = agent


def get_agent():
    if _agent is None:
        raise RuntimeError("Agent 尚未初始化（lifespan 启动阶段完成）")
    return _agent
