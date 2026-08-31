"""Evidence Copilot 入口。"""

import streamlit as st

from src.config.ncbi_credentials import resolve_ncbi_email
from src.services.storage import (
    WORKSPACE_PATH,
    load_workspace,
    quarantine_corrupt_workspace,
    save_workspace,
)
from src.ui.history import render_history_page
from src.ui.results import render_results_page, sync_active_search
from src.ui.search import render_search_page
from src.ui.setup import get_ncbi_credentials, has_ncbi_credentials, mask_email, render_setup_page

# 学术液态玻璃：牛津蓝、Plex Sans + Noto Sans SC、玻璃高光与漫射阴影
_ACADEMIC_GLASS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select,
[data-testid="stWidgetLabel"] p {
  font-family: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif !important;
  letter-spacing: 0.01em;
}

.stApp {
  background-color: #E8ECF2;
  background-image:
    radial-gradient(ellipse 80% 50% at 12% -10%, rgba(31, 78, 121, 0.14), transparent 55%),
    radial-gradient(ellipse 60% 40% at 92% 8%, rgba(184, 160, 122, 0.12), transparent 50%),
    radial-gradient(ellipse 50% 60% at 70% 100%, rgba(28, 36, 52, 0.06), transparent 45%);
  color: #1C2434;
}

/* 固定极淡噪点，不绑滚动容器 */
.stApp::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: 9998;
  pointer-events: none;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

