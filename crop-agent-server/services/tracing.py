"""LangSmith 可观测性：零依赖条件接入。

- 未启用（LANGSMITH_TRACING=false 或未填 API Key）时，装饰器直接透传原函数，业务零感知；
- 启用后，调用经 langsmith.trace 上下文管理器创建 run，父子 run 自动嵌套
  （crop_agent.run → llm.generate / retriever.search / analyzer.analyze）；
- 配置从 .env（pydantic settings）读取，调用前注入真实环境变量供 langsmith 客户端使用，
  因此不要求用户把 key 写进系统环境变量。
"""
import dataclasses
import functools
import inspect
import os

_ENV_KEYS = {
    "langsmith_api_key": "LANGSMITH_API_KEY",
    "langsmith_project": "LANGSMITH_PROJECT",
    "langsmith_endpoint": "LANGSMITH_ENDPOINT",
}


def langsmith_enabled() -> bool:
    from config import get_settings

    s = get_settings()
    return bool(s.langsmith_tracing and s.langsmith_api_key)


def _inject_env() -> bool:
    """将 .env 中的 LangSmith 配置注入真实环境变量（langsmith 客户端只读真实 env）。"""
    if not langsmith_enabled():
        return False
    from config import get_settings

    s = get_settings()
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    for attr, env in _ENV_KEYS.items():
        os.environ[env] = str(getattr(s, attr))
    return True


def _serializable(obj):
    """递归转成 langsmith 可序列化结构：dataclass→dict、bytes→占位、其余→repr。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        return f"<bytes {len(obj)}>"
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serializable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    return repr(obj)


def _outputs_to_dict(out) -> dict:
    """run.end(outputs=...) 要求 dict：非 dict 输出统一包一层 {"output": ...}。"""
    serialized = _serializable(out)
    return serialized if isinstance(serialized, dict) else {"output": serialized}


def _extract_inputs(fn, args, kwargs) -> dict:
    """从调用参数中提取可序列化的 inputs（跳过 self 等运行时对象）。"""
    try:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        return _serializable(
            {k: v for k, v in bound.arguments.items() if k != "self"}
        )
    except (TypeError, ValueError):
        return {}


def traceable(name: str, run_type: str = "chain", **run_kwargs):
    """条件 @traceable：LangSmith 未启用时透传原函数；启用时包一层 run 追踪。

    保持原函数同步/异步形态：同步函数得到同步 wrapper，调用点无需加 await。
    """

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                if not _inject_env():
                    return await fn(*args, **kwargs)
                from langsmith import trace

                async with trace(
                    name=name,
                    run_type=run_type,
                    inputs=_extract_inputs(fn, args, kwargs),
                    **run_kwargs,
                ) as run:
                    try:
                        out = await fn(*args, **kwargs)
                    except Exception as e:  # 记录错误，不吞异常
                        run.end(error=f"{type(e).__name__}: {e}")
                        raise
                    run.end(outputs=_outputs_to_dict(out))
                    return out

        else:

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                if not _inject_env():
                    return fn(*args, **kwargs)
                from langsmith import trace

                with trace(
                    name=name,
                    run_type=run_type,
                    inputs=_extract_inputs(fn, args, kwargs),
                    **run_kwargs,
                ) as run:
                    try:
                        out = fn(*args, **kwargs)
                    except Exception as e:  # 记录错误，不吞异常
                        run.end(error=f"{type(e).__name__}: {e}")
                        raise
                    run.end(outputs=_outputs_to_dict(out))
                    return out

        return wrapper

    return decorator
