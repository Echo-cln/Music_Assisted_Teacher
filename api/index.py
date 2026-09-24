"""Vercel Serverless Function 入口。

仓库的实际 FastAPI 应用在 backend/app/main.py；此文件只负责在 Vercel 的
Python 运行时中补上模块搜索路径并导出 ASGI 应用。
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

