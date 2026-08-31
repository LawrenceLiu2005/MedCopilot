# 演示与截图说明

## 固定演示检索

搜索页点击 **「填入示例检索」**，会使用与 E2E 验收相同的主题：

| 项目 | 内容 |
|------|------|
| 研究问题 | 2型糖尿病成人患者使用二甲双胍的随机对照试验疗效 |
| 检索式 | `(diabetes mellitus, type 2[MeSH]) AND metformin[Title/Abstract] AND randomized controlled trial[pt]` |
| 年份 | 2020 — 2024 |
| 条数 | 10 |

填好后核对「将发送给 PubMed」预览，再点 **搜索** 即可体验完整流程。

## 建议截图清单（部署后补充）

将 PNG 放入 `docs/screenshots/`，并在 [README.md](../README.md) 中引用：

1. `search-demo.png` — 搜索页（含示例检索与 Query 预览）
2. `results-screening.png` — 结果页初筛与进度条
3. `export-audit.png` — 导出区（含审计报告下载）
4. `history-diff.png` — 历史页两次检索 PMID 对比

本地截图命令示例：

```bash
streamlit run app.py
# 浏览器打开 http://localhost:8501，按上述页面截图保存到 docs/screenshots/
```
