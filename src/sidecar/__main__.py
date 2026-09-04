"""JSON 行侧车入口：Pi 扩展通过 subprocess 调用。

用法::
    echo '{"command":"ping"}' | python -m src.sidecar
    python -m src.sidecar --command propose_search --params '{"research_idea":"..."}'
"""

from __future__ import annotations

import argparse
import json
import sys

from src.config.desktop_settings import load_desktop_env
from src.sidecar.handlers import HANDLERS

load_desktop_env()


def _respond(ok: bool, *, result: dict | None = None, error: str | None = None) -> dict:
    payload: dict = {"ok": ok}
    if result is not None:
        payload["result"] = result
    if error:
        payload["error"] = error
    return payload


def dispatch(command: str, params: dict) -> dict:
    handler = HANDLERS.get(command)
    if handler is None:
        return _respond(False, error=f"未知命令：{command}")
    try:
        result = handler(params or {})
        return _respond(True, result=result)
    except Exception as exc:  # noqa: BLE001 — 侧车边界需返回 JSON 错误
        return _respond(False, error=str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence Copilot Python 侧车")
    parser.add_argument("--command", help="命令名")
    parser.add_argument("--params", default="{}", help="JSON 参数字符串")
    args = parser.parse_args(argv)

    if args.command:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as exc:
            print(json.dumps(_respond(False, error=f"params 不是合法 JSON：{exc}"), ensure_ascii=False))
            return 1
        print(json.dumps(dispatch(args.command, params), ensure_ascii=False))
        return 0

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError as exc:
            print(json.dumps(_respond(False, error=f"输入不是合法 JSON：{exc}"), ensure_ascii=False))
            continue
        command = str(message.get("command") or "")
        params = message.get("params") or {}
        print(json.dumps(dispatch(command, params), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
