# Evidence Copilot — Product Requirements Document (PRD)

**Version:** 2.1  
**Product stage:** MVP → Research Agent  
**Architecture direction:** Pi-based Agent Kernel + Research Environment  
**Primary audience:** Clinical researchers, clinicians, research teams, hospital research platforms  
**Status:** Strategic product specification

---

## 1. Product Definition

> **Evidence Copilot is an AI Research Agent for clinicians that turns an unstructured research idea into an evidence-backed, feasible, and executable research project, while keeping the researcher in control of all consequential decisions.**

The product should allow a clinician to say, in plain language:

> “I want to study this.”

The system then helps answer:

1. What exactly is the research question?
2. What has already been studied?
3. Are there existing systematic reviews or meta-analyses?
4. Is the proposed question sufficiently novel?
5. Where are the unresolved gaps?
6. What study designs could answer the question?
7. What data and variables would be required?
8. Can the user's available cohort/database support the study?
9. What statistical analysis would be appropriate?
10. What should the researcher do next?

The long-term product is therefore not simply an AI literature search tool. It is a **research workflow and decision-support layer** for clinical researchers.

---

# 2. Product Vision

Evidence Copilot should reduce the cognitive and operational burden of clinical research without reducing scientific accountability.

The core product philosophy is:

> **医生不需要学会使用 AI；医生只需要会提出科研问题。**

The product should hide unnecessary technical complexity while exposing every consequential research decision.

The intended journey is:

```text
Research Idea
    ↓
Research Triage
    ↓
Question Structuring
    ↓
Evidence Landscape
    ↓
Existing Reviews / Studies
    ↓
Novelty & Research Gap
    ↓
Study Design Recommendation
    ↓
Data / Cohort Feasibility
    ↓
Variable Feasibility
    ↓
Statistical Plan
    ↓
Human Approval
    ↓
Research Execution
    ↓
Literature Search
    ↓
Screening
    ↓
Extraction
    ↓
Analysis
    ↓
Research Dossier
```

This is the target architecture, not a requirement to implement the entire chain in one release.

---

---

# 4. Agent Architecture Decision

## 4.1 Core Decision

Evidence Copilot should **reuse an open-source Pi Agent architecture as the Agent Kernel**, rather than building a new Agent loop/framework from scratch.

The architectural principle is:

> **Keep the Agent kernel small; make the Research Environment rich.**

Pi is treated as an implementation substrate for the agent loop, tool execution, session/context handling, and extensibility. Evidence Copilot owns the domain-specific research state, evidence model, provenance, permissions, and clinical-research workflow.

This means the product is **not “a wrapper around Pi”**. Pi is an internal runtime dependency. The product abstraction exposed to clinicians is the Research Project.

## 4.2 Why Pi

The product does not need a large general-purpose multi-agent framework at the current stage.

The core research agent needs to repeatedly perform a small set of primitive operations:

```text
READ
  ↓
inspect evidence, project state, papers, data

WRITE
  ↓
create research artifacts and evidence records

EDIT
  ↓
revise questions, plans, criteria, and artifacts

EXECUTE
  ↓
run searches, data operations, scripts, and deterministic analysis
```

The important capability is not the number of tools. It is the quality of the environment in which those tools operate.

Therefore the first implementation should preserve the minimal Pi-style Agent Kernel and progressively add a controlled Research Environment around it.

## 4.3 Do Not Fork the Core Aggressively

Evidence Copilot should avoid rewriting the Agent loop unless a concrete requirement cannot be satisfied through configuration, extensions, adapters, or surrounding services.

Preferred order:

1. Configure existing Pi behavior.
2. Add extensions / adapters.
3. Add Research-specific tools.
4. Add a ResearchProject persistence layer.
5. Add policy, audit, and sandbox controls.
6. Only then modify the core Agent runtime when necessary.

The objective is to retain upstream compatibility and minimize framework maintenance burden.

## 4.4 Research Environment

The Agent Kernel should operate inside an Evidence Copilot Research Environment containing:

```text
                    Research Agent
                         │
                    Pi Agent Kernel
                         │
                ┌────────┴────────┐
                │ Research Harness│
                └────────┬────────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
 Evidence Services   Research State    Execution Layer
       │                 │                 │
 PubMed / PMC       ResearchProject     Python / R
 ClinicalTrials     EvidenceItem        deterministic stats
 Full text          SearchRun           data processing
                   ScreeningDecision
                   ResearchDecision
```

The Research Environment is responsible for ensuring that Agent actions are:

- evidence-backed;
- attributable to a source;
- reproducible where applicable;
- persisted as structured state;
- subject to human approval when consequential;
- constrained by security and permission policy.

