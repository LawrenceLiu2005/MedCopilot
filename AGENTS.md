# AGENTS.md — Evidence Copilot

> Workspace folder: `MedCopilot`. Canonical product name: **Evidence Copilot**.
> Full product spec: [PROJECT_PRD.md](PROJECT_PRD.md) (Chinese).

## User preferences

- **Primary user is non-technical** — explains requirements in natural language only.
- **Always explain in plain Chinese (白话)** when communicating with the user: avoid jargon, or define it on first use.
- **Do not assume** the user knows frontend/backend, APIs, databases, or deployment concepts.

## Handoff protocol

- **File**: [HANDOFF.md](HANDOFF.md) — session continuity for humans and agents.
- **On every task completion**: update HANDOFF.md before finishing (date, 当前进度, 本次做了什么, 下一次建议做什么, 阻塞/待你提供).
- **On session start**: read HANDOFF.md immediately after AGENTS.md.
- **Sections** (keep short): 最后更新 | 当前进度 | 本次做了什么 | 下一次建议做什么 | 你需要知道的事 | 阻塞/待你提供
- **Language**: 本次做了什么 / 下一次 / 你需要知道的事 — plain Chinese (白话); technical file names OK.

## Project

Evidence Copilot is a medical literature **reproducible search and manual screening workbench**.

MVP goal: let a medical researcher complete **PubMed search → literature organization → manual screening → standardized export**, with a full search audit trail.

Core principle:

> **Reliable + Reproducible + Researcher-controlled**

This is **not** a PubMed replacement, an auto systematic-review tool, or an AI screening product.

## Hard constraints

These rules override convenience or feature ideas. See PRD §3, §6, §10, §11.

- Use **NCBI E-utilities only** for PubMed; no web scraping as the primary data source.
- **PMID** is the core identifier.
- Show the **exact query** before search; never silently modify the query.
- Never auto-delete excluded papers; never rewrite or generate abstracts.
- Keep **PubMed metadata separate** from user screening fields; screening edits must not mutate PubMed fields.
- Dedup: **PMID exact match**, then **DOI exact match** only. Title similarity may flag `Potential Duplicate` but must not remove records.
- Missing data stays `null` / unavailable; never guess. On API failure, show a clear error — **no fake results**.
- **No runtime LLM for screening or abstract rewriting.** Optional DeepSeek may suggest English PICO from a Chinese research question, and may draft extraction numbers from title + abstract and/or open/uploaded full text; the researcher must confirm; missing numbers stay empty (never 0); MeSH still comes from NCBI. Do not add AI screening. Do not bypass paywalls to fetch full text.
- **Out of scope for MVP**: React, FastAPI, PostgreSQL, Redis, Docker, Tauri, user accounts, OpenAlex. Do not add AI screening.

## MVP scope

```text
Search → PubMed E-utilities → Results → Screening → Export
                              ↘ History
```

Three UI pages only: **Search**, **Results**, **History**.

| Area | MVP behavior |
|------|--------------|
| Search | Research question (save only), PubMed query, year range, limit 10/20/50/100/200/500, manual opt-in author-field wrap (plain text only), PubMed URL import (fills form only, never auto-modifies query), sort by relevance or pub date |
| Results | Card UI, collapsed abstract, preserve structured abstract sections |
| Screening | Unscreened / Include / Maybe / Exclude + exclusion reasons + notes |
| Filter/stats | Filter by status; live Total / Unscreened / Include / Maybe / Exclude counts |
| History | Session-scoped search records; no permanent DB required |
| Export | RIS, CSV, Search Snapshot (JSON or TXT) |

Include means "possibly eligible at this stage", not final systematic-review inclusion.

## Tech stack

```text
Python 3.12 | Streamlit | httpx | Pydantic | pandas | python-dotenv | pytest
Optional: tenacity (retry)
Deploy target: Streamlit Community Cloud
```

Monolith only. Modular, but do not over-engineer.

## Project structure

```text
app.py
requirements.txt
README.md
.env.example
src/models/evidence.py
src/clients/pubmed.py
src/services/{search,screening,export}.py
src/ui/{search,results,history}.py
tests/{test_pubmed,test_screening,test_export}.py
```

## Data model contract

Implement in `src/models/evidence.py` with Pydantic. Do not invent extra fields without PRD approval.

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
    screening_status: Unscreened | Include | Maybe | Exclude
    exclusion_reason: str | None
    notes: str | None
    source: str
    retrieved_at: datetime
```

Exclusion presets: Wrong population/intervention/comparator/outcome/study design/publication type, Animal study, Not relevant, Other.

## PubMed client rules

Implement in `src/clients/pubmed.py`.

- Flow: `ESearch → PMID list → EFetch / ESummary → article metadata`
- Env vars: `NCBI_EMAIL`, `NCBI_API_KEY` (from `.env`)
- Every request: timeout, limited retry, no duplicate requests, NCBI rate-limit compliance
- Use `tenacity` if retry logic is added
- PubMed search must not depend on OpenAlex or other auxiliary sources

## UI principles

Medical research tool, **not** an AI chatbot.

Prioritize: clarity, reliability, low cognitive load, readable data.

Avoid: giant chat UI, vanity dashboards, heavy animation, AI marketing copy, unvalidated "Evidence Score" metrics.

## Development order

Do not skip ahead. PRD §14:

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

Do not build AI, OpenAlex, desktop clients, or complex infrastructure before the core loop works.

## Definition of Done

MVP is done when a **real medical research topic** completes end-to-end:

- Enter research question and edit PubMed query
- Search and retrieve ≤50 records with correct metadata
- Screen with Include / Maybe / Exclude, exclusion reason, and notes
- View screening statistics
- Export RIS, CSV, and Search Snapshot
- Re-open the search record in History

## Engineering conventions

- Code comments, `print` output, and chart labels: **Simplified Chinese**
- If Matplotlib is used: set Chinese-capable `font.sans-serif` and `axes.unicode_minus = False`
- Strip `@` from user-mentioned filenames in code strings
- No `Any` type hints without `from typing import Any`
- Keep diffs minimal; match existing module patterns
- Do not add dependencies beyond the PRD stack without approval

## Read first

- [HANDOFF.md](HANDOFF.md) — current progress and next steps (read first)
- [PROJECT_PRD.md](PROJECT_PRD.md) — full product requirements
- [AGENTS.md](AGENTS.md) — agent operating rules
- `src/models/evidence.py`, `src/clients/pubmed.py` once they exist

## Skip unless asked

- AI screening suggestions (PRD §11)
- OpenAlex, citation graph, desktop app, auth, databases, Docker

## Commands

Run from repo root after scaffold exists:

```bash
pip install -r requirements.txt
cp .env.example .env   # set NCBI_EMAIL, NCBI_API_KEY, optional DEEPSEEK_API_KEY
streamlit run app.py
pytest
```

## Required checks and response format

Before completing a task: run `pytest` when tests exist; run manual E2E on a real medical query when touching search/screening/export; never claim tests passed without executing them.

**Update HANDOFF.md before marking task complete.**

Report only: what changed, main files, test results actually run, remaining unverified items.
