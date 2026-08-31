# Evidence Copilot — PRD

> **医学文献可复现检索与初筛工作台**
>
> MVP 目标：让医学科研人员能够用一个真实临床问题完成 **PubMed 检索 → 文献整理 → 人工初筛 → 标准化导出**，并保留完整的检索记录。

---

## 1. 产品定位

Evidence Copilot 不是 PubMed 的替代品，也不是自动完成 Systematic Review 的 AI。

它解决的是科研过程中：

- 检索式与检索记录容易丢失
- 文献整理需要在 PubMed、Zotero/EndNote、Excel 之间反复搬运
- 初筛结果缺乏统一记录
- 导出前需要大量手工整理

因此 MVP 的核心是：

> **Reliable + Reproducible + Researcher-controlled**

AI、OpenAlex、Citation Graph 等高级功能暂不进入 MVP。

---

## 2. MVP 核心流程

```text
研究问题 / PubMed Query
        ↓
用户检查并编辑最终 Query
        ↓
PubMed API 检索
        ↓
结构化文献结果
        ↓
人工 Screening
        ↓
Include / Maybe / Exclude
        ↓
RIS / CSV / Search Snapshot
```

用户不需要理解 API、Python 或数据库。

---

## 3. 功能范围

### 3.1 Search

用户可以输入：

- Research Question（仅保存，不做 AI 解析）
- PubMed Query
- Year Range
- Result Limit：10 / 20 / 50 / 100 / 200 / 500

执行搜索前必须显示**最终实际发送给 PubMed 的 Query**，允许用户修改。

不得在后台静默修改 Query。

### 3.2 PubMed Retrieval

使用 **NCBI E-utilities 官方 API**。

流程：

```text
ESearch
→ PMID list
→ EFetch / ESummary
→ Article metadata
```

每条记录至少保存：

- PMID
- Title
- Authors
- Journal
- Publication Date / Year
- Abstract
- Publication Type
- DOI（如果 PubMed 提供）

**PMID 是核心标识符。**

禁止使用网页爬虫作为主要数据来源。

### 3.3 Results

文献以 Card 展示：

```text
Title
First Author et al.
Journal · Year

PMID
DOI

Abstract

[Open PubMed]
[Open DOI]

[Include] [Maybe] [Exclude]
```

Abstract 默认折叠。

如果 PubMed 提供结构化摘要，则保留原始 section，例如：

```text
BACKGROUND
METHODS
RESULTS
CONCLUSIONS
```

不得自行生成或改写摘要。

### 3.4 Screening

每篇文献状态：

```text
Unscreened
Include
Maybe
Exclude
```

Exclude 时允许填写：

```text
Wrong population
Wrong intervention
Wrong comparator
Wrong outcome
Wrong study design
Wrong publication type
Animal study
Not relevant
Other
```

同时支持自由文本 Notes。

注意：

> Include 只表示当前筛选阶段认为可能符合标准，不代表最终纳入 Systematic Review。

系统不得自动删除 Exclude 文献。

### 3.5 Filtering & Statistics

Results 页面支持按 Screening Status 筛选：

```text
All
Unscreened
Include
Maybe
Exclude
```

显示实时统计：

```text
Total
Unscreened
Include
Maybe
Exclude
```

### 3.6 Search History

每次成功检索保存：

```text
Search ID
Research Question
Exact PubMed Query
Year Filter
Result Limit
Executed At
Total PubMed Hits
Retrieved PMID list
```

用户可以查看历史检索。

MVP 不要求永久数据库；数据只需保留在当前 Session。

### 3.7 Export

提供三个导出：

**RIS**

用于 Zotero / EndNote 等文献管理软件。

至少包含：

```text
Title
Authors
Journal
Year
DOI
Abstract
PMID
URL
```

**CSV**

至少包含：

```text
PMID
DOI
Title
Authors
Journal
Year
Publication Type
Abstract
Screening Status
Exclusion Reason
Notes
PubMed URL
DOI URL
```

**Search Snapshot**

记录：

```text
Search Date / Time
Exact Query
Filters
Total Hits
Retrieved PMIDs
```

推荐 JSON 或 TXT。

---

## 4. 数据模型

使用 Pydantic 建立统一模型。

```python
EvidenceRecord:
    pmid: str
    doi: str | None
    title: str
    authors: list[str]
    journal: str | None
    publication_date: str | None
    publication_year: int | None
    publication_types: list[str]
    abstract: str | None

    screening_status:
        Unscreened | Include | Maybe | Exclude

    exclusion_reason: str | None
    notes: str | None

    source: str
    retrieved_at: datetime
```

原则：

> 原始 PubMed 数据与用户 Screening 数据分离。

不得因为用户修改 Screening 而改变 PubMed 原始字段。

---

## 5. 去重

MVP 只做安全的精确去重：