## 4.5 Product State Is Not Agent State

The Agent runtime must not become the system of record for the research project.

The durable source of truth should be the Evidence Copilot domain model:

```text
ResearchProject
├── ResearchIdea
├── ResearchQuestion
├── EvidenceItem
├── SearchRun
├── ExistingReview
├── ResearchGap
├── StudyDesign
├── Dataset
├── Variable
├── ScreeningDecision
├── Extraction
├── AnalysisPlan
├── AnalysisRun
└── AuditEvent
```

The Agent can hold transient working context, but every consequential research artifact must be persisted independently.

This allows the product to change Agent frameworks in the future without migrating the underlying research record.

## 4.6 Agent vs Deterministic Tool Boundary

LLMs should decide and explain; deterministic systems should retrieve, calculate, validate, and persist.

The default boundary is:

```text
LLM / Agent
    │
    ├── interpret research intent
    ├── propose next action
    ├── synthesize evidence
    ├── identify uncertainty
    └── request human approval
             │
             ▼
Deterministic Services
    │
    ├── PubMed retrieval
    ├── full-text retrieval
    ├── metadata parsing
    ├── deduplication
    ├── database inspection
    ├── statistical computation
    ├── chart generation
    └── persistence
```

The Agent must not be trusted as the calculator, database, or evidence store.

## 4.7 Human Approval as a First-Class Runtime Event

The Agent must be able to pause before consequential actions and resume after explicit researcher approval.

Examples:

```text
Research Question proposed
        ↓
     APPROVAL
        ↓
Evidence search

Research Gap proposed
        ↓
     APPROVAL
        ↓
Study Design

Screening criteria proposed
        ↓
     APPROVAL
        ↓
Screening execution
```

Human approval must create an auditable ResearchDecision rather than merely a chat message.

## 4.8 Security and Execution Policy

A generic command-execution primitive must not imply unrestricted production access.

Before institutional deployment, the Research Harness must provide:

- command allowlists / denylists or equivalent policy enforcement;
- isolated execution for Python/R and other processes;
- network access controls;
- credential isolation;
- resource/time limits;
- audit logging;
- explicit handling of sensitive institutional data.

The initial MVP may run with a simpler local execution model, but the architecture must not assume unrestricted shell access is acceptable in a hospital environment.

## 4.9 Coding-Agent-Assisted Development

The Pi-based architecture is intentionally suitable for modification by coding agents.

The development loop should be:

```text
Product requirement
        ↓
Coding Agent reads repository + architecture rules
        ↓
Small implementation task
        ↓
Tests
        ↓
Run / inspect
        ↓
Review
        ↓
Next task
```

Coding agents are implementation tools, not part of the Evidence Copilot runtime.

The coding agent should be instructed to preserve:

- ResearchProject as the durable product abstraction;
- Evidence provenance;
- No Silent Transformation;
- Human-in-the-loop controls;
- deterministic computation boundaries;
- tests around every consequential behavior.

## 4.10 Initial Technical Stack

Preferred starting architecture:

```text
Frontend
  → React / Next.js or existing MVP UI

Application API
  → FastAPI / Python

Agent Kernel
  → Pi-based runtime

Persistence
  → PostgreSQL

Evidence APIs
  → PubMed / PMC / ClinicalTrials.gov and future sources

Deterministic Analysis
  → Python + R

Artifact / Full-text Storage
  → object storage or controlled filesystem

Observability
  → structured logs + audit events
```

The exact framework choices are implementation decisions and should not be allowed to distort the ResearchProject domain model.
---

# 4. Background and Existing MVP

The current Evidence Copilot MVP is a reproducible PubMed workflow:

```text
PubMed Search
    ↓
Query Review
    ↓
Structured Results
    ↓
Manual Screening
    ↓
RIS / CSV / Search Snapshot
```

The current README defines the product as a bridge between PubMed and Zotero / Excel, with three core principles:

- Reliable
- Reproducible
- Researcher-controlled

The current MVP already supports PubMed retrieval, manual screening, audit snapshots/reports, search comparison, and standardized exports.

The existing PRD defines the MVP goal as allowing a researcher to complete:

> **PubMed 检索 → 文献整理 → 人工初筛 → 标准化导出**

while retaining complete search records.

The current MVP should **not be discarded**. It becomes the Search Execution Layer of the future Research Agent.

---

# 5. Problem Statement

Clinical researchers commonly work across fragmented tools:

```text
Clinical observation
    ↓
ChatGPT / Gemini
    ↓
PubMed
    ↓
Google Scholar
    ↓
Zotero / EndNote
    ↓
Excel
    ↓
R / Python / RevMan
    ↓
Manuscript
```

