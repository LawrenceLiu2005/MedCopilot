# Handoff — Evidence Copilot

> 新会话请先读此文件，再接上次的进度。

## 最后更新

2026-08-31

## 当前进度

**用户定义的最后一项已完成**：结果页摘要默认展开，初筛时无需再点「摘要」。MVP 核心闭环（搜 → 筛 → 导出 → 审计 → 历史对比 + 摘要可见）已全部齐全。单元测试 **79 passed**（4 项 live API 测试需联网与 NCBI 邮箱）。

GitHub：本地还没有完整 Git 仓库（仅有残缺 `.git`）。已确认 GitHub 账号 `LawrenceLiu2005` 已登录 `gh`，且尚无 `MedCopilot` 仓库。**推送因当前会话仍处计划模式、切换执行模式被拒绝而暂停。**

## 本次做了什么

- 确认部署路径：Streamlit Cloud 发链接给导师；不用 Vercel / dmg
- 核对：`.env` 已在 `.gitignore`；无 `secrets.toml`；`gh` 已登录

## 下一次建议做什么

1. 在 **Agent 模式**下执行：补全 `.gitignore`（加上 `.streamlit/secrets.toml`）→ `git init` → 首次提交 → `gh repo create MedCopilot --public --source=. --push`
2. 再按 [DEPLOY.md](DEPLOY.md) 做 Streamlit Cloud
3. 按 [docs/DEMO.md](docs/DEMO.md) 走一遍后把网址发给导师

## 你需要知道的事

- 摘要仍可手动收起 expander；PubMed 无摘要的文献会显示「摘要不可用」
- 审计报告为 Markdown，可用 Word 或浏览器「打印为 PDF」
- 对外一句话：**把 PubMed 检索变成可提交、可复查、可导出的初筛工作台**

## 阻塞 / 待你提供

- [ ] 允许切换到 Agent 模式（或你本机自己跑下面命令），才能真正提交 GitHub
- [ ] Streamlit Cloud Deploy

本机可自行执行：

```bash
cd /Users/yuchenliu/Desktop/MedCopilot
# 在 .gitignore 末尾加上：.streamlit/secrets.toml
git init
git add .
git status   # 确认没有 .env、.data/
git commit -m "Add Evidence Copilot MVP for Streamlit Cloud deploy."
gh repo create MedCopilot --public --source=. --push
```

**命令**：

```bash
pip install -r requirements.txt
streamlit run app.py
pytest -v
```
