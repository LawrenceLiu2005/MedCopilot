"""DeepSeek 凭证解析；密钥不写入 workspace。"""

from __future__ import annotations

import os

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def _streamlit_secret(name: str) -> str | None:
    """读取 Streamlit Cloud Secrets；本地无 secrets 时忽略。"""
    try:
        import streamlit as st

        raw = st.secrets[name]
    except Exception:
        return None
    text = str(raw).strip()
    return text or None


def resolve_deepseek_api_key() -> str | None:
    """解析 DeepSeek 密钥。优先级：环境变量 / .env > Streamlit Secrets。"""
    load_dotenv()
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    return _streamlit_secret("DEEPSEEK_API_KEY")


def resolve_deepseek_base_url() -> str:
    """DeepSeek 接口根地址。"""
    load_dotenv()
    url = os.getenv("DEEPSEEK_BASE_URL", "").strip()
    if url:
        return url.rstrip("/")
    secret = _streamlit_secret("DEEPSEEK_BASE_URL")
    if secret:
        return secret.rstrip("/")
    return DEFAULT_BASE_URL


def resolve_deepseek_model() -> str:
    """DeepSeek 模型名。"""
    load_dotenv()
    model = os.getenv("DEEPSEEK_MODEL", "").strip()
    if model:
        return model
    secret = _streamlit_secret("DEEPSEEK_MODEL")
    if secret:
        return secret
    return DEFAULT_MODEL