The major problem is not merely that individual tools are weak.

The problem is that the researcher must act as the integration layer.

The researcher has to decide:

- what to search;
- how to search;
- whether enough evidence exists;
- whether the question is novel;
- which studies matter;
- whether a systematic review is warranted;
- whether a cohort study is feasible;
- which variables are required;
- which analysis is appropriate;
- what should happen next.

The product opportunity is therefore to reduce **research coordination cost**, not merely search cost.

---

# 6. Target Users

## 6.1 Primary Users

### Clinical researchers

Doctors who conduct clinical research but do not have dedicated research assistants.

Typical examples:

- Residents
- Attending physicians
- Clinical master's students
- Clinical PhD students
- Principal investigators
- Physician-scientists

### Research teams

Small teams consisting of:

- PI / mentor
- Clinical researchers
- Graduate students
- Research assistants

### Institutional users

Long-term targets include:

- Hospital research platforms
- Clinical research centers
- Medical schools
- Institutional research offices

---

# 7. User Jobs to Be Done

The core job is not:

> “Search PubMed.”

The core job is:

> **“I have a clinical research idea. Help me determine whether it is worth doing and what I should do next.”**

Secondary jobs include:

- Find relevant evidence.
- Identify prior reviews.
- Avoid duplicating existing work.
- Refine a vague research question.
- Select an appropriate study design.
- Assess cohort/database feasibility.
- Define required variables.
- Build a reproducible search strategy.
- Screen literature.
- Extract data.
- Perform statistical analysis.
- Preserve the research audit trail.
- Produce a reusable research package.

---

# 8. Product Principles

## 8.1 Evidence First

Primary evidence and authoritative source data take precedence over AI-generated statements.

AI-generated content is an interpretation, recommendation, or draft unless explicitly confirmed by the researcher.

---

## 8.2 Human in the Loop

AI can:

- Search
- Summarize
- Recommend
- Rank
- Draft
- Extract
- Propose

The researcher retains final authority over consequential scientific decisions.

---

## 8.3 No Silent Transformation

The system must never silently:

- Change the research question.
- Change a search query.
- Delete evidence.
- Modify an abstract.
- Modify a screening decision.
- Convert missing values to zero.
- Change a research design.
- Start a consequential analysis without confirmation.

The user must be able to distinguish:

```text
Original user input
        ↓
AI interpretation
        ↓
AI recommendation
        ↓
Human confirmation
        ↓
Confirmed research state
```

---

## 8.4 Everything Traceable

Important conclusions and actions must be traceable to:

- Source
- Time
- Query
- Filters
- Evidence
- User decision
- AI recommendation
- Version
- Analysis configuration

---

## 8.5 Missing ≠ Zero

The system must distinguish:

- Not reported
- Not found
- Missing
- Unknown
- Zero
- Negative result

Absence of evidence must not be represented as evidence of absence.

---

## 8.6 Researcher-Controlled

Evidence Copilot should assist the researcher rather than become an autonomous authority.

The product must optimize for:

> **Researcher control + machine assistance**

rather than:

> **Machine autonomy + researcher approval after the fact**

---

# 9. Product Positioning

Evidence Copilot is:

> **A zero-learning-curve Research Agent for clinicians.**

It is not:

- A replacement for PubMed.
- A generic chatbot.
- An autonomous scientist.
- A fully automated systematic review platform.
- A substitute for statistical software.
- A substitute for clinical judgment.
- A tool that decides which evidence is true.

The product should feel like a **clinical research workspace**, not an AI chatbot.

---

# 10. Competitive Positioning

The competitive landscape contains several categories:

| Category | Examples | Primary strength |
|---|---|---|
| Literature databases | PubMed, Google Scholar | Evidence discovery |
| Research AI | Elicit and similar systems | Search, synthesis, research assistance |
| Systematic review platforms | Rayyan, Covidence, Nested Knowledge | Review workflow |
| Statistical tools | R, Python, RevMan, Stata | Analysis |
| Reference managers | Zotero, EndNote | Reference organization |
| General AI | ChatGPT, Gemini | General reasoning and generation |
| Evidence Copilot | — | Research problem → decision → executable workflow |

The product must not claim that competitors cannot perform AI search, screening, extraction, or systematic review.

The defensible direction is narrower:

> **Start with an underspecified clinical research idea and manage the reasoning and workflow required to turn it into a feasible research project.**

---

# 11. Core Product Experience

## 11.1 Home

The primary interaction should be:

> **你想研究什么？**

Example:

> “我想研究肝癌术后某类患者的复发风险。”

