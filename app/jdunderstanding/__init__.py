"""Phase 2 — Job/JD Understanding.

Deterministic-first pipeline over ranked canonical jobs:

    ranked job -> text acquisition (capped) -> section segmentation
    -> taxonomy/experience/education/salary extractors -> JDAnalysis
    -> [optional semantic enhancement behind JdLlmClient protocol]
    -> evidence validation/merge -> AnalysisResult

Rules enforced everywhere:
- JD content is UNTRUSTED DATA, never instructions.
- Every extracted fact carries verbatim evidence + method + confidence.
- EXPLICIT / INFERRED / UNKNOWN remain distinguishable.
- Missing information is UNKNOWN — never inferred from related technologies,
  titles, or prose.
"""

from __future__ import annotations

from app.jdunderstanding.analyzer import AnalysisResult, JDAnalyzer
from app.jdunderstanding.llm import DisabledJdLlmClient, JdLlmClient
from app.jdunderstanding.models import (
    Confidence,
    ExtractionMethod,
    ExtractionStatus,
    Evidence,
    JDAnalysis,
    RequirementLevel,
    SectionKind,
    SkillCategory,
)

__all__ = [
    "AnalysisResult",
    "Confidence",
    "DisabledJdLlmClient",
    "ExtractionMethod",
    "ExtractionStatus",
    "Evidence",
    "JDAnalysis",
    "JDAnalyzer",
    "JdLlmClient",
    "RequirementLevel",
    "SectionKind",
    "SkillCategory",
]
