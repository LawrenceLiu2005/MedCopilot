# Handoff — Evidence Copilot

> 新会话请先读此文件，再接上次的进度。

## 最后更新

2026-09-04（Phase 0.5 Release 已发布，install.sh 可用）

## 当前进度

**桌面版 Phase 0.5 已对外可装**：

- Release：https://github.com/LawrenceLiu2005/MedCopilot/releases/tag/desktop-v0.1.0
- `install.sh` 一键安装已验证（`latest/download/EvidenceCopilot-mac-arm64.dmg` 返回 200）
- 侧车测试 7/7 通过（含 propose → PubMed mock → 初筛 → 导出全链 E2E）

GitHub：**https://github.com/LawrenceLiu2005/MedCopilot**

## 本次做了什么

- **GitHub Release**：从 CI artifact 上传 `EvidenceCopilot-mac-arm64.dmg`（Windows .exe 下载因网络中断，未挂 Release）
- **install.sh 验证**：latest download URL 可 200，脚本可正常拉取
- **Homebrew cask**：修正 tag 路径 `desktop-v0.1.0`（待 commit push）
- **侧车 E2E**：`pytest tests/test_sidecar.py` 7/7 通过；ping 正常

## 下一次建议做什么

1. 本机 GUI 手动走一遍：`cd desktop && npm run dev` → 设置 → 提议 → PubMed → 初筛 → 导出（需 NCBI 邮箱）
2. 补挂 Windows `.exe` 到 Release（重试 `gh run download … EvidenceCopilot-win`）
3. 按 `docs/PILOT_PLAN.md` 找 10–20 位医生试用

## 你需要知道的事

- **Release 版仍依赖本机 Python 3.12+**（侧车 `python3 -m src.sidecar`）；内置 Python 打包是下一 epic。
- 开发机推荐用项目 `.venv`：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。
- 桌面版不绑 Streamlit；PubMed/初筛/导出逻辑在 Python 侧车。
- Apple 开发者账号非必须；内测可右键打开未签名 .app。

## 阻塞 / 待你提供

- 真实 PubMed GUI 联调需 NCBI 邮箱（桌面设置页或 `.env`）。
- Windows 安装包尚未挂 Release（macOS 已可用）。

**命令**：

```bash
# 一键安装（macOS arm64）
curl -fsSL https://raw.githubusercontent.com/LawrenceLiu2005/MedCopilot/main/scripts/install.sh | bash

# 开发
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.sidecar --command ping --params '{}'
cd desktop && npm install && npm run dev
.venv/bin/pytest tests/test_sidecar.py -v
```