Primary action:

> **开始评估**

Secondary area:

- Recent research projects
- Continue project
- Saved research ideas

The interface should avoid a giant AI chat box.

---

# 12. Research Triage

Research Triage is the highest-priority future capability.

Its purpose is to answer:

> **“这个科研想法值得继续做吗？”**

Input:

```text
Natural-language research idea
```

Output:

1. Interpreted research question.
2. Existing evidence.
3. Existing reviews.
4. Existing meta-analyses.
5. Major studies.
6. Recent developments.
7. Potential novelty.
8. Research gaps.
9. Potential study designs.
10. Immediate next steps.

---

# 13. Research Question Understanding

The system should transform natural language into a structured draft.

Example:

```text
Original:
“我想研究肝癌术后哪些患者更容易复发。”

Agent interpretation:

Population:
Patients with HCC undergoing liver resection

Exposure:
Candidate prognostic factors

Outcome:
Postoperative recurrence

Time:
Postoperative follow-up

Uncertainty:
Exposure definition not yet specified
Outcome definition not yet specified
```

The system must explicitly label uncertainty.

It must not silently convert the vague question into a more specific research question.

---

# 14. Evidence Landscape

After question understanding, the Agent should construct an evidence landscape.

It should identify, where supported:

- Systematic reviews
- Meta-analyses
- Randomized trials
- Cohort studies
- Case-control studies
- Diagnostic studies
- Prediction studies
- Guidelines
- Clinical trials
- Recent high-relevance publications

The user should be able to see:

```text
What has been studied?
What populations were studied?
What exposures/interventions were studied?
What outcomes were studied?
What methods were used?
What remains uncertain?
```

---

# 15. Existing Review Discovery

The Agent should specifically identify:

- Systematic Reviews
- Meta-analyses
- Umbrella Reviews
- Scoping Reviews
- Guidelines

It must distinguish between:

> “A review exists in this general topic”

and:

> “The exact research question has already been adequately answered.”

The existence of a review does not automatically mean that a research question is saturated.

---

# 16. Novelty Analysis

The system should avoid arbitrary “novelty scores”.

Instead, it should produce evidence-backed reasoning.

Example:

> “The broad association between X and Y has already been extensively studied.”

Then:

> “However, existing studies primarily involve population A.”

> “Evidence in population B is limited.”

> “Existing studies also use inconsistent definitions of outcome C.”

Possible novelty dimensions:

- Population
- Exposure
- Comparator
- Outcome
- Time horizon
- Geography
- Subgroup
- Study design
- Data source
- Methodology
- New intervention
- New biomarker
- New causal question

---

# 17. Research Gap

A research gap must be supported by evidence.

The system should show:

```text
Research Gap
    ↓
Supporting studies
    ↓
Why the gap exists
    ↓
Potential research question
```

The Agent must never invent a gap merely because a search result was incomplete.

---

# 18. Research Question Refinement

The user should be able to accept or modify an Agent recommendation.

Interface:

```text
Your original question

↓

Agent's proposed refinement

↓

Reason for refinement

↓

Supporting evidence

[Accept] [Edit]
```

Only the confirmed version becomes the canonical Research Question.

---

# 19. Study Design Recommendation

The Agent may recommend potential study designs such as:

- Retrospective cohort
- Prospective cohort
- Case-control
- Cross-sectional study
- Randomized controlled trial
- Systematic review
- Meta-analysis
- Diagnostic accuracy study
- Prediction model
- Survival analysis

For each candidate design, the system should explain:

- Why it fits the question.
- What data are required.
- Main strengths.
- Main limitations.
- Potential biases.
- Expected feasibility.
- Key methodological risks.

The system should recommend, not dictate.

---

# 20. Data / Cohort Feasibility

A major differentiating capability should be:

> **Can this research actually be done with the user's data?**

The user may provide:

- Cohort description.
- Database description.
- Sample size.
- Date range.
- Variable list.
- Follow-up information.
- Outcome definitions.

The Agent should map:

```text
Research Question
        ↓
Required Variables
        ↓
Available Variables
        ↓
Definition Compatibility
        ↓
Missingness / Quality
        ↓
Feasibility
```

---

# 21. Variable Feasibility

The system should create a structured variable matrix.

Example:

| Variable | Required | Available | Definition compatible | Status |
|---|---:|---:|---:|---|
| Age | Yes | Yes | Yes | Ready |
| Sex | Yes | Yes | Yes | Ready |
| AFP | Yes | Yes | Yes | Ready |
| Recurrence | Yes | Yes | Partial | Review |
| Biomarker X | Yes | No | — | Blocked |

The system should explain blockers.

