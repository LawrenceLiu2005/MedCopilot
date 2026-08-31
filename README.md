# Evidence Copilot

**把 PubMed 检索变成可提交、可复查、可导出的初筛工作台**

> 你决定纳入哪些文献，系统只负责记住每一步。

---

## 这是什么？

Evidence Copilot 是 **PubMed 与 Zotero / Excel 之间的检索审计桥梁**，帮医学科研人员完成：

```text
PubMed 检索 → 核对检索式 → 人工初筛 → 导出 RIS / CSV / 审计报告
```

**三个关键词**：可靠、可复现、你说了算（不是 AI 替你决定纳入哪些文献）。

### 和 Rayyan / Covidence 的区别

| | Evidence Copilot | Rayyan / Covidence |
|--|------------------|---------------------|
| 定位 | 可复现检索 + 轻量初筛桥梁 | 全流程系统评价协作平台 |
| 协作 | 单人；可导出工作区 JSON 备份 | 多人盲筛、冲突解决 |
| AI | 无运行时 AI | 常有 AI 辅助筛文献 |
| 强项 | **检索审计留痕**、Query 预览、Search Snapshot | PRISMA 全流程、双人 κ |

我们**不替代** Covidence；适合「我要可追溯地搜 PubMed 并初筛几十到几百篇」的场景。

---

## 给谁用的？

- 做**系统综述**、**Meta 分析**的研究者  
- 需要**可追溯检索记录**（写方法学、答辩、补材料）的临床 / 基础医学科研  
- 希望在 PubMed 结果上**快速初筛**，再导出到 Zotero、EndNote 或 Excel 的人  

不需要会编程；浏览器里点选即可。

---

## 能帮你做什么？

| 功能 | 说明 |
|------|------|
| **PubMed 检索** | 执行前预览最终 Query；支持 PubMed 链接导入、作者字段包装 |
| **文献初筛** | 纳入 / 待定 / 排除 + 排除原因 + 笔记；进度条与批量标记 |
| **检索审计** | 检索快照 JSON + **人类可读审计报告**（Markdown，可贴附录） |
| **检索对比** | 历史页对比两次检索的 PMID 新增 / 消失 / 共有 |
| **标准化导出** | RIS、CSV、检索快照；导出范围可选（全部 / 纳入+待定 / 仅纳入 / 当前筛选） |

---

## 不是什么？

- **不是** AI 自动筛文献或自动写综述  
- **不是** PubMed 网站替代品  
- **不是** Rayyan / Covidence 的全流程替代品（无双人盲筛、无 PRISMA 图生成）  
- **不是** 聊天式 AI 工具  

---

## 快速试用

### 在线版（部署后）

推送到 GitHub 并在 [Streamlit Community Cloud](https://share.streamlit.io) 部署后，打开公开链接即可使用。步骤见 [DEPLOY.md](DEPLOY.md)。

### 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

1. **设置**页填写 NCBI 邮箱（只需一次，保存到 `.data/workspace.json`）  
2. **搜索**页点 **「填入示例检索」**（二甲双胍 RCT 示例，见 [docs/DEMO.md](docs/DEMO.md)）  
3. 核对 Query 预览 → **搜索**  
4. **结果**页初筛 → 下载 **审计报告** / RIS / CSV  
5. **历史**页对比两次检索（需至少搜两次）  

> **当前状态**：MVP 核心功能已完成，`pytest -v` 全部通过。进度见 [HANDOFF.md](HANDOFF.md)。

---

## 部署到 Streamlit Community Cloud

详见 [DEPLOY.md](DEPLOY.md)。简要步骤：

1. 推送项目到 **GitHub**  
2. [share.streamlit.io](https://share.streamlit.io) → Create app → Main file: `app.py`  
3. Secrets 配置 `NCBI_EMAIL`（及可选 `NCBI_API_KEY`）  
4. Deploy  

---

## 界面预览

部署或本地运行后，可按 [docs/DEMO.md](docs/DEMO.md) 补充截图至 `docs/screenshots/`。

| 页面 | 做什么 |
|------|--------|
| **搜索** | 检索式、示例一键填入、Query 预览、执行搜索 |
| **结果** | 文献卡片、初筛、进度条、批量标记、导出与审计报告 |
| **历史** | 检索记录、PMID 对比、工作区备份 |
| **设置** | NCBI 邮箱 |

---

## 项目文档

| 文档 | 说明 |
|------|------|
| [HANDOFF.md](HANDOFF.md) | 进度交接 |
| [docs/DEMO.md](docs/DEMO.md) | 演示检索与截图清单 |
| [DEPLOY.md](DEPLOY.md) | Streamlit Cloud 部署 |
| [PROJECT_PRD.md](PROJECT_PRD.md) | 完整产品需求 |
| [AGENTS.md](AGENTS.md) | 开发规则 |

---

## 给开发者

```bash
pip install -r requirements.txt
cp .env.example .env   # 可选；或在 App 设置页填邮箱
streamlit run app.py
pytest -v
```

---

*Evidence Copilot — Reliable · Reproducible · Researcher-controlled*
