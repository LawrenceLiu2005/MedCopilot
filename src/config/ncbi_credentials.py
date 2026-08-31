"""NCBI 凭证统一解析（App、客户端、pytest 共用）。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _streamlit_secret(name: str) -> str | None:
    """读取 Streamlit Cloud Secrets；本地无 secrets 时忽略。"""
    try:
        import streamlit as st

        raw = st.secrets[name]
    except Exception:
        return None
    text = str(raw).strip()
    return text or None


def resolve_ncbi_email(*, workspace_path: Path | None = None) -> str | None:
    """解析 NCBI 邮箱。优先级：环境变量（含 .env）> Streamlit Secrets > workspace.json。"""
    load_dotenv()
    email = os.getenv("NCBI_EMAIL", "").strip()
    if email:
        return email

    secret_email = _streamlit_secret("NCBI_EMAIL")
    if secret_email:
        return secret_email

    # 延迟导入，避免 storage → search → pubmed → 本模块 的循环依赖
    from src.services.storage import load_workspace

    workspace = load_workspace(workspace_path)
    if workspace and workspace.ncbi_email:
        return workspace.ncbi_email.strip()
    return None


def resolve_ncbi_api_key() -> str | None:
    """解析 NCBI API Key。仅环境变量 / .env / Streamlit Secrets（不写 workspace）。"""
    load_dotenv()
    key = os.getenv("NCBI_API_KEY", "").strip()
    if key:
        return key
    return _streamlit_secret("NCBI_API_KEY")


def has_ncbi_email(*, workspace_path: Path | None = None) -> bool:
    """是否已有可用的 NCBI 邮箱。"""
    return bool(resolve_ncbi_email(workspace_path=workspace_path))