It should not produce an unsupported single-number “feasibility score”.

---

# 22. Research Plan

Once the user confirms the research question, gap, design, and feasibility, Evidence Copilot should produce a structured Research Plan.

The Research Plan should contain:

- Research question
- Background
- Hypothesis
- Population
- Exposure / intervention
- Comparator
- Outcome
- Study design
- Inclusion criteria
- Exclusion criteria
- Variables
- Confounders
- Statistical plan
- Sensitivity analyses
- Potential limitations
- Evidence supporting the plan

The Research Plan is a structured editable object, not merely generated prose.

---

# 23. Research Project Object

The central data object should evolve from the current Search-centric model to a Research Project model.

```text
ResearchProject
├── ResearchQuestion
├── EvidenceLandscape
│   ├── EvidenceItem
│   └── SearchRun
├── ResearchGap
├── StudyDesign
├── Dataset
│   └── Variable
├── ResearchPlan
├── Screening
├── Extraction
├── Analysis
└── AuditTrail
```

---

# 24. Research State Machine

Every project should have an explicit state.

```text
IDEA
  ↓
TRIAGED
  ↓
QUESTION_DEFINED
  ↓
EVIDENCE_REVIEWED
  ↓
GAP_IDENTIFIED
  ↓
DESIGN_PROPOSED
  ↓
FEASIBILITY_CHECKED
  ↓
PLAN_APPROVED
  ↓
SEARCHING
  ↓
SCREENING
  ↓
EXTRACTION
  ↓
ANALYSIS
  ↓
COMPLETED
```

The system should always tell the user:

> **“你现在处于科研流程的哪一步。”**

---

# 25. Literature Search Execution

The current PubMed MVP becomes the execution layer.

Workflow:

```text
Confirmed Research Question
        ↓
PICO / Search Concept
        ↓
MeSH / Free-text suggestions
        ↓
Editable Query
        ↓
Human confirmation
        ↓
PubMed execution
        ↓
Structured results
```

The actual query sent to PubMed must always be visible before execution.

No silent query modification.

---

# 26. Screening

Current screening model remains:

- Include
- Maybe
- Exclude
- Exclusion reason
- Notes

Future AI assistance:

```text
AI screening suggestion
        ↓
Human review
        ↓
Confirmed decision
```

AI must not become the final screening authority.

---

# 27. Full-text Retrieval

Permitted sources:

- PMC
- Unpaywall
- User-uploaded PDF
- Institutionally accessible full text

The system must not bypass paywalls.

Every extracted evidence item should retain its source.

---

# 28. Data Extraction

AI may propose extraction drafts for:

- Sample size
- Mean / SD
- Event counts
- OR
- RR
- HR
- Confidence intervals
- Follow-up
- Baseline characteristics
- Other structured study data

Workflow:

```text
Paper
 ↓
AI extraction draft
 ↓
Source passage
 ↓
Human verification
 ↓
Confirmed extraction
```

The system must preserve:

- Source paper
- Source passage
- Model
- Prompt/version
- Draft value
- Human-confirmed value

Missing information remains missing.

---

# 29. Meta-analysis

Meta-analysis is an execution module, not an autonomous AI conclusion.

Workflow:

```text
Included Studies
    ↓
Extraction Table
    ↓
Human Confirmation
    ↓
Effect Size
    ↓
Statistical Model
    ↓
Pooling
    ↓
Forest Plot
    ↓
Heterogeneity
    ↓
Sensitivity Analysis
    ↓
Publication Bias
```

Statistical calculations must be performed by deterministic statistical software.

LLMs must not be relied upon for arithmetic.

---

# 30. Analysis Principles

Analysis should preserve:

- Input dataset version.
- Inclusion criteria.
- Analysis configuration.
- Statistical method.
- Software version.
- Output.
- Human confirmation.

Every analysis should be reproducible.

---

# 31. Research Dossier

The final deliverable should be a structured Research Dossier rather than a chat transcript.

It should include:

### Research Question

Confirmed research question and revisions.

### Evidence Landscape

Key evidence and sources.

### Existing Research

Relevant reviews and major studies.

### Research Gap

Evidence-backed unresolved questions.

### Study Design

Recommended and selected design.

### Data Feasibility

Available and missing variables.

### Research Plan

Protocol-level structured plan.

### Search Strategy

Queries, databases, dates and filters.

### Screening

Screening history and decisions.

### Extraction

Confirmed extraction table.

### Analysis

Statistical methods and outputs.

### Audit Trail

Important research decisions and their history.

---

# 32. Audit Trail

Every consequential action should create an audit event.

Example:

