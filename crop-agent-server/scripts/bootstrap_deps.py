"""引导脚本：在无法使用 pip/uv 的环境下，直接从 PyPI 下载并解压 wheel 到 _smoke_deps/。

仅用于沙箱冒烟测试（沙箱禁止带管道捕获的子进程，pip/uv/venv 均不可用）。
全程单进程：urllib 下载 + zipfile 解压，不调用任何子进程。

用法：
  python scripts/bootstrap_deps.py
然后：
  $env:PYTHONPATH="<server根>\\_smoke_deps"; python scripts/smoke_test.py
"""
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "_smoke_deps")
os.makedirs(TARGET, exist_ok=True)

# 冒烟测试所需的完整传递依赖（模块级）
PACKAGES = [
    "fastapi",
    "starlette",
    "annotated-doc",
    "pydantic",
    "pydantic-core",
    "pydantic-settings",
    "python-dotenv",
    "typing-inspection",
    "sqlalchemy",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    "idna",
    "certifi",
    "typing-extensions",
    "annotated-types",
    "python-multipart",
    "websockets",
]


def fetch_json(url, tries=4):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last


def fetch_bytes(url, tries=4):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last


def pick_wheel(files):
    """优先纯 Python wheel，其次 cp312 win_amd64，其次 abi3。"""

    def score(f):
        if f.endswith("py3-none-any.whl"):
            return 3
        if "-cp312-" in f and "win_amd64" in f:
            return 2
        if "-abi3-" in f and "win_amd64" in f:
            return 1
        return 0

    return max(files, key=score)


def _pin_core_version(reqs):
    """从 pydantic 的 requires_dist 中提取 pydantic-core 的精确版本约束。"""
    for r in reqs or []:
        if r.lower().startswith("pydantic-core"):
            m = re.search(r"==\s*([0-9][0-9.]*)", r)
            if m:
                return m.group(1)
    return None


def main():
    core_pin = None
    for pkg in PACKAGES:
        if pkg == "pydantic-core" and core_pin:
            url = f"https://pypi.org/pypi/{pkg}/{core_pin}/json"
        else:
            url = f"https://pypi.org/pypi/{pkg}/json"
        try:
            data = fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            print(f"SKIP {pkg}: {exc}")
            continue

        if pkg == "pydantic":
            core_pin = _pin_core_version(data["info"].get("requires_dist"))
            print(f"PIN  pydantic-core -> {core_pin}")

        info_name = data["info"]["name"]
        prefix = info_name.replace("-", "_")
        wheels = [
            u
            for u in data.get("urls", [])
            if u["filename"].endswith(".whl")
            and u["filename"].lower().startswith(prefix.lower())
        ]
        if not wheels:
            print(f"SKIP {pkg}: no wheel found")
            continue

        filename = pick_wheel([u["filename"] for u in wheels])
        info = next(u for u in wheels if u["filename"] == filename)
        marker = os.path.join(TARGET, filename + ".done")
        if os.path.exists(marker):
            print(f"OK   {pkg} (cached) {filename}")
            continue

        print(f"GET  {pkg} -> {filename}")
        blob = fetch_bytes(info["url"])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            # 先清掉同名包的旧解压目录，避免残留旧版本
            tops = {n.split("/")[0] for n in z.namelist() if "/" in n}
            for t in tops:
                shutil.rmtree(os.path.join(TARGET, t), ignore_errors=True)
            z.extractall(TARGET)
        with open(marker, "w", encoding="utf-8") as f:
            f.write("ok")

    print("DONE ->", TARGET)


if __name__ == "__main__":
    sys.exit(main())