```text
PMID exact match
        ↓
DOI exact match
```

标题标准化可以用于提示潜在重复，但：

> **不得因为标题相似而自动删除文献。**

疑似重复应标记为：

```text
Potential Duplicate
```

而不是直接删除。

---

## 6. API 与错误处理

所有 API 请求必须：

- 设置 timeout
- 有限 retry
- 避免重复请求
- 遵守 NCBI 当前 API 使用政策
- 使用 `NCBI_EMAIL`
- API Key 从环境变量读取

环境变量：

```text
NCBI_EMAIL=
NCBI_API_KEY=
```

如果没有 API Key，仍应使用安全的默认请求速率。

API 失败时：

> 显示明确错误，不生成伪结果。

OpenAlex 等辅助数据源即使未来加入，也不得让核心 PubMed 搜索依赖它。

---

## 7. 技术栈

MVP 使用简单单体架构：

```text
Python 3.12
Streamlit
httpx
Pydantic
pandas
python-dotenv
pytest
```

可选：

```text
tenacity
```

用于 retry。

### 不要在 MVP 引入

```text
React
FastAPI
PostgreSQL
Redis
Docker
Tauri
用户账号
LLM API
OpenAlex
```

除非后续 PRD 明确要求。

---

## 8. 项目结构

```text
evidence-copilot/
│
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
│
├── src/
│   ├── models/
│   │   └── evidence.py
│   ├── clients/
│   │   └── pubmed.py
│   ├── services/
│   │   ├── search.py
│   │   ├── screening.py
│   │   └── export.py
│   └── ui/
│       ├── search.py
│       ├── results.py
│       └── history.py
│
└── tests/
    ├── test_pubmed.py
    ├── test_screening.py
    └── test_export.py
```

保持模块化，但不要过度工程化。

---

## 9. UI 原则

整体风格：

**医学科研工具，而不是 AI Chatbot。**

优先：

```text
清晰
可靠
低认知负担
数据可读
```

不要：

- 巨型 AI 聊天框
- 无意义 Dashboard
- 复杂动画
- AI 风格营销文案
- “Evidence Score” 等未经验证的评分

核心页面只需要：

```text
Search
Results
History
```

---

## 10. 科研与数据原则

这是项目最重要的约束：

### Evidence First

PubMed 原始数据优先于任何 AI 生成内容。

### Reproducibility

每次搜索必须记录：

```text
Where
When
What Query
What Filters
What Results
```

### Human in the Loop

研究者拥有最终 Screening 决定权。

### No Silent Transformation

系统不得偷偷：

- 修改 Query
- 删除文献
- 修改摘要
- 修改用户 Screening 结果

### Missing ≠ Zero

缺失的数据必须明确标记为 unavailable / null，不得猜测。

---

## 11. AI 边界

MVP **不依赖运行时 LLM**。

Cursor、Claude、GPT 等仅用于开发，不属于产品运行时组件。

未来版本可以增加：

```text
Research Question
→ PICO extraction
→ PubMed Query suggestion
→ Human confirmation
```

以及：

```text
Inclusion / Exclusion Criteria
→ AI screening suggestion
→ Human confirmation
```

但 AI 永远只能提供建议：

> **AI assists the researcher; it does not make the final evidence-screening decision.**

---

## 12. 部署

MVP 目标：

**Streamlit Community Cloud**

用户无需：

- 安装 Python
- 安装 Cursor
- 使用 Terminal
- 配置本地环境

即可打开 Web App。

---

## 13. Definition of Done

MVP 完成必须能够真实跑通：

```text
输入一个真实医学研究问题
        ↓
输入 / 编辑 PubMed Query
        ↓
执行搜索
        ↓
获得 ≤50 篇文献
        ↓
正确显示 PubMed metadata
        ↓
人工 Include / Maybe / Exclude
        ↓
填写 Exclusion Reason / Notes
        ↓
查看筛选统计
        ↓
导出 RIS
        ↓
导出 CSV
        ↓
导出 Search Snapshot
        ↓
重新查看本次检索记录
```

最终必须使用一个真实医学研究主题进行端到端测试。

---

## 14. 开发优先级

严格按照以下顺序：

```text
1. PubMed API
2. Evidence data model
3. Search
4. Results UI
5. Screening
6. Export
7. Search History
8. Error handling
9. Tests
10. UI polish
11. Deployment
```

不要在核心流程完成前开发 AI、OpenAlex、桌面客户端或复杂基础设施。

---

## 15. 产品成功标准

v1.0 不以“功能多”为成功标准。

只验证一个核心假设：

> **一个医学科研人员能否使用 Evidence Copilot，更可靠、更快速、更可复现地完成从 PubMed 检索到候选文献整理与导出的全过程。**

如果这个闭环可靠，才进入下一阶段。

---

# End
