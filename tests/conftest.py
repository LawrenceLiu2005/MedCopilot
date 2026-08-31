"""pytest 全局配置：从 workspace 注入 NCBI 凭证。"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from src.config.ncbi_credentials import resolve_ncbi_api_key, resolve_ncbi_email


def pytest_configure(config) -> None:
    """测试启动时：若环境变量无邮箱，尝试从 workspace.json 注入。"""
    load_dotenv()
    if not os.getenv("NCBI_EMAIL"):
        email = resolve_ncbi_email()
        if email:
            os.environ["NCBI_EMAIL"] = email
    if not os.getenv("NCBI_API_KEY"):
        api_key = resolve_ncbi_api_key()
        if api_key:
            os.environ["NCBI_API_KEY"] = api_key
