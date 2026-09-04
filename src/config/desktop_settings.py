"""桌面版设置（Application Support/.env）。"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from src.services.research_project_storage import default_data_dir

SETTINGS_KEYS = (
    "NCBI_EMAIL",
    "NCBI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
)


def settings_env_path():
    return default_data_dir() / ".env"


def load_desktop_env() -> None:
    """加载桌面版 .env；侧车每次命令前应调用。"""
    path = settings_env_path()
    if path.is_file():
        load_dotenv(path, override=True)


def _mask_secret(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}****{value[-2:]}"


def _read_env_file() -> dict[str, str]:
    path = settings_env_path()
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, raw = text.partition("=")
        values[key.strip()] = raw.strip()
    return values


def get_settings_payload() -> dict:
    load_desktop_env()
    stored = _read_env_file()
    ncbi_email = stored.get("NCBI_EMAIL") or os.getenv("NCBI_EMAIL", "").strip()
    ncbi_key = stored.get("NCBI_API_KEY") or os.getenv("NCBI_API_KEY", "").strip()
    deepseek_key = stored.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "").strip()
    return {
        "env_path": str(settings_env_path()),
        "ncbi_email": ncbi_email,
        "ncbi_api_key_set": bool(ncbi_key),
        "ncbi_api_key_hint": _mask_secret(ncbi_key) if ncbi_key else "",
        "deepseek_api_key_set": bool(deepseek_key),
        "deepseek_api_key_hint": _mask_secret(deepseek_key) if deepseek_key else "",
        "has_ncbi_email": bool(ncbi_email),
    }


def save_settings_payload(params: dict) -> dict:
    path = settings_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = _read_env_file()

    if "ncbi_email" in params:
        stored["NCBI_EMAIL"] = str(params.get("ncbi_email") or "").strip()
    if params.get("ncbi_api_key"):
        stored["NCBI_API_KEY"] = str(params["ncbi_api_key"]).strip()
    if params.get("deepseek_api_key"):
        stored["DEEPSEEK_API_KEY"] = str(params["deepseek_api_key"]).strip()

    lines = [f"{key}={stored[key]}" for key in SETTINGS_KEYS if stored.get(key)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    load_dotenv(path, override=True)
    return get_settings_payload()
