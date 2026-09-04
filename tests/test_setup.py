"""NCBI 设置页与凭证解析测试。"""

from pathlib import Path

import pytest

from src.config.deepseek_credentials import resolve_deepseek_api_key
from src.config.ncbi_credentials import has_ncbi_email, resolve_ncbi_email
from src.services.storage import save_workspace
from src.ui.setup import is_valid_email, mask_email


def test_is_valid_email():
    assert is_valid_email("user@example.com")
    assert not is_valid_email("invalid")
    assert not is_valid_email("user@localhost")


def test_mask_email():
    assert mask_email("researcher@uni.edu") == "r***@uni.edu"


def test_resolve_ncbi_email_from_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    path = tmp_path / "workspace.json"
    save_workspace([], None, "saved@example.com", path=path)
    assert resolve_ncbi_email(workspace_path=path) == "saved@example.com"
    assert has_ncbi_email(workspace_path=path) is True


def test_resolve_ncbi_email_env_overrides_workspace(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "env@example.com")
    path = tmp_path / "workspace.json"
    save_workspace([], None, "saved@example.com", path=path)
    assert resolve_ncbi_email(workspace_path=path) == "env@example.com"


def test_resolve_ncbi_email_from_streamlit_secrets(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.setattr(
        "src.config.ncbi_credentials._streamlit_secret",
        lambda name: "secret@example.com" if name == "NCBI_EMAIL" else None,
    )
    path = tmp_path / "workspace.json"
    save_workspace([], None, "saved@example.com", path=path)
    assert resolve_ncbi_email(workspace_path=path) == "secret@example.com"


def test_resolve_deepseek_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    assert resolve_deepseek_api_key() == "sk-test-key"


def test_resolve_deepseek_api_key_missing(monkeypatch):
    monkeypatch.setattr("src.config.deepseek_credentials.load_dotenv", lambda: None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "src.config.deepseek_credentials._streamlit_secret",
        lambda name: None,
    )
    assert resolve_deepseek_api_key() is None
