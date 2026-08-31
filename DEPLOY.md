# Streamlit Community Cloud 部署指南

## 前置条件

1. 项目已推送到 **GitHub** 公开或私有仓库
2. 拥有 [Streamlit Community Cloud](https://share.streamlit.io) 账号（GitHub 登录）
3. NCBI 账号邮箱（[注册](https://www.ncbi.nlm.nih.gov/account/)）

## 步骤

### 1. 推送代码到 GitHub

```bash
cd MedCopilot
git init
git add .
git commit -m "Evidence Copilot MVP"
gh repo create MedCopilot --public --source=. --push
# 若 gh 未登录：gh auth login
```

### 2. 在 Streamlit Cloud 创建应用

1. 打开 [share.streamlit.io](https://share.streamlit.io) → **Create app**
2. **Repository**：选择你的 `MedCopilot` 仓库
3. **Branch**：`main`
4. **Main file path**：`app.py`

### 3. 配置 Secrets

在 App Settings → **Secrets**，粘贴（参考 [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example)）：

```toml
NCBI_EMAIL = "你的NCBI邮箱@example.com"
NCBI_API_KEY = ""
```

保存后应用会自动重启。

### 4. 验收

打开部署 URL，确认：

- 三页导航正常
- 搜索页能执行真实 PubMed 检索；**「填入示例检索」** 可一键体验二甲双胍 RCT 演示
- 结果页初筛、进度条、批量标记、**审计报告** 下载可用
- 历史页可重新打开检索；两次以上搜索后可 **检索对比**
- 导出 RIS / CSV / 检索快照 JSON 正常

## 演示主题

固定演示检索与 E2E 验收一致，详见 [docs/DEMO.md](docs/DEMO.md)：

- 研究问题：2 型糖尿病 + 二甲双胍 RCT 疗效  
- 年份 2020–2024，返回 10 篇  

部署完成后建议按 [docs/DEMO.md](docs/DEMO.md) 截取界面图放入 `docs/screenshots/`。

## 当前状态

- 部署配置文件已就绪（`requirements.txt`、`.streamlit/config.toml`、Secrets 示例）
- 应用功能与演示主题已就绪；**需你本地执行**：`gh auth login` 后推送仓库并在 Streamlit Cloud 点 Deploy

## 本地与云端环境变量对照

| 本地 `.env` | Streamlit Secrets |
|-------------|-------------------|
| `NCBI_EMAIL=` | `NCBI_EMAIL = "..."` |
| `NCBI_API_KEY=` | `NCBI_API_KEY = "..."` |