```text
09:21
User entered research question.

09:23
Agent generated PICO draft.

09:25
User modified Population.

09:28
Agent searched PubMed.

09:30
User approved search query.

09:31
PubMed search executed.

09:38
User excluded PMID XXXXX.

Reason:
Wrong population.
```

The audit trail is part of the research artifact, not merely an engineering log.

---

# 33. AI Permission Model

| Action | AI | Human confirmation |
|---|---:|---:|
| Research interpretation | Yes | Yes |
| Search suggestion | Yes | Yes |
| Search execution | Yes | Yes |
| Screening suggestion | Yes | Yes |
| Final screening | No | Yes |
| Extraction draft | Yes | Yes |
| Final extraction | No | Yes |
| Study design recommendation | Yes | Yes |
| Final study design | No | Yes |
| Statistical calculation | Tool | Yes |
| Final analysis interpretation | Yes | Yes |

---

# 34. UI Requirements

The interface should resemble a medical research tool.

Priorities:

1. Clear
2. Reliable
3. Low cognitive load
4. Data-readable
5. Explicit state
6. Traceable evidence

Avoid:

- Giant AI chat boxes.
- Decorative dashboards.
- Excessive animation.
- Marketing language.
- Unsupported evidence scores.
- “Magic” buttons that conceal consequential actions.

The core interface should be a **Research Workspace**.

---

# 35. Research Workspace

Suggested structure:

```text
┌───────────────────────────────────────────┐
│ Research Project                          │
├───────────────────────────────────────────┤
│ Question                                  │
│ Evidence                                  │
│ Research Gap                              │
│ Study Design                              │
│ Data                                     │
│ Analysis                                 │
│ Audit                                    │
├───────────────────────────────────────────┤
│ Current stage: Research Design             │
│                                           │
│ [Continue]                                │
└───────────────────────────────────────────┘
```

Chat can exist as an interaction mechanism, but it must not become the product's primary information architecture.

---

# 36. Evidence Provenance

Every evidence-derived claim should expose:

- Source
- PMID / DOI where applicable
- Publication
- Relevant passage
- Retrieval date
- Search strategy
- AI interpretation, if any

The user should be able to move from:

> “Agent says X”

to:

> “Here is the evidence supporting X.”

---

# 37. Research Decision Provenance

The system should distinguish:

```text
Evidence
↓
AI interpretation
↓
AI recommendation
↓
Human decision
```

This is different from simply logging model messages.

The goal is to reconstruct:

> **How did this research project arrive at its current state?**

---

# 38. Security and Privacy

Institutional deployments must support:

- Authentication
- Authorization
- Role-based access
- Project-level permissions
- Audit logs
- Data isolation
- API key protection
- No exposure of credentials in snapshots
- Appropriate handling of sensitive clinical data

Patient-level data must not be sent to external model providers without an appropriate institutional and legal basis.

A future institutional version should support controlled model/provider configuration.

---

# 39. Institutional Deployment

Potential deployment models:

### Public cloud

Best for early validation.

### Institution-managed environment

Best for sensitive research workflows.

### Private deployment

Potential long-term enterprise offering.

The architecture should avoid making private deployment impossible, even if MVP uses a simple hosted environment.

---

# 40. Current MVP Definition of Done

The current MVP remains complete when it can reliably perform:

```text
Real medical research question
        ↓
Input / edit PubMed Query
        ↓
Execute search
        ↓
Retrieve ≤50 papers
        ↓
Display correct PubMed metadata
        ↓
Include / Maybe / Exclude
        ↓
Exclusion reason / Notes
        ↓
Screening statistics
        ↓
RIS export
        ↓
CSV export
        ↓
Search Snapshot
        ↓
Reopen search history
```

The current PRD explicitly defines this end-to-end validation using a real medical research topic.

---

# 41. Product Roadmap

## Phase 0 — Current MVP

Goal:

> Prove reliable and reproducible literature search.

Scope:

- PubMed API
- Search
- Results
- Screening
- Export
- Search history
- Audit snapshot
- Error handling
- Tests
- Deployment

Do not expand the MVP unnecessarily.

---

## Phase 0.5 — Pi Agent Kernel Integration

Before expanding Research Triage, establish the Agent foundation without replacing the current deterministic MVP.

Deliverables:

- Integrate the Pi-based Agent Kernel as an isolated runtime component.
- Implement Research Harness boundaries.
- Define ResearchProject persistence independently of Agent state.
- Implement the first Research Environment tools around the existing PubMed capability.
- Add human approval / interrupt semantics for consequential actions.
- Add structured Agent event and audit logging.
- Add sandbox / execution policy for any shell, Python, or R execution.
- Add end-to-end test: research idea → search proposal → human approval → PubMed execution → evidence records.
- Ensure the existing Search / Results / History MVP remains usable without the Agent.

