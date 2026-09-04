# Handoff — Evidence Copilot

> 新会话请先读此文件，再接上次的进度。

## 最后更新

2026-09-04（Phase 0.5 已 commit + tag + CI 绿）

## 当前进度

**桌面版 Phase 0.5 已发版**：commit `0eb5081`，tag `desktop-v0.1.0`，GitHub Actions Desktop Release 已通过（macOS .dmg + Windows .exe artifact）。

GitHub：**https://github.com/LawrenceLiu2005/MedCopilot**

## 本次做了什么

- **收尾发版**：rebase 到 remote main → push → tag `desktop-v0.1.0`
- **CI 验证**：Desktop Release workflow #33880390661 全绿（侧车测试 + .dmg 构建）
- （此前）设置页、Pi 审批、初筛、导出、侧车 E2E 测试

## 下一次建议做什么

1. 从 GitHub Actions artifact 下载 `.dmg`，或手动创建 GitHub Release 挂上 artifact（`install.sh` 才可用）
2. 本机：`cd desktop && npm run dev`，走一遍 **设置 → 提议 → PubMed → 初筛 → 导出**
3. 按 `docs/PILOT_PLAN.md` 找 10–20 位医生试用

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
