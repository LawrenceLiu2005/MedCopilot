# Handoff — Evidence Copilot

> 新会话请先读此文件，再接上次的进度。

## 最后更新

2026-09-04

## 当前进度

**桌面版 Phase 0.5 已补完（代码）**：设置页、Pi 审批回传、初筛、导出 RIS/CSV/Snapshot、侧车 E2E 测试。

GitHub：**https://github.com/LawrenceLiu2005/MedCopilot**

## 本次做了什么

- **设置页**：侧车 `get_settings` / `save_settings` → 写入 `~/Library/Application Support/EvidenceCopilot/.env`；桌面「设置」按钮。
- **Pi 审批**：监听 `extension_ui_request`（confirm）→ 批准/拒绝回传 `extension_ui_response`。
- **初筛**：侧车 `update_screening` + 桌面 record 卡片四态按钮与排除原因。
- **导出**：侧车 `export_project`（ris/csv/snapshot）+ 桌面下载对话框。
- **测试**：`tests/test_sidecar.py` 新增 settings / 全链 E2E（9 项侧车相关测试通过）。
- **文档**：更新 `docs/DESKTOP.md` 完整竖切流程说明。

## 下一次建议做什么

1. 本机：`cd desktop && npm run dev`，走一遍 **设置 → 提议 → PubMed → 初筛 → 导出**。
2. 安装 Pi：`npm i -g --ignore-scripts @earendil-works/pi-coding-agent`，试「交给 Pi Agent」+ 工具批准。
3. 打 tag `desktop-v0.1.0` 触发 GitHub Actions 产出 .dmg。
4. 按 `docs/PILOT_PLAN.md` 找 10–20 位医生试用。

## 你需要知道的事

- **Release 版目前仍依赖本机 Python 3.12+**（侧车 `python3 -m src.sidecar`）；内置 Python 打包是下一 epic。
- 开发机推荐用项目 `.venv`：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。
- 桌面版不绑 Streamlit；PubMed/初筛/导出逻辑在 Python 侧车。
- Apple 开发者账号非必须；内测可右键打开未签名 .app。

## 阻塞 / 待你提供

- 首次 .dmg 需在 GitHub Release 发布，`install.sh` 才能一键下载。
- 真实 PubMed 联调需 NCBI 邮箱（桌面设置页或 `.env`）。

**命令**：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.sidecar --command ping --params '{}'
cd desktop && npm install && npm run dev
.venv/bin/pytest tests/test_sidecar.py -v
```