[data-testid="stSidebar"] {
  background: rgba(255, 255, 255, 0.48) !important;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-right: 1px solid rgba(255, 255, 255, 0.4) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    4px 0 24px -12px rgba(28, 36, 52, 0.1);
}
[data-testid="stSidebar"] * { color: #1C2434; }

h1 {
  font-family: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif !important;
  font-weight: 600 !important;
  letter-spacing: 0 !important;
  color: #1C2434 !important;
  text-align: left !important;
}
h2, h3 {
  font-family: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif !important;
  font-weight: 600 !important;
  letter-spacing: 0 !important;
  color: #1C2434 !important;
}

[data-testid="stCaption"] { color: #5B6577 !important; }

/* 液态玻璃卡片：顶边 gilt 高光，无青绿竖轨 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 12px !important;
  border: 1px solid rgba(255, 255, 255, 0.45) !important;
  border-top: 1px solid #B8A07A !important;
  background: rgba(255, 255, 255, 0.58) !important;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.65),
    0 12px 32px -12px rgba(28, 36, 52, 0.14) !important;
  animation: cardIn 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
}

div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(1) { animation-delay: 0.02s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(2) { animation-delay: 0.06s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(3) { animation-delay: 0.10s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(4) { animation-delay: 0.14s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(5) { animation-delay: 0.18s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(6) { animation-delay: 0.22s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(7) { animation-delay: 0.26s; }
div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(8) { animation-delay: 0.30s; }

@keyframes cardIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  div[data-testid="stVerticalBlockBorderWrapper"] { animation: none !important; }
  .stButton > button, .stDownloadButton > button { transition: none !important; }
}

div[data-testid="stExpander"],
div[data-testid="stMetric"] {
  border-radius: 12px !important;
  border: 1px solid rgba(255, 255, 255, 0.4) !important;
  background: rgba(255, 255, 255, 0.5) !important;
  backdrop-filter: blur(12px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5) !important;
}

.stButton > button,
.stDownloadButton > button,
.stLinkButton > a {
  border-radius: 12px !important;
  font-weight: 500 !important;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1),
              background-color 0.2s cubic-bezier(0.16, 1, 0.3, 1),
              border-color 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.25),
    0 4px 12px -4px rgba(28, 36, 52, 0.12) !important;
}
.stButton > button:active,
.stDownloadButton > button:active,
.stLinkButton > a:active {
  transform: scale(0.98) !important;
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
  background-color: #1F4E79 !important;
  border-color: #1F4E79 !important;
  color: #F5F7FA !important;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover {
  background-color: #163A5C !important;
  border-color: #163A5C !important;
}

.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox [data-baseweb="select"] > div {
  border-radius: 12px !important;
  border-color: rgba(28, 36, 52, 0.16) !important;
  background-color: rgba(255, 255, 255, 0.72) !important;
  backdrop-filter: blur(8px);
}

[data-testid="stCode"], pre, code, .stCodeBlock {
  font-family: "IBM Plex Mono", "Noto Sans SC", ui-monospace, monospace !important;
}
[data-testid="stCode"] {
  background-color: #1C2434 !important;
  color: #D8DEE8 !important;
  border-radius: 12px !important;
  border: 1px solid rgba(184, 160, 122, 0.35) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
  padding: 0.85rem 1.05rem !important;
}
[data-testid="stCode"] code, [data-testid="stCode"] pre {
  color: #D8DEE8 !important;
  background: transparent !important;
}

.mono-id {
  font-family: "IBM Plex Mono", "Noto Sans SC", ui-monospace, monospace !important;
  font-size: 0.875rem;
  color: #5B6577;
}

hr { border-color: rgba(28, 36, 52, 0.1) !important; }
</style>
"""


def init_session_state() -> None:
    """初始化会话状态。"""
    if "history" not in st.session_state:
        st.session_state.history = []
    if "records" not in st.session_state:
        st.session_state.records = []
    if "active_search" not in st.session_state:
        st.session_state.active_search = None
    if "ncbi_email" not in st.session_state:
        st.session_state.ncbi_email = None
    if "ncbi_api_key" not in st.session_state:
        st.session_state.ncbi_api_key = None
    if not st.session_state.get("_workspace_hydrated"):
        workspace = load_workspace()
        if workspace:
            st.session_state.history = workspace.history
            st.session_state.active_search = workspace.active_search
            st.session_state.records = workspace.records
            if workspace.ncbi_email:
                st.session_state.ncbi_email = workspace.ncbi_email
        elif WORKSPACE_PATH.is_file():
            bak = quarantine_corrupt_workspace()
            st.session_state._workspace_corrupt = True
            st.session_state._workspace_corrupt_bak = str(bak) if bak else None
        st.session_state._workspace_hydrated = True


def persist_workspace() -> None:
    """将当前工作区写入本地文件。"""
    if st.session_state.get("_workspace_corrupt"):
        return
    sync_active_search()
    email = (st.session_state.get("ncbi_email") or "").strip() or resolve_ncbi_email()
    try:
        save_workspace(
            st.session_state.history,
            st.session_state.active_search,
            email,
        )
    except OSError:
        if not st.session_state.get("_workspace_save_warned"):
            st.warning("工作区未能写入本地文件，请检查目录权限。")
            st.session_state._workspace_save_warned = True


st.set_page_config(page_title="Evidence Copilot", layout="wide")
st.markdown(_ACADEMIC_GLASS_CSS, unsafe_allow_html=True)
init_session_state()

if st.session_state.get("_workspace_corrupt"):
    bak_hint = st.session_state.get("_workspace_corrupt_bak") or "workspace.json.bak"
    st.warning(
        f"本地工作区文件损坏，已改名为备份（{bak_hint}），本次不会覆盖它。"
        "可到「历史」页导入备份；新的检索保存后会重新写入工作区。"
    )

if not has_ncbi_credentials():
    st.title("Evidence Copilot")
    render_setup_page()
    persist_workspace()
    st.stop()

st.title("Evidence Copilot")
st.caption("PubMed 可复现检索 · 检索审计留痕 · 人工初筛 · 标准导出")

st.sidebar.markdown("### Evidence Copilot")
email, _ = get_ncbi_credentials()
st.sidebar.caption(f"NCBI：{mask_email(email)}")
st.sidebar.caption("工作台导航")
st.sidebar.divider()

page = st.sidebar.radio("导航", ["搜索", "结果", "历史", "设置"], label_visibility="collapsed")

if page == "搜索":
    render_search_page()
elif page == "结果":
    render_results_page()
elif page == "历史":
    render_history_page()
else:
    render_setup_page()

persist_workspace()
