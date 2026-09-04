"""DeepSeek Chat Completions 客户端（OpenAI 兼容 JSON 模式）。"""

from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.deepseek_credentials import (
    resolve_deepseek_api_key,
    resolve_deepseek_base_url,
    resolve_deepseek_model,
)

TIMEOUT = 60.0


class DeepSeekError(Exception):
    """DeepSeek 调用失败。"""


class DeepSeekConfigError(DeepSeekError):
    """缺少密钥或配置无效。"""


class DeepSeekRetryableError(DeepSeekError):
    """可重试的瞬时失败。"""


def _chat_url(base_url: str) -> str:
    """拼 chat/completions 地址；兼容带或不带 /v1 的根路径。"""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/chat/completions"


def _strip_markdown_fence(text: str) -> str:
    """去掉模型可能包上的 ```json 围栏。"""
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_json_content(text: str) -> dict[str, Any]:
    """把模型回复解析成 JSON 对象。"""
    cleaned = _strip_markdown_fence(text)
    if not cleaned:
        raise DeepSeekError("模型返回为空，无法拆出 PICO。")
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("模型返回不是合法 JSON，无法拆出 PICO。") from exc
    if not isinstance(payload, dict):
        raise DeepSeekError("模型返回的 JSON 不是对象，无法拆出 PICO。")
    return payload


class DeepSeekClient:
    """仅用于结构化 JSON 补全，不用于筛文献。"""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = TIMEOUT,
    ) -> None:
        self.api_key = (api_key if api_key is not None else resolve_deepseek_api_key() or "").strip()
        if not self.api_key:
            raise DeepSeekConfigError("缺少 DeepSeek 密钥，请在设置页或 .env 中配置 DEEPSEEK_API_KEY。")
        self.base_url = (base_url or resolve_deepseek_base_url()).rstrip("/")
        self.model = (model or resolve_deepseek_model()).strip() or resolve_deepseek_model()
        self.timeout = timeout

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """调用 chat/completions，要求 JSON 对象。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        data = self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek 返回格式异常。") from exc
        if content is None:
            raise DeepSeekError("模型返回为空，无法拆出 PICO。")
        return parse_json_content(str(content))

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, DeepSeekRetryableError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _chat_url(self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise DeepSeekRetryableError(f"DeepSeek 网络请求失败: {exc}") from exc
        if response.status_code in {401, 403}:
            raise DeepSeekError("DeepSeek 密钥无效或没有权限。")
        if response.status_code == 402:
            raise DeepSeekError("DeepSeek 账户余额不足。")
        if response.status_code == 429:
            raise DeepSeekRetryableError("DeepSeek 请求过于频繁，请稍后再试。")
        if response.status_code >= 500:
            raise DeepSeekRetryableError(f"DeepSeek 服务器错误: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise DeepSeekError(f"DeepSeek 请求被拒绝: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise DeepSeekError("DeepSeek 返回格式异常。") from exc