Exit criteria:

> The Agent can perform a real research-search task while every consequential state change remains inspectable, reproducible, and independently persisted.

## Phase 1 — Research Triage

Goal:

> Prove that clinicians will give Evidence Copilot real research ideas.

Scope:

- Natural-language research idea
- Question understanding
- Evidence search
- Existing review discovery
- Evidence landscape
- Research gap analysis
- Research question refinement
- Suggested next steps

Primary validation metric:

> Does the user return with another real research question?

---

## Phase 2 — Research Planning

Goal:

> Move from “interesting idea” to “feasible research project”.

Scope:

- Study design recommendation
- Database/cohort feasibility
- Variable feasibility
- Research Plan
- Statistical plan
- Structured project state

---

## Phase 3 — Research Execution

Goal:

> Execute the approved research plan.

Scope:

- Advanced literature search
- AI-assisted screening
- Full-text retrieval
- Extraction
- Meta-analysis
- Statistical workflows
- Reproducible analysis

---

## Phase 4 — Institutional Research Infrastructure

Goal:

> Become part of the institutional clinical research workflow.

Scope:

- Institutional databases
- Cohort discovery
- Permissions
- Team collaboration
- Institutional knowledge
- Private deployment
- Governance
- Security
- Audit
- Research project management

---

# 42. Metrics

Avoid optimizing for:

- DAU
- Number of chats
- Token consumption
- Number of generated answers
- Time spent in app

These metrics can increase while scientific value decreases.

Primary metrics:

## Research Idea → Useful Decision Rate

Percentage of users who report that the first Research Triage produced a useful research decision.

Initial target:

> ≥70%

---

## Return Research Rate

Percentage of first-time users who return with another research question.

Initial target:

> ≥50%

---

## Real Project Conversion

Percentage of users who hand a real research project to the system after triage.

Initial target:

> ≥30%

---

## Sustained Usage

Percentage of users who continue using the product for more than one month.

Initial target:

> ≥20%

---

## Research Milestones Progressed

Count of projects moved from:

```text
Idea
→ Question
→ Feasible Design
→ Protocol
→ Data
→ Analysis
```

This should become the long-term North Star Metric.

---

# 43. North Star Metric

> **Research Projects Progressed**

The product's purpose is not to maximize interactions.

Its purpose is to move real clinical research projects forward.

---

# 44. Validation Plan

The next major validation should not be another feature sprint.

Run a real-world pilot.

Suggested cohort:

> 10–20 real clinicians / clinical researchers.

Duration:

> Approximately 3 months.

Track:

- Research ideas submitted.
- Triage completion.
- Research gaps identified.
- Projects abandoned after evidence review.
- Projects redesigned.
- Projects entering protocol design.
- Projects entering data analysis.
- Repeat usage.
- Human overrides.
- AI errors.
- Trust failures.
- Reasons for abandoning the product.

---

# 45. Critical Success Signal

The strongest possible user feedback is not:

> “这个 AI 很聪明。”

It is:

> **“我本来想做 A，它告诉我 A 已经被做得差不多了，然后帮我找到了 B；而 B 正好是我们科室有数据、也真正能做的。”**

That demonstrates value at the research-decision level.

---

# 46. Failure Signals

The project should be reconsidered if:

1. Users say the product is impressive but do not return.
2. Users only use it when the founder personally assists them.
3. Users immediately return to ChatGPT/Gemini/PubMed.
4. No real research projects are handed to the system.
5. Users use the tool only as a nicer PubMed interface.
6. AI recommendations are not trusted.
7. Evidence provenance is considered too cumbersome.
8. The product saves search time but does not change research decisions.

---

# 47. Commercial Strategy

The product should not assume individual subscription as its default business model.

The likely value structure is:

```text
Free individual use
        ↓
Real research adoption
        ↓
Research project / team usage
        ↓
Institutional deployment
```

Potential monetization:

### Individual

Free or low-cost access for adoption.

### Research Project

Paid project-level advanced workflows.

### Research Team

Paid shared workspaces for PI + students + research assistants.

### Institution

Hospital / university / clinical research platform licensing.

### Enterprise / Private Deployment

Institution-controlled deployment, data governance, security and integrations.

The product should sell:

> **Research workflow capability**

rather than:

> **AI tokens**

---

# 48. Why Not Subscription First?

Clinical research is not necessarily a high-frequency consumer workflow.

A researcher may work intensely on one project for weeks or months and then switch projects.

Therefore, a monthly subscription can create the wrong product incentive.

