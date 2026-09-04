"""DeepSeek 客户端测试（无真实网络）。"""

from unittest.mock import MagicMock

import pytest

from src.clients.deepseek import (
    DeepSeekClient,
    DeepSeekConfigError,
    DeepSeekError,
    parse_json_content,
)


def test_parse_json_content_object():
    payload = parse_json_content('{"population": ["metformin"]}')
    assert payload["population"] == ["metformin"]


def test_parse_json_content_strips_fence():
    payload = parse_json_content("```json\n{\"ok\": true}\n```")
    assert payload["ok"] is True


def test_parse_json_content_rejects_array():
    with pytest.raises(DeepSeekError, match="不是对象"):
        parse_json_content("[1, 2]")


def test_parse_json_content_rejects_invalid():
    with pytest.raises(DeepSeekError, match="不是合法 JSON"):
        parse_json_content("not-json")


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "src.clients.deepseek.resolve_deepseek_api_key",
        lambda: None,
    )
    with pytest.raises(DeepSeekConfigError, match="缺少 DeepSeek"):
        DeepSeekClient(api_key="")


def test_complete_json_parses_message(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert "Authorization" in headers
        assert json["response_format"]["type"] == "json_object"
        assert json["thinking"]["type"] == "disabled"
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {"message": {"content": '{"population": ["hepatocellular carcinoma"]}'}}
            ]
        }
        return response

    monkeypatch.setattr("src.clients.deepseek.httpx.post", fake_post)
    client = DeepSeekClient(api_key="sk-test", model="deepseek-v4-flash")
    payload = client.complete_json([{"role": "user", "content": "q"}])
    assert payload["population"] == ["hepatocellular carcinoma"]


def test_complete_json_401(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        response = MagicMock()
        response.status_code = 401
        return response

    monkeypatch.setattr("src.clients.deepseek.httpx.post", fake_post)
    client = DeepSeekClient(api_key="bad", model="deepseek-v4-flash")
    with pytest.raises(DeepSeekError, match="密钥无效"):
        client.complete_json([{"role": "user", "content": "q"}])
