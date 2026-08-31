# E2E 验收记录 — PRD §13

## 验收日期

2026-08-31

## 医学主题

- **研究问题**：2型糖尿病成人患者使用二甲双胍的随机对照试验疗效
- **PubMed 检索式**：`(diabetes mellitus, type 2[MeSH]) AND metformin[Title/Abstract] AND randomized controlled trial[pt]`
- **年份**：2020–2024
- **返回条数**：10

## 执行结果

| 步骤 | 结果 |
|------|------|
| PubMed 搜索 | 通过 — 总命中 440，拉回 10 篇 |
| Metadata 完整性 | 通过 — PMID、Title 等字段非空 |
| Include / Exclude 初筛 | 通过 — Include 1，Exclude 1，Unscreened 8 |
| 筛选统计 | 通过 |
| 导出 RIS | 通过 |
| 导出 CSV | 通过 |
| Search Snapshot JSON | 通过 — 含 exact_query、retrieved_pmids |
| 历史重新打开 | 通过 — 会话内 history +「打开此检索」 |

## 复现命令

```bash
# 已在 App 设置页保存邮箱（.data/workspace.json）或 .env 中配置后：
pytest tests/test_e2e_acceptance.py -v
pytest tests/test_smoke.py -v
```

## 备注

- 验收使用 NCBI E-utilities 真实 API，无 mock 数据。
- **邮箱只需填一次**：App 设置页保存后写入 workspace.json，pytest 会自动读取，无需单独维护 `.env`。
