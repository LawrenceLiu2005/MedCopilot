"""NCBI 账号设置（会话级，非密码登录）。"""

from __future__ import annotations

import streamlit as st

from src.clients.pubmed import PubMedClient
from src.config.ncbi_credentials import resolve_ncbi_api_key, resolve_ncbi_email
from src.services.storage import save_workspace


def is_valid_email(email: str) -> bool:
    """简单邮箱格式校验。"""
    value = email.strip()
    if "@" not in value:
        return False
    local, domain = value.rsplit("@", 1)
    return bool(local and domain and "." in domain)


def mask_email(email: str) -> str:
    """侧栏脱敏显示。"""
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    masked_local = local[0] + "***" if local else "***"
    return f"{masked_local}@{domain}"


def get_ncbi_credentials() -> tuple[str, str | None]:
    """会话凭证优先，其次环境变量 / workspace。"""
    session_email = (st.session_state.get("ncbi_email") or "").strip()
    email = session_email or (resolve_ncbi_email() or "")
    session_key = st.session_state.get("ncbi_api_key")
    if session_key:
        api_key = str(session_key).strip() or None
    else:
        api_key = resolve_ncbi_api_key()
    return email, api_key


def has_ncbi_credentials() -> bool:
    return bool(get_ncbi_credentials()[0])


def build_pubmed_client() -> PubMedClient:
    email, api_key = get_ncbi_credentials()
    return PubMedClient(email=email, api_key=api_key)


def render_setup_page() -> None:
    """设置 NCBI 邮箱与可选 API Key。"""
    st.header("设置 NCBI 账号")
    st.caption(
        "PubMed 官方接口要求填写联系邮箱。邮箱会保存到本地，下次打开自动恢复；"
        "API Key 仅本次浏览器有效。"
    )
    st.markdown(
        "还没有 NCBI 账号？[免费注册](https://www.ncbi.nlm.nih.gov/account/)"
    )

    current_email, current_key = get_ncbi_credentials()
    default_email = st.session_state.get("ncbi_email") or current_email
    default_key = st.session_state.get("ncbi_api_key") or current_key or ""

    email = st.text_input("NCBI 邮箱", value=default_email, placeholder="your-email@example.com")
    api_key = st.text_input(
        "NCBI API Key（可选）",
        value=default_key,
        type="password",
        help="在 NCBI 账号设置中申请，有 Key 时检索更快。",
    )

    if st.button("保存并进入", type="primary"):
        cleaned = email.strip()
        if not is_valid_email(cleaned):
            st.error("请填写有效的邮箱地址（需包含 @ 和域名）。")
            return
        st.session_state.ncbi_email = cleaned
        st.session_state.ncbi_api_key = api_key.strip() or None
        st.session_state._workspace_corrupt = False
        try:
            save_workspace(
                st.session_state.get("history", []),
                st.session_state.get("active_search"),
                cleaned,
            )
        except OSError:
            st.warning("邮箱已保存到本次会话，但未能写入本地文件，请检查目录权限。")
        st.success("已保存。邮箱下次打开会自动恢复；请从左侧进入「搜索」开始检索。")
        st.rerun()