The long-term value may be better represented by:

- Research projects.
- Teams.
- Institutional workflows.
- Data infrastructure.
- Governance.
- Research output.

The product should validate user value before locking itself into a pricing model.

---

# 49. Potential Institutional Value

For a hospital or research institution, the product can potentially provide:

- Standardized research workflows.
- Reproducible evidence search.
- Lower research-assistant workload.
- Better documentation.
- More consistent screening/extraction.
- Research project traceability.
- Institutional knowledge accumulation.
- Controlled AI usage.
- Research governance.

The strategic product is therefore potentially:

> **Clinical Research Infrastructure**

rather than:

> **Another AI SaaS application.**

---

# 50. Competitive Moat

The following are useful but weak moats:

- Simple UI
- Natural-language input
- AI literature search
- AI summarization
- Zero-learning-curve UX

These can be copied.

Potentially stronger moats:

### 49.1 Research Workflow State

The system understands where every project is in its lifecycle.

### 49.2 Evidence Provenance

Every important conclusion can be reconstructed.

### 49.3 Clinical Research Workflow Knowledge

The system learns the operational structure of real clinical research.

### 49.4 Data / Cohort Knowledge

The system understands which research questions require which variables and which institutional datasets can support them.

### 49.5 Institutional Integration

Permissions, databases, governance and research workflows become difficult to replace.

### 49.6 Evaluation Dataset

Over time:

```text
Research question
    ↓
Agent recommendation
    ↓
Expert decision
    ↓
Actual research outcome
```

can become a high-value evaluation and improvement dataset.

---

# 51. Key Strategic Risk

The biggest competitor is not another application.

It is:

```text
Doctor
+
ChatGPT / Gemini
+
PubMed
+
Google Scholar
+
Zotero
+
Excel
+
R / Python
+
Research assistant
```

This combination is flexible and already embedded in user habits.

Therefore Evidence Copilot must not merely demonstrate:

> “We can do this.”

It must demonstrate:

> **“We remove enough coordination cost that the old workflow is no longer worth returning to.”**

---

# 52. Product Strategy Summary

Evidence Copilot should not attempt to win by having the most AI features.

It should win by owning the transition:

```text
Unstructured clinical idea
          ↓
Structured research problem
          ↓
Evidence-backed decision
          ↓
Feasible study design
          ↓
Executable research project
```

The current PubMed MVP is the foundation.

Research Triage is the next strategic bet.

Research Planning is the next expansion.

Research Execution is the eventual full workflow.

Institutional Research Infrastructure is the long-term commercial opportunity.

---

# 53. Final Product Thesis

The product thesis is:

> **医生不缺 AI。医生缺的是一个懂科研工作流、能够替他处理复杂度，同时又不替他偷偷做决定的 Research Agent。**

Evidence Copilot should therefore be built around one central promise:

> **“你只需要告诉我你想研究什么；我帮你判断这个问题值不值得做、还能怎么做、你的数据能不能做，以及下一步应该做什么。”**

The ultimate product is not an AI that “does research instead of the doctor”.

It is an AI that makes the doctor substantially better at navigating research.

---

# 54. Immediate Next Step
The immediate engineering task is **not** to build the complete Research Agent.

First build a small Pi-based vertical slice:

```text
Doctor research idea
      ↓
Research Agent
      ↓
Read current project context
      ↓
Propose PubMed search
      ↓
Human approval
      ↓
Execute existing PubMed service
      ↓
Persist SearchRun + EvidenceItems
      ↓
Show result in the existing Results UI
```

The first coding-agent task should therefore be to integrate the Pi Agent Kernel without disturbing the current MVP. The second should establish the ResearchProject domain state. The third should connect the existing PubMed search as a deterministic capability. Only after this vertical slice is stable should additional autonomous research behavior be added.

The next development cycle should be deliberately narrow.

Do not immediately build the complete autonomous research stack.

Build:

```text
“I want to study X.”
        ↓
What exactly do you mean?
        ↓
What has already been done?
        ↓
What reviews exist?
        ↓
What remains uncertain?
        ↓
Is there a meaningful gap?
        ↓
What could you study instead?
        ↓
What data would you need?
        ↓
What should you do next?
```

If real clinicians repeatedly use this flow and subsequently hand real projects to the system, Evidence Copilot has demonstrated product-market signal.

If they do not, adding more databases, more agents, more charts and more automation is unlikely to solve the fundamental problem.

---

# 55. Product Definition in One Sentence

> **Evidence Copilot is a zero-learning-curve clinical Research Agent that turns “我想研究这个” into “这个问题值得做，而且我知道下一步怎么做”。**
