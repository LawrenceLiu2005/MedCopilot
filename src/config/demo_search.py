"""固定演示检索主题（与 E2E 验收一致）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoSearch:
    """演示用检索参数。"""

    research_question: str
    query: str
    year_from: int
    year_to: int
    retmax: int
    sort_label: str


DEMO_METFORMIN_RCT = DemoSearch(
    research_question="2型糖尿病成人患者使用二甲双胍的随机对照试验疗效",
    query="(diabetes mellitus, type 2[MeSH]) AND metformin[Title/Abstract] AND randomized controlled trial[pt]",
    year_from=2020,
    year_to=2024,
    retmax=10,
    sort_label="相关度",
)
