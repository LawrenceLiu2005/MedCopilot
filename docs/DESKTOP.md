# Evidence Copilot 桌面版

> Pi 官方 Agent 内核 + Python PubMed 侧车 + Electron 原生 GUI（不绑 Streamlit）

## 用户安装（OpenCode 风格）

```bash
# 方式 1：一条命令（需 GitHub Release 已发布）
curl -fsSL https://raw.githubusercontent.com/LawrenceLiu2005/MedCopilot/main/scripts/install.sh | bash

# 方式 2：Homebrew Cask
brew install --cask evidence-copilot
# 见 packaging/homebrew/evidence-copilot.rb

# 方式 3：手动下载
# GitHub Releases → EvidenceCopilot-mac-arm64.dmg
```

**Apple 开发者账号不是必须**：内测可右键「打开」未签名 .app；大规模分发建议签名。

## 开发者环境

| 依赖 | 用途 |
|---|---|
| Python 3.12 + `pip install -r requirements.txt` | PubMed 侧车 |
| Node.js 22+ | Electron 桌面壳 |
| `@earendil-works/pi-coding-agent` | Pi 官方 CLI / RPC |

```bash
# 1. Python 侧车
pip install -r requirements.txt
python -m src.sidecar --command ping --params '{}'

# 2. Pi 扩展（项目级 .pi/agent/）
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --mode rpc   # 可选：单独测 RPC

# 3. 桌面 GUI
cd desktop
npm install
npm run dev
```

## 架构

```text
desktop/renderer     → 医学 GUI（你想研究什么 / 提议 / 确认 / 结果）
desktop/electron     → Pi RPC + 侧车 spawn
.pi/agent/extensions → TypeScript 医学工具
src/sidecar/         → Python 确定性服务（PubMed、ResearchProject）
```

数据默认写入：

- macOS: `~/Library/Application Support/EvidenceCopilot/`
- 开发: `.data/desktop/`（若 Application Support 尚不存在）

## 竖切流程（Phase 0.5）

1. **设置**：填写 NCBI 邮箱（必填）与可选 API Key / DeepSeek Key
2. 输入白话研究想法
3. `propose_pubmed_search` → 生成 PICO + 检索式提议（**不执行**）
4. 用户在界面编辑并点击「确认并执行 PubMed」
5. `run_pubmed_search(approved=true)` → 调用 NCBI E-utilities
6. 对结果逐篇初筛（Include / Maybe / Exclude + 排除原因）
7. 导出 RIS / CSV / Search Snapshot
8. 结果与审计轨迹写入 `ResearchProject`

### Pi Agent 路径

- 「交给 Pi Agent」走 Pi RPC；consequential 工具（如 `run_pubmed_search`）会弹出批准栏
- 批准/拒绝通过 `extension_ui_response` 回传 Pi

### 侧车命令一览

| 命令 | 用途 |
|---|---|
| `ping` | 健康检查 |
| `get_settings` / `save_settings` | 读写 API 密钥 |
| `propose_search` | 生成检索提议 |
| `run_pubmed_search` | 执行 PubMed（须 `approved=true`） |
| `update_screening` | 更新单篇初筛 |
| `export_project` | 导出 ris / csv / snapshot |
| `get_project` | 读取项目与审计轨迹 |

## 打包说明

**当前 .dmg 仍需要用户机器上已安装 Python 3.12+**（Electron 壳通过 `python3 -m src.sidecar` 调用侧车）。内置 Python Interpreter 打包计划在医生大规模试用前单独做。

## 打正式包

```bash
cd desktop
npm run dist:mac   # macOS .dmg
npm run dist       # 当前平台
```

GitHub Actions：打 tag `desktop-v*` 触发 [.github/workflows/desktop-release.yml](../.github/workflows/desktop-release.yml)。

## 与 Streamlit 版关系

- **Streamlit**（`app.py`）保留为 legacy 工作台，不再作为桌面 Agent 的 UI。
- **桌面版**是 v2.1 PRD 的主交付形态。
